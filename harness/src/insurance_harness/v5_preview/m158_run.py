from __future__ import annotations

import argparse
import json
import os
import re
import zipfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any, Protocol
from xml.etree import ElementTree

from .catalog import catalog_sha256, load_v5_catalog
from .contracts import CandidateValue, PluginFieldResult, TriState, V5CandidatePreview
from .llm_plugin import OpenAICompatibleCompletion
from .m152_gapfill import _replace_preview_fields
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
    M156FieldDecision,
    M156ReplacementDecision,
)
from .m156_run import (
    M156_PRODUCT_IDS,
    M156CallRecord,
    M156FieldRecord,
    M156Material,
    M156ProductExecution,
    _canonical_digest,
    _execute_batch,
    _load_m156_material,
    _output_product,
    _sha256_bytes,
    _sha256_text,
    _snapshot,
    _typed_error_code,
    _write_json,
)
from .m157_quality import build_m157_field_context, classify_m157_evidence
from .m158_quality import (
    M158_LONG_FIELD_IDS,
    M158_MAX_CALLS,
    FeedbackIssue,
    LongFieldShard,
    admit_verified_evidence_subset,
    assess_feedback_issues,
    build_long_field_shards,
    choose_m158_replacement,
    merge_atomic_shard_results,
)
from .provider_trial import (
    ProviderIdentity,
    ProviderTrialError,
    ProviderTrialProduct,
    V5ProviderTrialRun,
    load_provider_trial_run,
    seal_provider_trial_run,
    write_provider_trial_run,
)

M158_BASELINE_RUN_SHA256 = "b00fc0daa029e07c3f106de6387af4a144c4338d8fca2a482af3e13fb3038247"
M158_BASELINE_FILE_SHA256 = "5f136ece85ca6626ae691f0290b625c0f86caf7e17d127b32164a23cc4934ec4"
M158_CATALOG_SHA256 = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M158_BUSINESS_FEEDBACK_SHA256 = "3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3"
M158_EXPECTED_FEEDBACK_ISSUES = 30
M158_ARTIFACT_LABEL = "m158"
M158_FOCUS_FIELD_IDS: tuple[str, ...] = M156_FOCUS_FIELD_IDS
M158_MAX_COMPACT_FIELDS = 8

_FIELD_NAME_TO_ID: Mapping[str, str] = {
    "保险责任": "coverage_responsibilities",
    "责任免除": "exclusions",
    "缴费期限": "premium_payment_term",
    "缴费方式": "premium_payment_frequency",
    "保单权益": "policyholder_rights",
    "等待期": "waiting_period",
    "疾病定义与认定标准": "disease_definitions_and_criteria",
}
_PRODUCT_NAME_TO_ID: Mapping[str, str] = {
    "e生保尊享（医疗险）": "596",
    "盛世金越（终身寿险）": "5003",
    "年金险测试产品": "1830",
    "意外伤害保险": "1814",
    "失能收入损失保险": "1816",
    "重疾险测试产品": "1828",
}


@dataclass(frozen=True, slots=True)
class M158Batch:
    batch_index: int
    field_ids: tuple[str, ...]
    context: str
    kind: str
    coverage: Mapping[str, Mapping[str, Any]]
    shard: LongFieldShard | None = None


class MaterialLoader(Protocol):
    def __call__(
        self,
        *,
        product: ProviderTrialProduct,
        sample_root: Path,
        serious_illness_root: Path,
        supplemental_root_596: Path,
    ) -> M156Material: ...


class RepairHintBuilder(Protocol):
    def __call__(self, batch: M158Batch) -> str: ...


class EvidenceAdmitter(Protocol):
    def __call__(
        self,
        result: PluginFieldResult,
        *,
        candidate_text: str,
        product_display_name: str,
    ) -> tuple[PluginFieldResult | None, M156FieldDecision]: ...


class ReplacementSelector(Protocol):
    def __call__(
        self,
        *,
        field_id: str,
        baseline_state: TriState,
        baseline_value: CandidateValue | None,
        baseline_evidence_quotes: Sequence[str],
        proposed_state: TriState,
        proposed_value: CandidateValue | None,
        proposed_evidence_quotes: Sequence[str],
        candidate_text: str,
        product_display_name: str,
    ) -> M156ReplacementDecision: ...


