from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import httpx
import pdfplumber

from .catalog import catalog_sha256, load_v5_catalog
from .contracts import CandidateField, IngestRequest, PluginFieldResult, V5CandidatePreview
from .dynamic_gapfill import DynamicMaterialPage
from .llm_plugin import (
    CompletionReceipt,
    LlmPluginError,
    OpenAICompatibleCompletion,
    SchemaGuidedLlmPlugin,
)
from .m152_gapfill import _replace_preview_fields, _review_error_code
from .m154_concurrency import (
    AdaptiveProviderGate,
    GlobalCallBudget,
    ProductConcurrencyProfile,
    ProductWork,
    ProviderAttemptTiming,
    RetryBudgetUnavailable,
    RunTimingRecorder,
    execute_products_ordered,
    invoke_provider_attempt,
)
from .m156_quality import (
    M156_FOCUS_FIELD_IDS,
    M156_LONG_ATOMIC_FIELD_IDS,
    M156FieldContext,
    build_m156_field_context,
    choose_m156_replacement,
)
from .material_support import compute_material_supported_extraction_rate
from .provider_trial import (
    APPROVED_PRODUCTS,
    ProviderAttemptReceipt,
    ProviderIdentity,
    ProviderTrialError,
    ProviderTrialProduct,
    V5ProviderTrialRun,
    load_provider_trial_run,
    seal_provider_trial_run,
    write_provider_trial_run,
)
from .source_evidence import SourcePage, classify_evidence

M156_PRODUCT_IDS: tuple[str, ...] = ("596", "5003", "1830", "1814", "1816", "1828")
M156_BASELINE_RUN_SHA256 = "dc5d3ecd2bc29a1409c1d581ffd202b03490c7a3cc8e1cda2ef0cf15092fd60b"
M156_BASELINE_FILE_SHA256 = "82920ff26652a378446730740e46e035ae2f9de4182666e5255b802cb9bfdff9"
M156_CATALOG_SHA256 = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M156_BUSINESS_FEEDBACK_SHA256 = "3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3"
M156_MAX_CALLS = 18


@dataclass(frozen=True, slots=True)
class M156Material:
    pages: tuple[DynamicMaterialPage, ...]
    scanned_page_count: int
    unreadable_page_locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class M156CallRecord:
    provider_call: int
    product_version_id: str
    batch_index: int
    attempt: int
    kind: str
    target_field_ids: tuple[str, ...]
    context_sha256: str
    outcome: str
    error_code: str | None
    completion: CompletionReceipt | None