@dataclass(frozen=True, slots=True)
class M158RunPolicy:
    """Immutable run-specific dependencies and frozen artifact identities."""

    baseline_run_sha256: str
    baseline_file_sha256: str
    catalog_sha256: str
    business_feedback_sha256: str
    artifact_label: str
    focus_field_ids: tuple[str, ...]
    max_compact_fields: int
    material_loader: MaterialLoader
    repair_hint_builder: RepairHintBuilder
    evidence_admitter: EvidenceAdmitter
    replacement_selector: ReplacementSelector

    @classmethod
    def default(cls) -> M158RunPolicy:
        return cls(
            baseline_run_sha256=M158_BASELINE_RUN_SHA256,
            baseline_file_sha256=M158_BASELINE_FILE_SHA256,
            catalog_sha256=M158_CATALOG_SHA256,
            business_feedback_sha256=M158_BUSINESS_FEEDBACK_SHA256,
            artifact_label=M158_ARTIFACT_LABEL,
            focus_field_ids=M158_FOCUS_FIELD_IDS,
            max_compact_fields=M158_MAX_COMPACT_FIELDS,
            material_loader=_load_m156_material,
            repair_hint_builder=_repair_hint,
            evidence_admitter=admit_verified_evidence_subset,
            replacement_selector=choose_m158_replacement,
        )


def _long_shard_limit(field_id: str) -> int:
    return 24_000 if field_id == "disease_definitions_and_criteria" else 42_000


def _plan_product_batches(
    product: ProviderTrialProduct,
    material: M156Material,
    *,
    policy: M158RunPolicy,
) -> tuple[M158Batch, ...]:
    catalog = load_v5_catalog()
    schema = catalog.schema_for(product.insurance_class)
    applicable = tuple(
        field.field_id for field in schema.fields if field.field_id in policy.focus_field_ids
    )
    plans: list[M158Batch] = []
    index = 0
    for field_id in applicable:
        if field_id not in M158_LONG_FIELD_IDS:
            continue
        shards = build_long_field_shards(
            material.pages,
            schema,
            field_id,
            product_display_name=product.product_display_name,
            max_characters=_long_shard_limit(field_id),
        )
        for shard in shards:
            index += 1
            plans.append(
                M158Batch(
                    batch_index=index,
                    field_ids=(field_id,),
                    context=shard.text,
                    kind="long_field_shard",
                    coverage={
                        field_id: {
                            "scanned_page_count": shard.scanned_page_count,
                            "candidate_page_count": len(shard.candidate_locators),
                            "included_page_count": len(shard.selected_locators),
                            "candidate_locators": shard.candidate_locators,
                            "selected_locators": shard.selected_locators,
                            "shard_index": shard.shard_index,
                            "shard_count": shard.shard_count,
                        }
                    },
                    shard=shard,
                )
            )
    compact_ids = tuple(
        field_id for field_id in applicable if field_id not in M158_LONG_FIELD_IDS
    )
    for start in range(0, len(compact_ids), policy.max_compact_fields):
        compact_batch_ids = compact_ids[start : start + policy.max_compact_fields]
        if not compact_batch_ids:
            continue
        context = build_m157_field_context(
            material.pages,
            schema,
            compact_batch_ids,
            product_display_name=product.product_display_name,
            max_characters=150_000,
        )
        index += 1
        plans.append(
            M158Batch(
                batch_index=index,
                field_ids=compact_batch_ids,
                context=context.text,
                kind="compact_coupled",
                coverage={
                    field_id: asdict(context.coverage[field_id])
                    for field_id in compact_batch_ids
                },
            )
        )
    return tuple(plans)


def _repair_hint(batch: M158Batch) -> str:
    if batch.kind == "long_field_shard":
        return (
            "Mission 158 field shard. Read this bounded shard independently and return every "
            "material-supported atomic item for the one target field. Keep formal conditions, "
            "exceptions, limits and applicable contract. Do not return a directory reference, "
            "do not use 等 or 详见, and do not infer facts from another contract. Evidence must "
            "be a short verbatim quote from one marked page for each atomic item."
        )
    return (
        "Mission 158 coupled compact fields. Extract formal option sets instead of illustration "
        "examples. Keep payment term separate from payment frequency. Waiting period must include "
        "duration, starting point, applicable responsibility, accident exception and stated "
        "consequence when present. Policy rights must belong to the current product, not merely "
        "to a referenced main or additional contract. Never invent an unsupported value."
    )