@dataclass(frozen=True, slots=True)
class M156FieldRecord:
    field_id: str
    display_name: str
    batch_index: int
    provider_call: int
    phase: str
    action: str
    reason: str
    changed: bool
    coverage: Mapping[str, Any]
    baseline_audit: Mapping[str, Any] | None
    proposed_audit: Mapping[str, Any] | None
    before: Mapping[str, Any]
    proposed: Mapping[str, Any] | None
    after: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class M156ProductExecution:
    product: ProviderTrialProduct
    calls: tuple[M156CallRecord, ...]
    fields: tuple[M156FieldRecord, ...]
    attempt_timings: tuple[ProviderAttemptTiming, ...]
    material: M156Material


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_digest(contract: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {"contract": contract, **payload},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _typed_error_code(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"PROVIDER_HTTP_{error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return "PROVIDER_NETWORK_ERROR"
    value = str(error).strip()
    if value and len(value) <= 120 and all(
        character.isalnum() or character == "_" for character in value
    ):
        return value
    return type(error).__name__.upper()


def _snapshot(field: CandidateField | PluginFieldResult) -> dict[str, Any]:
    return {
        "state": field.state,
        "value": field.value,
        "evidence": [item.model_dump(mode="json") for item in field.evidence],
    }


def _load_m156_material(
    *,
    product: ProviderTrialProduct,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
) -> M156Material:
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    approved_by_id = {item.product_id: item for item in APPROVED_PRODUCTS}
    try:
        approved = approved_by_id[product.product_id]
    except KeyError as exc:
        raise ProviderTrialError("M156_APPROVED_PRODUCT_MISSING") from exc
    root = serious_illness_root if product.product_id == "1828" else sample_root
    folder = root / approved.directory_name
    if not folder.is_dir():
        raise ProviderTrialError("M156_PRODUCT_ROOT_MISSING")
    expected_names = {"product_meta.json", *(item.file_name for item in approved.pdfs)}
    actual_names = {path.name for path in folder.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ProviderTrialError("M156_SOURCE_SET_DRIFT")
    metadata = folder / "product_meta.json"
    if _sha256_bytes(metadata.read_bytes()) != approved.metadata_sha256:
        raise ProviderTrialError("M156_SOURCE_METADATA_SHA256_DRIFT")

    base_names = {item.file_name for item in approved.pdfs}
    pages: list[DynamicMaterialPage] = []
    unreadable: list[str] = []
    scanned = 0
    for receipt in product.files:
        path = (
            folder / receipt.file_name
            if receipt.file_name in base_names
            else supplemental_root_596 / receipt.file_name
        )
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != receipt.sha256:
            raise ProviderTrialError("M156_SOURCE_FILE_SHA256_DRIFT")
        with pdfplumber.open(path) as document:
            if len(document.pages) != receipt.page_count:
                raise ProviderTrialError("M156_SOURCE_PAGE_COUNT_DRIFT")
            for page_number, page in enumerate(document.pages, 1):
                scanned += 1
                text = (page.extract_text() or "").strip()
                locator = f"pdf:{receipt.file_name}#page={page_number}"
                if not text:
                    unreadable.append(locator)
                    continue
                pages.append(
                    DynamicMaterialPage(
                        document_name=receipt.file_name,
                        document_sha256=receipt.sha256,
                        page_number=page_number,
                        text=text,
                    )
                )
    return M156Material(
        pages=tuple(pages),
        scanned_page_count=scanned,
        unreadable_page_locators=tuple(unreadable),
    )


def plan_m156_batches(insurance_class: str) -> tuple[tuple[str, ...], ...]:
    schema = load_v5_catalog().schema_for(insurance_class)
    applicable = tuple(
        field.field_id for field in schema.fields if field.field_id in M156_FOCUS_FIELD_IDS
    )
    long_fields = tuple(
        field_id for field_id in applicable if field_id in M156_LONG_ATOMIC_FIELD_IDS
    )
    compact_fields = tuple(
        field_id for field_id in applicable if field_id not in M156_LONG_ATOMIC_FIELD_IDS
    )
    batches = tuple(batch for batch in (long_fields, compact_fields) if batch)
    if len(batches) != 2 or set(field_id for batch in batches for field_id in batch) != set(
        applicable
    ):
        raise ProviderTrialError("M156_BATCH_TOPOLOGY_INVALID")
    return batches


def _project_batch_results(
    results: Sequence[PluginFieldResult], field_ids: tuple[str, ...]
) -> tuple[PluginFieldResult, ...]:
    """Project the plugin's full-schema response onto one ordered batch."""

    requested = set(field_ids)
    targeted = tuple(field for field in results if field.field_id in requested)
    if tuple(field.field_id for field in targeted) != field_ids:
        raise LlmPluginError("M156_PROVIDER_FIELD_TOPOLOGY_DRIFT")
    return targeted


def _execute_batch(
    *,
    product: ProviderTrialProduct,
    preview: V5CandidatePreview,
    material: M156Material,
    field_ids: tuple[str, ...],
    context: str,
    completion: OpenAICompatibleCompletion,
    evidence_classifier: Callable[..., Any] = classify_evidence,
    repair_hint: str | None = None,
) -> tuple[PluginFieldResult, ...]:
    source_pages = tuple(
        SourcePage(
            document_name=page.document_name,
            document_sha256=page.document_sha256,
            page_number=page.page_number,
            text=page.text,
        )
        for page in material.pages
    )
    request = IngestRequest(
        source_revision_id=preview.source_revision_id,
        catalog_id=preview.catalog_id,
        schema_id=preview.schema_id,
        product_id=preview.product_id,
        product_version_id=preview.product_version_id,
        product_display_name=preview.product_display_name,
        reviewed_insurance_class=preview.insurance_class,
        source_text=context,
    )
    result = SchemaGuidedLlmPlugin(
        completion=completion,
        evidence_resolver=lambda quote, locator: evidence_classifier(
            source_pages, quote, locator
        ),
        repair_hint=repair_hint,
        target_field_ids=field_ids,
    ).extract(request, load_v5_catalog().schema_for(product.insurance_class))
    # SchemaGuidedLlmPlugin deliberately returns the complete schema topology;
    # fields outside this bounded batch are returned as ``unknown``.  The
    # batch executor must project that result back to the requested, ordered
    # field set before merge.  Treating the full plugin result as a batch was
    # the cause of M156_PROVIDER_FIELD_TOPOLOGY_DRIFT in the first run.
    return _project_batch_results(result.fields, field_ids)


def _merge_batch(
    *,
    preview: V5CandidatePreview,
    results: Sequence[PluginFieldResult],
    context: M156FieldContext,
    batch_index: int,
    provider_call: int,
    phase: str,
    replacement_chooser: Callable[..., Any] = choose_m156_replacement,
) -> tuple[V5CandidatePreview, tuple[M156FieldRecord, ...], tuple[str, ...]]:
    before_by_id = {field.field_id: field for field in preview.fields}
    updates: dict[str, PluginFieldResult] = {}
    records: list[M156FieldRecord] = []
    retry_fields: list[str] = []
    for result in results:
        original = before_by_id[result.field_id]
        evidence_ok = bool(result.evidence) and all(
            item.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
            for item in result.evidence
        )
        replacement = replacement_chooser(
            field_id=result.field_id,
            baseline_state=original.state,
            baseline_value=original.value,
            baseline_evidence_quotes=tuple(item.quote for item in original.evidence),
            proposed_state=result.state,
            proposed_value=result.value,
            proposed_evidence_quotes=tuple(item.quote for item in result.evidence),
            candidate_text=context.text,
            product_display_name=preview.product_display_name,
        )
        action = replacement.action if evidence_ok else "keep_baseline"
        reason = replacement.reason if evidence_ok else "PROPOSAL_EVIDENCE_UNVERIFIED"
        if action == "replace":
            updates[result.field_id] = result
        elif not replacement.proposed_audit.accepted or result.state == "unknown":
            retry_fields.append(result.field_id)
        after = result if action == "replace" else original
        records.append(
            M156FieldRecord(
                field_id=result.field_id,
                display_name=original.display_name,
                batch_index=batch_index,
                provider_call=provider_call,
                phase=phase,
                action=action,
                reason=reason,
                changed=action == "replace",
                coverage=asdict(context.coverage[result.field_id]),
                baseline_audit=(
                    asdict(replacement.baseline_audit)
                    if replacement.baseline_audit is not None
                    else None
                ),
                proposed_audit=asdict(replacement.proposed_audit),
                before=_snapshot(original),
                proposed=_snapshot(result),
                after=_snapshot(after),
            )
        )
    return _replace_preview_fields(preview, updates), tuple(records), tuple(retry_fields)


def _error_records(
    *,
    preview: V5CandidatePreview,
    field_ids: Sequence[str],
    context: M156FieldContext,
    batch_index: int,
    provider_call: int,
    phase: str,
    error_code: str,
) -> tuple[M156FieldRecord, ...]:
    by_id = {field.field_id: field for field in preview.fields}
    return tuple(
        M156FieldRecord(
            field_id=field_id,
            display_name=by_id[field_id].display_name,
            batch_index=batch_index,
            provider_call=provider_call,
            phase=phase,
            action="keep_baseline",
            reason=error_code,
            changed=False,
            coverage=asdict(context.coverage[field_id]),
            baseline_audit=None,
            proposed_audit=None,
            before=_snapshot(by_id[field_id]),
            proposed=None,
            after=_snapshot(by_id[field_id]),
        )
        for field_id in field_ids
    )


def _repair_hint(records: Sequence[M156FieldRecord]) -> str:
    failures = [
        {
            "field_id": item.field_id,
            "failed_check": item.reason,
            "missing_components": (
                item.proposed_audit.get("missing_components", ())
                if item.proposed_audit
                else ()
            ),
        }
        for item in records
    ]
    return (
        "Mission 156 bounded structural repair. Re-read all supplied pages independently. "
        "Return a complete material-supported value for each ordered field and obey its field "
        "instruction. The failed structural checks below are not expected answers and the prior "
        "value is intentionally omitted. Never invent a missing fact. failures="
        + json.dumps(failures, ensure_ascii=False, separators=(",", ":"))
    )


def _attempt_receipts(
    calls: Sequence[M156CallRecord],
    *,
    review_error: str | None,
) -> tuple[ProviderAttemptReceipt, ...]:
    attempts: list[ProviderAttemptReceipt] = []
    for index, call in enumerate(calls, 1):
        outcome: Literal[
            "ACCEPTED", "PRESERVED", "REJECTED", "ERROR", "REPAIR_REJECTED"
        ]
        error_code: str | None
        if call.outcome == "ERROR":
            outcome = (
                "REPAIR_REJECTED"
                if review_error is not None and index == len(calls) and index >= 2
                else "ERROR"
            )
            error_code = call.error_code or "M156_PROVIDER_ERROR"
        else:
            outcome = "PRESERVED" if review_error is not None else "ACCEPTED"
            error_code = review_error
        completion = call.completion
        attempts.append(
            ProviderAttemptReceipt(
                attempt=index,
                outcome=outcome,
                response_id=completion.response_id if completion else None,
                response_model=completion.response_model if completion else None,
                finish_reason=completion.finish_reason if completion else None,
                prompt_tokens=completion.prompt_tokens if completion else None,
                completion_tokens=completion.completion_tokens if completion else None,
                total_tokens=completion.total_tokens if completion else None,
                error_code=error_code,
            )
        )
    return tuple(attempts)


def _output_product(
    baseline: ProviderTrialProduct,
    preview: V5CandidatePreview,
    calls: Sequence[M156CallRecord],
) -> ProviderTrialProduct:
    review_error = _review_error_code(preview)
    metrics = compute_material_supported_extraction_rate(preview, baseline.material_support)
    return ProviderTrialProduct(
        product_id=baseline.product_id,
        product_version_id=baseline.product_version_id,
        product_display_name=baseline.product_display_name,
        insurance_class=baseline.insurance_class,
        schema_id=baseline.schema_id,
        source_revision_id=baseline.source_revision_id,
        source_manifest_sha256=baseline.source_manifest_sha256,
        status="SUCCESS" if review_error is None else "REVIEW_REQUIRED",
        error_code=review_error,
        files=baseline.files,
        attempts=_attempt_receipts(calls, review_error=review_error),
        preview=preview,
        material_support=baseline.material_support,
        material_support_metrics=metrics,
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def run_m156(
    *,
    baseline_path: Path,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
    business_feedback_path: Path,
    output_path: Path,
    audit_output_path: Path,
    completion_factory: Callable[[], OpenAICompatibleCompletion],
    concurrency_profile: ProductConcurrencyProfile,
    run_code: str = "M156",
    product_ids: Sequence[str] = M156_PRODUCT_IDS,
    baseline_run_sha256: str = M156_BASELINE_RUN_SHA256,
    baseline_file_sha256: str = M156_BASELINE_FILE_SHA256,
    expected_catalog_sha256: str = M156_CATALOG_SHA256,
    business_feedback_sha256: str = M156_BUSINESS_FEEDBACK_SHA256,
    max_calls: int = M156_MAX_CALLS,
    expected_primary_calls: int = 12,
    audit_contract: str = "insurance-v5-m156-seven-field-audit.v1",
    focus_field_ids: Sequence[str] = M156_FOCUS_FIELD_IDS,
    batch_planner: Callable[[str], tuple[tuple[str, ...], ...]] = plan_m156_batches,
    context_builder: Callable[..., M156FieldContext] = build_m156_field_context,
    replacement_chooser: Callable[..., Any] = choose_m156_replacement,
    evidence_classifier: Callable[..., Any] = classify_evidence,
) -> tuple[V5ProviderTrialRun, Mapping[str, Any]]:
    if output_path.resolve() == baseline_path.resolve():
        raise ProviderTrialError(f"{run_code}_BASELINE_OVERWRITE_FORBIDDEN")
    if output_path.exists() or audit_output_path.exists():
        raise ProviderTrialError(f"{run_code}_OUTPUT_ALREADY_EXISTS")
    if _sha256_bytes(baseline_path.read_bytes()) != baseline_file_sha256:
        raise ProviderTrialError(f"{run_code}_BASELINE_FILE_SHA256_DRIFT")
    if (
        not business_feedback_path.is_file()
        or _sha256_bytes(business_feedback_path.read_bytes())
        != business_feedback_sha256
    ):
        raise ProviderTrialError(f"{run_code}_BUSINESS_FEEDBACK_SHA256_DRIFT")
    baseline = load_provider_trial_run(baseline_path)
    if baseline.run_sha256 != baseline_run_sha256:
        raise ProviderTrialError(f"{run_code}_BASELINE_RUN_SHA256_DRIFT")
    catalog = load_v5_catalog()
    if catalog_sha256(catalog) != expected_catalog_sha256:
        raise ProviderTrialError(f"{run_code}_CATALOG_SHA256_DRIFT")
    by_id = {product.product_id: product for product in baseline.products}
    if any(product_id not in by_id for product_id in product_ids):
        raise ProviderTrialError(f"{run_code}_PRODUCT_SET_MISSING")
    products = tuple(by_id[product_id] for product_id in product_ids)

    timer = RunTimingRecorder()
    with timer.stage("materials_parse"):
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = {
                product.product_version_id: pool.submit(
                    _load_m156_material,
                    product=product,
                    sample_root=sample_root,
                    serious_illness_root=serious_illness_root,
                    supplemental_root_596=supplemental_root_596,
                )
                for product in products
            }
            materials = {version: future.result() for version, future in futures.items()}
    print(
        json.dumps(
            {
                "event": f"{run_code}_MATERIALS_VALIDATED",
                "products": len(materials),
                "pdfs": sum(len(product.files) for product in products),
                "scanned_pages": sum(item.scanned_page_count for item in materials.values()),
                "readable_pages": sum(len(item.pages) for item in materials.values()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    with timer.stage("planning"):
        batches = {
            product.product_version_id: batch_planner(product.insurance_class)
            for product in products
        }
        primary_count = sum(len(item) for item in batches.values())
        if primary_count != expected_primary_calls:
            raise ProviderTrialError(f"{run_code}_PRIMARY_CALL_TOPOLOGY_DRIFT")
        contexts: dict[tuple[str, tuple[str, ...]], M156FieldContext] = {}
        for product in products:
            schema = catalog.schema_for(product.insurance_class)
            material = materials[product.product_version_id]
            applicable = tuple(
                field.field_id
                for field in schema.fields
                if field.field_id in set(focus_field_ids)
            )
            for field_ids in (*batches[product.product_version_id], applicable):
                cache_key = (product.product_version_id, field_ids)
                if cache_key not in contexts:
                    contexts[cache_key] = context_builder(
                        material.pages,
                        schema,
                        field_ids,
                        product_display_name=product.product_display_name,
                        max_characters=150_000,
                    )
    print(
        json.dumps(
            {
                "event": f"{run_code}_PLAN_FROZEN",
                "primary_calls": primary_count,
                "max_calls": max_calls,
                "max_product_workers": concurrency_profile.max_products,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    budget = GlobalCallBudget(total_calls=max_calls, required_primary_calls=primary_count)
    gate = AdaptiveProviderGate(concurrency_profile)

    def execute_product(work: ProductWork[ProviderTrialProduct]) -> M156ProductExecution:
        product = work.payload
        if product.preview is None:
            raise ProviderTrialError(f"{run_code}_BASELINE_PREVIEW_MISSING")
        material = materials[product.product_version_id]
        preview = product.preview
        completion = completion_factory()
        calls: list[M156CallRecord] = []
        records: list[M156FieldRecord] = []
        timings: list[ProviderAttemptTiming] = []
        retry_fields: list[str] = []

        def invoke(
            field_ids: tuple[str, ...],
            context: M156FieldContext,
            *,
            batch_index: int,
            phase: str,
            retry: bool,
            repair_hint: str | None = None,
        ) -> tuple[PluginFieldResult, ...] | None:
            before_receipts = len(completion.receipts)
            outcome = invoke_provider_attempt(
                budget=budget,
                gate=gate,
                product_version_id=product.product_version_id,
                batch_index=batch_index,
                attempt=1 if not retry else 2,
                retry=retry,
                call=partial(
                    _execute_batch,
                    product=product,
                    preview=preview,
                    material=material,
                    field_ids=field_ids,
                    context=context.text,
                    completion=completion,
                    evidence_classifier=evidence_classifier,
                    repair_hint=repair_hint,
                ),
            )
            timings.append(outcome.timing)
            provider_receipt = (
                completion.receipts[-1]
                if len(completion.receipts) > before_receipts
                else None
            )
            error_code = _typed_error_code(outcome.error) if outcome.error else None
            calls.append(
                M156CallRecord(
                    provider_call=outcome.reservation.provider_call,
                    product_version_id=product.product_version_id,
                    batch_index=batch_index,
                    attempt=outcome.reservation.attempt,
                    kind=phase,
                    target_field_ids=field_ids,
                    context_sha256=_sha256_text(context.text),
                    outcome="ERROR" if outcome.error else "ACCEPTED",
                    error_code=error_code,
                    completion=provider_receipt,
                )
            )
            print(
                json.dumps(
                    {
                        "event": f"{run_code}_PROVIDER_CALL",
                        "provider_call": outcome.reservation.provider_call,
                        "product_version_id": product.product_version_id,
                        "batch_index": batch_index,
                        "phase": phase,
                        "outcome": "ERROR" if outcome.error else "ACCEPTED",
                        "error_code": error_code,
                        "duration_ms": outcome.timing.duration_ms,
                        "active_limit": gate.current_limit,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return outcome.value if outcome.error is None else None

        try:
            for batch_index, field_ids in enumerate(batches[product.product_version_id], 1):
                context = contexts[(product.product_version_id, field_ids)]
                results = invoke(
                    field_ids,
                    context,
                    batch_index=batch_index,
                    phase="primary",
                    retry=False,
                )
                if results is None:
                    try:
                        results = invoke(
                            field_ids,
                            context,
                            batch_index=batch_index,
                            phase="provider_retry",
                            retry=True,
                        )
                    except RetryBudgetUnavailable:
                        results = None
                if results is None:
                    last_call = calls[-1]
                    records.extend(
                        _error_records(
                            preview=preview,
                            field_ids=field_ids,
                            context=context,
                            batch_index=batch_index,
                            provider_call=last_call.provider_call,
                            phase="primary",
                            error_code=last_call.error_code
                            or f"{run_code}_PROVIDER_RESULT_MISSING",
                        )
                    )
                    retry_fields.extend(field_ids)
                    continue
                preview, merged, retry = _merge_batch(
                    preview=preview,
                    results=results,
                    context=context,
                    batch_index=batch_index,
                    provider_call=calls[-1].provider_call,
                    phase="primary",
                    replacement_chooser=replacement_chooser,
                )
                records.extend(merged)
                retry_fields.extend(retry)

            repair_ids = tuple(
                field.field_id
                for field in catalog.schema_for(product.insurance_class).fields
                if field.field_id in set(retry_fields)
            )
            if repair_ids:
                context = contexts[
                    (
                        product.product_version_id,
                        tuple(
                            field.field_id
                            for field in catalog.schema_for(product.insurance_class).fields
                            if field.field_id in set(focus_field_ids)
                        ),
                    )
                ]
                failed_records = tuple(
                    record for record in records if record.field_id in set(repair_ids)
                )
                try:
                    results = invoke(
                        repair_ids,
                        context,
                        batch_index=len(batches[product.product_version_id]) + 1,
                        phase="quality_repair",
                        retry=True,
                        repair_hint=_repair_hint(failed_records),
                    )
                except RetryBudgetUnavailable:
                    results = None
                if results is not None:
                    preview, merged, _retry = _merge_batch(
                        preview=preview,
                        results=results,
                        context=context,
                        batch_index=len(batches[product.product_version_id]) + 1,
                        provider_call=calls[-1].provider_call,
                        phase="quality_repair",
                        replacement_chooser=replacement_chooser,
                    )
                    records.extend(merged)
        finally:
            completion.close()

        output = _output_product(product, preview, calls)
        return M156ProductExecution(
            product=output,
            calls=tuple(calls),
            fields=tuple(records),
            attempt_timings=tuple(timings),
            material=material,
        )

    works = tuple(
        ProductWork(
            ordinal=index,
            product_version_id=product.product_version_id,
            payload=product,
        )
        for index, product in enumerate(products)
    )
    with timer.stage("provider"):
        execution = execute_products_ordered(
            works,
            worker=execute_product,
            profile=concurrency_profile,
        )

    started_at = timer.started_at
    with timer.stage("merge_write"):
        finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        run = seal_provider_trial_run(
            provider=ProviderIdentity(),
            products=tuple(item.product for item in execution.values),
            started_at=started_at,
            finished_at=finished_at,
        )
        write_provider_trial_run(output_path, run)
    performance = timer.finish(
        peak_product_workers=execution.peak_products,
        peak_provider_calls=gate.peak_active,
        product_timings=execution.product_timings,
        provider_attempts=tuple(
            timing for item in execution.values for timing in item.attempt_timings
        ),
        throttle_events=gate.throttle_events,
    )

    final_records: dict[tuple[str, str], M156FieldRecord] = {}
    for item in execution.values:
        for record in item.fields:
            final_records[(item.product.product_id, record.field_id)] = record
    baseline_supported = sum(
        product.material_support_metrics.material_supported_field_count
        for product in products
        if product.material_support_metrics is not None
    )
    baseline_present = sum(
        product.material_support_metrics.material_supported_present_count
        for product in products
        if product.material_support_metrics is not None
    )
    result_supported = sum(
        item.product.material_support_metrics.material_supported_field_count
        for item in execution.values
        if item.product.material_support_metrics is not None
    )
    result_present = sum(
        item.product.material_support_metrics.material_supported_present_count
        for item in execution.values
        if item.product.material_support_metrics is not None
    )
    audit_payload: dict[str, Any] = {
        "baseline_file_sha256": baseline_file_sha256,
        "baseline_run_sha256": baseline_run_sha256,
        "result_run_sha256": run.run_sha256,
        "catalog_sha256": expected_catalog_sha256,
        "business_feedback_sha256": business_feedback_sha256,
        "provider": ProviderIdentity().model_dump(mode="json"),
        "max_calls": max_calls,
        "call_count": budget.used,
        "started_at": started_at,
        "finished_at": finished_at,
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "performance": performance.model_dump(mode="json"),
        "metrics": {
            "product_count": len(execution.values),
            "pdf_count": sum(len(item.product.files) for item in execution.values),
            "scanned_page_count": sum(
                item.material.scanned_page_count for item in execution.values
            ),
            "focus_field_count": len(final_records),
            "changed_field_count": sum(record.changed for record in final_records.values()),
            "rejected_field_count": sum(
                record.proposed_audit is None
                or not bool(record.proposed_audit.get("accepted"))
                for record in final_records.values()
            ),
            "baseline_material_supported_present_count": baseline_present,
            "baseline_material_supported_field_count": baseline_supported,
            "baseline_material_supported_extraction_rate": (
                baseline_present / baseline_supported if baseline_supported else 0.0
            ),
            "material_supported_present_count": result_present,
            "material_supported_field_count": result_supported,
            "material_supported_extraction_rate": (
                result_present / result_supported if result_supported else 0.0
            ),
        },
        "products": [
            {
                "product_id": item.product.product_id,
                "product_version_id": item.product.product_version_id,
                "product_display_name": item.product.product_display_name,
                "scanned_page_count": item.material.scanned_page_count,
                "readable_page_count": len(item.material.pages),
                "unreadable_page_locators": item.material.unreadable_page_locators,
                "calls": [
                    {
                        **asdict(call),
                        "completion": (
                            call.completion.model_dump(mode="json")
                            if call.completion
                            else None
                        ),
                    }
                    for call in item.calls
                ],
                "fields": [asdict(record) for record in item.fields],
            }
            for item in execution.values
        ],
    }
    contract = audit_contract
    audit = {
        "contract": contract,
        "artifact_sha256": _canonical_digest(contract, audit_payload),
        **audit_payload,
    }
    _write_json(audit_output_path, audit)
    return run, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission 156 six-product seven-field run")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--serious-illness-root", type=Path, required=True)
    parser.add_argument("--supplemental-root-596", type=Path, required=True)
    parser.add_argument("--business-feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit("M156_PROVIDER_API_KEY_NOT_CONFIGURED")

    def completion_factory() -> OpenAICompatibleCompletion:
        return OpenAICompatibleCompletion(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model="qwen-plus",
            model_family="qwen",
            timeout_seconds=300.0,
            max_calls=M156_MAX_CALLS,
        )

    started = perf_counter()
    run, audit = run_m156(
        baseline_path=args.baseline,
        sample_root=args.sample_root,
        serious_illness_root=args.serious_illness_root,
        supplemental_root_596=args.supplemental_root_596,
        business_feedback_path=args.business_feedback,
        output_path=args.output,
        audit_output_path=args.audit_output,
        completion_factory=completion_factory,
        concurrency_profile=ProductConcurrencyProfile(
            max_products=args.max_product_concurrency
        ),
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_sha256": run.run_sha256,
                "call_count": audit["call_count"],
                "metrics": audit["metrics"],
                "elapsed_seconds": round(perf_counter() - started, 3),
                "output": str(args.output.resolve()),
                "audit_output": str(args.audit_output.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "M156_MAX_CALLS",
    "M156_PRODUCT_IDS",
    "plan_m156_batches",
    "run_m156",
]