def _candidate_field_result(preview: V5CandidatePreview, field_id: str) -> PluginFieldResult:
    field = next(item for item in preview.fields if item.field_id == field_id)
    return PluginFieldResult(
        ordinal=field.ordinal,
        field_id=field.field_id,
        state=field.state,
        value=field.value,
        evidence=field.evidence,
    )


def _unknown_result(preview: V5CandidatePreview, field_id: str) -> PluginFieldResult:
    field = next(item for item in preview.fields if item.field_id == field_id)
    return PluginFieldResult(
        ordinal=field.ordinal,
        field_id=field_id,
        state="unknown",
        value=None,
        evidence=(),
    )


def _field_record(
    *,
    preview: V5CandidatePreview,
    result: PluginFieldResult,
    candidate_text: str,
    coverage: Mapping[str, Any],
    batch_index: int,
    provider_call: int,
    phase: str,
    replacement_selector: ReplacementSelector,
) -> tuple[V5CandidatePreview, M156FieldRecord]:
    original = next(field for field in preview.fields if field.field_id == result.field_id)
    replacement = replacement_selector(
        field_id=result.field_id,
        baseline_state=original.state,
        baseline_value=original.value,
        baseline_evidence_quotes=tuple(item.quote for item in original.evidence),
        proposed_state=result.state,
        proposed_value=result.value,
        proposed_evidence_quotes=tuple(item.quote for item in result.evidence),
        candidate_text=candidate_text,
        product_display_name=preview.product_display_name,
    )
    action = replacement.action
    after = result if action == "replace" else original
    updated = (
        _replace_preview_fields(preview, {result.field_id: result})
        if action == "replace"
        else preview
    )
    return updated, M156FieldRecord(
        field_id=result.field_id,
        display_name=original.display_name,
        batch_index=batch_index,
        provider_call=provider_call,
        phase=phase,
        action=action,
        reason=replacement.reason,
        changed=action == "replace",
        coverage=coverage,
        baseline_audit=(
            asdict(replacement.baseline_audit) if replacement.baseline_audit is not None else None
        ),
        proposed_audit=asdict(replacement.proposed_audit),
        before=_snapshot(original),
        proposed=_snapshot(result),
        after=_snapshot(after),
    )


def _xlsx_rows(path: Path, sheet_name: str) -> tuple[Mapping[str, str], ...]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    office_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{{{main_ns}}}t"))
                for item in root.findall(f"{{{main_ns}}}si")
            ]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relation_id = None
        for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
            if sheet.get("name") == sheet_name:
                relation_id = sheet.get(f"{{{office_ns}}}id")
                break
        if relation_id is None:
            raise ProviderTrialError("M158_FEEDBACK_SHEET_MISSING")
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(
            (
                rel.get("Target")
                for rel in rels.findall(f"{{{package_ns}}}Relationship")
                if rel.get("Id") == relation_id
            ),
            None,
        )
        if not target:
            raise ProviderTrialError("M158_FEEDBACK_SHEET_RELATIONSHIP_MISSING")
        normalized_target = str(PurePosixPath("xl") / target.lstrip("/"))
        if normalized_target.startswith("xl/xl/"):
            normalized_target = normalized_target[3:]
        sheet = ElementTree.fromstring(archive.read(normalized_target))
        matrix: list[dict[int, str]] = []
        for row in sheet.findall(f".//{{{main_ns}}}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{{{main_ns}}}c"):
                reference = cell.get("r", "")
                letters = re.match(r"[A-Z]+", reference)
                if letters is None:
                    continue
                column = 0
                for character in letters.group(0):
                    column = column * 26 + ord(character) - 64
                cell_type = cell.get("t")
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
                else:
                    raw = cell.findtext(f"{{{main_ns}}}v", default="")
                    value = shared[int(raw)] if cell_type == "s" and raw else raw
                values[column] = value
            matrix.append(values)
    if not matrix:
        return ()
    headers = {column: value for column, value in matrix[0].items() if value}
    return tuple(
        {header: row.get(column, "") for column, header in headers.items()}
        for row in matrix[1:]
        if any(row.values())
    )


def load_feedback_issues(path: Path) -> tuple[FeedbackIssue, ...]:
    issues: list[FeedbackIssue] = []
    rows = _xlsx_rows(path, "问题明细归类")
    for workbook_row, row in enumerate(rows, 2):
        field_name = row.get("字段", "").strip()
        if field_name not in _FIELD_NAME_TO_ID:
            continue
        product_name = row.get("产品", "").strip()
        if product_name not in _PRODUCT_NAME_TO_ID:
            raise ProviderTrialError("M158_FEEDBACK_PRODUCT_UNMAPPED")
        try:
            issue_id = int(float(row.get("ID", "")))
        except ValueError as exc:
            raise ProviderTrialError("M158_FEEDBACK_ID_INVALID") from exc
        issues.append(
            FeedbackIssue(
                issue_id=issue_id,
                product_id=_PRODUCT_NAME_TO_ID[product_name],
                field_id=_FIELD_NAME_TO_ID[field_name],
                field_name=field_name,
                problem_label=row.get("标准化问题标签", "").strip(),
                business_note=row.get("人工备注", "").strip(),
                workbook_row=workbook_row,
            )
        )
    if len(issues) != M158_EXPECTED_FEEDBACK_ISSUES:
        raise ProviderTrialError("M158_FEEDBACK_ISSUE_COUNT_DRIFT")
    return tuple(issues)


def run_m158(
    *,
    baseline_path: Path,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
    business_feedback_path: Path | None,
    output_path: Path,
    audit_output_path: Path,
    assessment_output_path: Path,
    completion_factory: Callable[[], OpenAICompatibleCompletion],
    concurrency_profile: ProductConcurrencyProfile,
    product_ids: Sequence[str] = M156_PRODUCT_IDS,
    policy: M158RunPolicy | None = None,
) -> tuple[V5ProviderTrialRun, Mapping[str, Any], Mapping[str, Any]]:
    effective_policy = policy or M158RunPolicy.default()
    outputs = (output_path, audit_output_path, assessment_output_path)
    if any(path.resolve() == baseline_path.resolve() for path in outputs):
        raise ProviderTrialError("M158_BASELINE_OVERWRITE_FORBIDDEN")
    if any(path.exists() for path in outputs):
        raise ProviderTrialError("M158_OUTPUT_ALREADY_EXISTS")
    if _sha256_bytes(baseline_path.read_bytes()) != effective_policy.baseline_file_sha256:
        raise ProviderTrialError("M158_BASELINE_FILE_SHA256_DRIFT")
    selected_product_ids = tuple(dict.fromkeys(product_ids))
    if not selected_product_ids or any(
        product_id not in M156_PRODUCT_IDS for product_id in selected_product_ids
    ):
        raise ProviderTrialError("M158_PRODUCT_SET_INVALID")
    if business_feedback_path is None:
        if len(selected_product_ids) != 1:
            raise ProviderTrialError("M158_BUSINESS_FEEDBACK_REQUIRED")
    elif (
        not business_feedback_path.is_file()
        or _sha256_bytes(business_feedback_path.read_bytes())
        != effective_policy.business_feedback_sha256
    ):
        raise ProviderTrialError("M158_BUSINESS_FEEDBACK_SHA256_DRIFT")
    baseline = load_provider_trial_run(baseline_path)
    if baseline.run_sha256 != effective_policy.baseline_run_sha256:
        raise ProviderTrialError("M158_BASELINE_RUN_SHA256_DRIFT")
    catalog = load_v5_catalog()
    if catalog_sha256(catalog) != effective_policy.catalog_sha256:
        raise ProviderTrialError("M158_CATALOG_SHA256_DRIFT")
    by_id = {product.product_id: product for product in baseline.products}
    if any(product_id not in by_id for product_id in selected_product_ids):
        raise ProviderTrialError("M158_PRODUCT_SET_MISSING")
    products = tuple(by_id[product_id] for product_id in selected_product_ids)
    feedback_issues = (
        tuple(
            issue
            for issue in load_feedback_issues(business_feedback_path)
            if issue.product_id in selected_product_ids
        )
        if business_feedback_path is not None
        else ()
    )
    feedback_sha256 = (
        effective_policy.business_feedback_sha256 if business_feedback_path else None
    )

    timer = RunTimingRecorder()
    with timer.stage("materials_parse"):
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = {
                product.product_version_id: pool.submit(
                    effective_policy.material_loader,
                    product=product,
                    sample_root=sample_root,
                    serious_illness_root=serious_illness_root,
                    supplemental_root_596=supplemental_root_596,
                )
                for product in products
            }
            materials = {version: future.result() for version, future in futures.items()}
    with timer.stage("planning"):
        plans = {
            product.product_version_id: _plan_product_batches(
                product,
                materials[product.product_version_id],
                policy=effective_policy,
            )
            for product in products
        }
        primary_count = sum(len(items) for items in plans.values())
        if primary_count > M158_MAX_CALLS:
            raise ProviderTrialError("M158_PRIMARY_CALL_BUDGET_EXCEEDED")
        if any(len(items) > 12 for items in plans.values()):
            raise ProviderTrialError("M158_PRODUCT_ATTEMPT_LIMIT_EXCEEDED")
    print(
        json.dumps(
            {
                "event": "M158_PLAN_FROZEN",
                "primary_calls": primary_count,
                "max_calls": M158_MAX_CALLS,
                "products": {
                    version: [
                        {
                            "batch": item.batch_index,
                            "kind": item.kind,
                            "fields": item.field_ids,
                            "characters": len(item.context),
                        }
                        for item in items
                    ]
                    for version, items in plans.items()
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    budget = GlobalCallBudget(total_calls=M158_MAX_CALLS, required_primary_calls=primary_count)
    gate = AdaptiveProviderGate(concurrency_profile)

    def execute_product(work: ProductWork[ProviderTrialProduct]) -> M156ProductExecution:
        product = work.payload
        if product.preview is None:
            raise ProviderTrialError("M158_BASELINE_PREVIEW_MISSING")
        material = materials[product.product_version_id]
        preview = product.preview
        completion = completion_factory()
        calls: list[M156CallRecord] = []
        timings: list[ProviderAttemptTiming] = []
        records: list[M156FieldRecord] = []
        long_results: dict[str, list[PluginFieldResult]] = {}
        long_contexts: dict[str, list[str]] = {}
        long_coverages: dict[str, list[Mapping[str, Any]]] = {}
        long_calls: dict[str, list[int]] = {}

        def invoke(batch: M158Batch, *, retry: bool) -> tuple[PluginFieldResult, ...] | None:
            before_receipts = len(completion.receipts)
            outcome = invoke_provider_attempt(
                budget=budget,
                gate=gate,
                product_version_id=product.product_version_id,
                batch_index=batch.batch_index,
                attempt=2 if retry else 1,
                retry=retry,
                call=partial(
                    _execute_batch,
                    product=product,
                    preview=preview,
                    material=material,
                    field_ids=batch.field_ids,
                    context=batch.context,
                    completion=completion,
                    evidence_classifier=classify_m157_evidence,
                    repair_hint=effective_policy.repair_hint_builder(batch),
                ),
            )
            timings.append(outcome.timing)
            receipt = (
                completion.receipts[-1] if len(completion.receipts) > before_receipts else None
            )
            error_code = _typed_error_code(outcome.error) if outcome.error else None
            calls.append(
                M156CallRecord(
                    provider_call=outcome.reservation.provider_call,
                    product_version_id=product.product_version_id,
                    batch_index=batch.batch_index,
                    attempt=outcome.reservation.attempt,
                    kind="provider_retry" if retry else batch.kind,
                    target_field_ids=batch.field_ids,
                    context_sha256=_sha256_text(batch.context),
                    outcome="ERROR" if outcome.error else "ACCEPTED",
                    error_code=error_code,
                    completion=receipt,
                )
            )
            print(
                json.dumps(
                    {
                        "event": "M158_PROVIDER_CALL",
                        "provider_call": outcome.reservation.provider_call,
                        "product_version_id": product.product_version_id,
                        "batch_index": batch.batch_index,
                        "kind": batch.kind,
                        "retry": retry,
                        "outcome": "ERROR" if outcome.error else "ACCEPTED",
                        "error_code": error_code,
                        "duration_ms": outcome.timing.duration_ms,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return outcome.value if outcome.error is None else None

        try:
            for batch in plans[product.product_version_id]:
                results = invoke(batch, retry=False)
                if results is None:
                    try:
                        results = invoke(batch, retry=True)
                    except RetryBudgetUnavailable:
                        results = None
                if batch.kind == "long_field_shard":
                    field_id = batch.field_ids[0]
                    long_contexts.setdefault(field_id, []).append(batch.context)
                    long_coverages.setdefault(field_id, []).append(batch.coverage[field_id])
                    long_calls.setdefault(field_id, []).append(calls[-1].provider_call)
                    if results is not None:
                        admitted, _decision = effective_policy.evidence_admitter(
                            results[0],
                            candidate_text=batch.context,
                            product_display_name=product.product_display_name,
                        )
                        if admitted is not None:
                            long_results.setdefault(field_id, []).append(admitted)
                    continue
                if results is None:
                    results = tuple(
                        _unknown_result(preview, field_id) for field_id in batch.field_ids
                    )
                for result in results:
                    admitted, _decision = effective_policy.evidence_admitter(
                        result,
                        candidate_text=batch.context,
                        product_display_name=product.product_display_name,
                    )
                    proposal = admitted or _unknown_result(preview, result.field_id)
                    preview, record = _field_record(
                        preview=preview,
                        result=proposal,
                        candidate_text=batch.context,
                        coverage=batch.coverage[result.field_id],
                        batch_index=batch.batch_index,
                        provider_call=calls[-1].provider_call,
                        phase="compact_coupled",
                        replacement_selector=effective_policy.replacement_selector,
                    )
                    records.append(record)

            schema = catalog.schema_for(product.insurance_class)
            applicable_long = tuple(
                field.field_id
                for field in schema.fields
                if field.field_id in M158_LONG_FIELD_IDS
                and field.field_id in effective_policy.focus_field_ids
            )
            for field_id in applicable_long:
                admitted_shards = tuple(long_results.get(field_id, ()))
                proposal = (
                    merge_atomic_shard_results(field_id, admitted_shards)
                    if admitted_shards
                    else _unknown_result(preview, field_id)
                )
                candidate_text = "\n\n".join(long_contexts.get(field_id, ()))
                if proposal.state == "present":
                    admitted, _decision = effective_policy.evidence_admitter(
                        proposal,
                        candidate_text=candidate_text,
                        product_display_name=product.product_display_name,
                    )
                    proposal = admitted or _unknown_result(preview, field_id)
                coverage = {
                    "scanned_page_count": material.scanned_page_count,
                    "shard_count": len(long_contexts.get(field_id, ())),
                    "admitted_shard_count": len(admitted_shards),
                    "provider_calls": tuple(long_calls.get(field_id, ())),
                    "shards": tuple(long_coverages.get(field_id, ())),
                }
                preview, record = _field_record(
                    preview=preview,
                    result=proposal,
                    candidate_text=candidate_text,
                    coverage=coverage,
                    batch_index=max(
                        batch.batch_index
                        for batch in plans[product.product_version_id]
                        if batch.field_ids == (field_id,)
                    ),
                    provider_call=max(long_calls.get(field_id, (0,))),
                    phase="long_field_merge",
                    replacement_selector=effective_policy.replacement_selector,
                )
                records.append(record)
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
            works, worker=execute_product, profile=concurrency_profile
        )

    with timer.stage("merge_write"):
        finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        run = seal_provider_trial_run(
            provider=ProviderIdentity(),
            products=tuple(item.product for item in execution.values),
            started_at=timer.started_at,
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
    final_records = {
        (item.product.product_id, record.field_id): record
        for item in execution.values
        for record in item.fields
    }
    metrics = {
        "product_count": len(execution.values),
        "pdf_count": sum(len(item.product.files) for item in execution.values),
        "scanned_page_count": sum(item.material.scanned_page_count for item in execution.values),
        "focus_field_count": len(final_records),
        "changed_field_count": sum(record.changed for record in final_records.values()),
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
    }
    audit_payload: dict[str, Any] = {
        "baseline_file_sha256": effective_policy.baseline_file_sha256,
        "baseline_run_sha256": effective_policy.baseline_run_sha256,
        "result_run_sha256": run.run_sha256,
        "catalog_sha256": effective_policy.catalog_sha256,
        "business_feedback_sha256": feedback_sha256,
        "provider": ProviderIdentity().model_dump(mode="json"),
        "max_calls": M158_MAX_CALLS,
        "planned_primary_calls": primary_count,
        "call_count": budget.used,
        "started_at": timer.started_at,
        "finished_at": finished_at,
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "performance": performance.model_dump(mode="json"),
        "metrics": metrics,
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
                            call.completion.model_dump(mode="json") if call.completion else None
                        ),
                    }
                    for call in item.calls
                ],
                "fields": [asdict(record) for record in item.fields],
            }
            for item in execution.values
        ],
    }
    audit_contract = (
        f"insurance-v5-{effective_policy.artifact_label}-business-quality-audit.v1"
    )
    audit = {
        "contract": audit_contract,
        "artifact_sha256": _canonical_digest(audit_contract, audit_payload),
        **audit_payload,
    }
    _write_json(audit_output_path, audit)

    baseline_fields = {
        (product.product_id, field.field_id): _candidate_field_result(
            product.preview, field.field_id
        )
        for product in products
        if product.preview is not None
        for field in product.preview.fields
    }
    final_fields = {
        (item.product.product_id, field.field_id): _candidate_field_result(
            item.product.preview, field.field_id
        )
        for item in execution.values
        if item.product.preview is not None
        for field in item.product.preview.fields
    }
    assessments = assess_feedback_issues(feedback_issues, final_fields)
    status_counts = Counter(item.status for item in assessments)
    assessment_payload: dict[str, Any] = {
        "baseline_run_sha256": effective_policy.baseline_run_sha256,
        "result_run_sha256": run.run_sha256,
        "business_feedback_sha256": feedback_sha256,
        "feedback_evaluation": "COMPLETE" if business_feedback_path else "NOT_RUN",
        "issue_count": len(assessments),
        "status_counts": dict(sorted(status_counts.items())),
        "issues": [
            {
                **asdict(assessment),
                "before": _snapshot(baseline_fields[(assessment.product_id, assessment.field_id)]),
                "after": _snapshot(final_fields[(assessment.product_id, assessment.field_id)]),
            }
            for assessment in assessments
        ],
    }
    assessment_contract = (
        f"insurance-v5-{effective_policy.artifact_label}-business-feedback-assessment.v1"
    )
    assessment = {
        "contract": assessment_contract,
        "artifact_sha256": _canonical_digest(assessment_contract, assessment_payload),
        **assessment_payload,
    }
    _write_json(assessment_output_path, assessment)
    return run, audit, assessment


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission 158 business seven-field rerun")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--serious-illness-root", type=Path, required=True)
    parser.add_argument("--supplemental-root-596", type=Path, required=True)
    parser.add_argument("--business-feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--assessment-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit("M158_PROVIDER_API_KEY_NOT_CONFIGURED")

    def completion_factory() -> OpenAICompatibleCompletion:
        return OpenAICompatibleCompletion(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model="qwen-plus",
            model_family="qwen",
            timeout_seconds=300.0,
            max_calls=M158_MAX_CALLS,
        )

    started = perf_counter()
    run, audit, assessment = run_m158(
        baseline_path=args.baseline,
        sample_root=args.sample_root,
        serious_illness_root=args.serious_illness_root,
        supplemental_root_596=args.supplemental_root_596,
        business_feedback_path=args.business_feedback,
        output_path=args.output,
        audit_output_path=args.audit_output,
        assessment_output_path=args.assessment_output,
        completion_factory=completion_factory,
        concurrency_profile=ProductConcurrencyProfile(max_products=args.max_product_concurrency),
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_sha256": run.run_sha256,
                "call_count": audit["call_count"],
                "metrics": audit["metrics"],
                "feedback_status_counts": assessment["status_counts"],
                "elapsed_seconds": round(perf_counter() - started, 3),
                "output": str(args.output.resolve()),
                "audit_output": str(args.audit_output.resolve()),
                "assessment_output": str(args.assessment_output.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "M158_BASELINE_FILE_SHA256",
    "M158_BASELINE_RUN_SHA256",
    "M158Batch",
    "M158RunPolicy",
    "load_feedback_issues",
    "run_m158",
]
