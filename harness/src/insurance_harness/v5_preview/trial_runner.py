"""Provider-call orchestration for the local V5 trial."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .catalog import load_v5_catalog
from .contracts import EvidenceResolution, IngestRequest, V5CandidatePreview
from .dynamic_ingest import (
    MetadataMappingPlugin,
    build_candidate_source_text,
    build_field_micro_batches,
    locate_field_candidates,
)
from .ingest import PreviewCompilationError, merge_candidate_previews
from .llm_plugin import LlmPluginError, OpenAICompatibleCompletion, SchemaGuidedLlmPlugin
from .material_loader import PreparedProduct
from .material_support import is_pdf_extractable_field
from .ocr import BAILIAN_OCR_MODEL, BailianOcrClient
from .source_evidence import SourcePage, classify_evidence
from .source_supported_completion import complete_source_supported_fields
from .source_manifest import APPROVED_PRODUCTS
from .trial_artifacts import (
    seal_provider_trial_run,
    write_ocr_receipt_artifact,
    write_provider_trial_run,
)
from .trial_contracts import (
    MAX_MICROBATCH_PRODUCT_ATTEMPTS,
    MAX_MICROBATCH_PROVIDER_CALLS,
    ProviderAttemptReceipt,
    ProviderIdentity,
    ProviderTrialError,
    ProviderTrialProduct,
    V5ProviderTrialRun,
)
from .trial_policy import (
    M143_SEMANTIC_TARGET_FIELD_IDS,
    M144_CONTENT_SYNTHESIS_FIELD_IDS,
    _attempt_from_completion,
    _compiler,
    _content_synthesis_context,
    _content_synthesis_targets,
    _controlled_repair_hint,
    _controlled_repair_targets,
    _error_code,
    _request_for_product,
    _review_error_code,
)
from .trial_preparation import (
    M146_SERVICE_FIELD_IDS,
    _material_support_for_product,
    build_m146_repair_source_text,
    prepare_approved_products,
)

BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BAILIAN_MODEL = "qwen-plus"
MAX_PROVIDER_CALLS = 18
MAX_PRODUCT_ATTEMPTS = 2


def _run_controlled_product(
    *,
    prepared: PreparedProduct,
    completion: OpenAICompatibleCompletion,
    emit: Callable[[str], None],
    max_product_attempts: int,
) -> ProviderTrialProduct:
    approved = prepared.approved
    typed_catalog = load_v5_catalog()
    schema = typed_catalog.schema_for(approved.insurance_class)
    base_request = _request_for_product(prepared)
    preview = _compiler(
        MetadataMappingPlugin(
            metadata=prepared.metadata,
            source_pages=prepared.pages,
        )
    ).compile(base_request)
    attempts: list[ProviderAttemptReceipt] = []
    terminal_error: str | None = _review_error_code(preview)

    def evidence_resolver(quote: str, advisory_locator: str) -> EvidenceResolution:
        return classify_evidence(prepared.pages, quote, advisory_locator)

    batches = build_field_micro_batches(schema)
    for batch in batches[:max_product_attempts]:
        attempt_number = len(attempts) + 1
        source_text = build_candidate_source_text(
            prepared.pages,
            schema,
            batch.field_ids,
        )
        request = _request_for_product(prepared, source_text=source_text)
        emit(
            f"PROVIDER_GROUP_CALL_START version={approved.product_version_id} "
            f"attempt={attempt_number} categories={','.join(batch.category_ids)} "
            f"fields={len(batch.field_ids)}"
        )
        receipt_count = len(completion.receipts)
        try:
            group_preview = _compiler(
                SchemaGuidedLlmPlugin(
                    completion=completion,
                    evidence_resolver=evidence_resolver,
                    target_field_ids=batch.field_ids,
                )
            ).compile(request)
            preview = merge_candidate_previews(preview, group_preview, typed_catalog)
            terminal_error = _review_error_code(preview)
            receipt = completion.receipts[-1] if len(completion.receipts) > receipt_count else None
            attempts.append(
                _attempt_from_completion(
                    attempt=attempt_number,
                    outcome="PRESERVED" if terminal_error else "ACCEPTED",
                    receipt=receipt,
                    error_code=terminal_error,
                )
            )
            emit(
                f"PROVIDER_GROUP_CALL_PRESERVED version={approved.product_version_id} "
                f"attempt={attempt_number}"
            )
        except (LlmPluginError, PreviewCompilationError, httpx.HTTPError) as exc:
            error_code = _error_code(exc)
            receipt = completion.receipts[-1] if len(completion.receipts) > receipt_count else None
            attempts.append(
                _attempt_from_completion(
                    attempt=attempt_number,
                    outcome="PRESERVED",
                    receipt=receipt,
                    error_code=_review_error_code(preview) or "EXTRACTION_GAP_REVIEW_REQUIRED",
                )
            )
            terminal_error = _review_error_code(preview) or "EXTRACTION_GAP_REVIEW_REQUIRED"
            emit(
                f"PROVIDER_GROUP_CALL_REJECTED version={approved.product_version_id} "
                f"attempt={attempt_number} code={error_code}"
            )

    eligible_field_ids = tuple(
        field.field_id for field in schema.fields if is_pdf_extractable_field(field)
    )
    located_candidates = locate_field_candidates(prepared.pages, schema, eligible_field_ids)
    candidate_field_ids = {
        field_id for field_id, candidates in located_candidates.items() if candidates
    }
    repair_targets = _controlled_repair_targets(
        preview,
        schema,
        candidate_field_ids=candidate_field_ids,
        priority_field_ids=(
            *M143_SEMANTIC_TARGET_FIELD_IDS,
            *_content_synthesis_targets(preview, schema),
        ),
    )
    if repair_targets and len(attempts) < max_product_attempts:
        attempt_number = len(attempts) + 1
        source_text = build_candidate_source_text(
            prepared.pages,
            schema,
            repair_targets,
        )
        request = _request_for_product(prepared, source_text=source_text)
        emit(
            f"PROVIDER_TARGETED_REPAIR_START version={approved.product_version_id} "
            f"attempt={attempt_number} fields={len(repair_targets)}"
        )
        receipt_count = len(completion.receipts)
        try:
            repair_preview = _compiler(
                SchemaGuidedLlmPlugin(
                    completion=completion,
                    evidence_resolver=evidence_resolver,
                    repair_hint=_controlled_repair_hint(preview, schema, repair_targets),
                    target_field_ids=repair_targets,
                    synthesis_context=(
                        _content_synthesis_context(preview)
                        if any(
                            field_id in M144_CONTENT_SYNTHESIS_FIELD_IDS
                            for field_id in repair_targets
                        )
                        else None
                    ),
                )
            ).compile(request)
            preview = merge_candidate_previews(preview, repair_preview, typed_catalog)
            terminal_error = _review_error_code(preview)
            receipt = completion.receipts[-1] if len(completion.receipts) > receipt_count else None
            attempts.append(
                _attempt_from_completion(
                    attempt=attempt_number,
                    outcome="PRESERVED" if terminal_error else "ACCEPTED",
                    receipt=receipt,
                    error_code=terminal_error,
                )
            )
            emit(
                f"PROVIDER_TARGETED_REPAIR_PRESERVED version={approved.product_version_id} "
                f"attempt={attempt_number}"
            )
        except (LlmPluginError, PreviewCompilationError, httpx.HTTPError) as exc:
            receipt = completion.receipts[-1] if len(completion.receipts) > receipt_count else None
            attempts.append(
                _attempt_from_completion(
                    attempt=attempt_number,
                    outcome="REPAIR_REJECTED",
                    receipt=receipt,
                    error_code=_error_code(exc),
                )
            )
            terminal_error = _review_error_code(preview) or "EXTRACTION_GAP_REVIEW_REQUIRED"
            emit(
                f"PROVIDER_TARGETED_REPAIR_REJECTED version={approved.product_version_id} "
                f"attempt={attempt_number} code={_error_code(exc)}"
            )

    terminal_error = _review_error_code(preview)
    preview, completion_receipts = complete_source_supported_fields(
        preview=preview,
        source_manifest_sha256=prepared.source_manifest_sha256,
        pages=prepared.pages,
    )
    if completion_receipts:
        emit(
            f"SOURCE_SUPPORTED_COMPLETION version={approved.product_version_id} "
            f"fields={len(completion_receipts)}"
        )
    terminal_error = _review_error_code(preview)
    review_required = terminal_error is not None
    material_support, material_support_metrics = _material_support_for_product(
        prepared=prepared,
        schema=schema,
        preview=preview,
    )
    return ProviderTrialProduct(
        product_id=approved.product_id,
        product_version_id=approved.product_version_id,
        product_display_name=approved.product_display_name,
        insurance_class=approved.insurance_class,
        schema_id=schema.schema_id,
        source_revision_id=prepared.source_revision_id,
        source_manifest_sha256=prepared.source_manifest_sha256,
        status="REVIEW_REQUIRED" if review_required else "SUCCESS",
        error_code=terminal_error,
        files=prepared.files,
        attempts=tuple(attempts),
        preview=preview,
        material_support=material_support,
        material_support_metrics=material_support_metrics,
    )


def run_provider_trial(
    *,
    source_root: Path,
    output_path: Path,
    api_key: str,
    progress: Callable[[str], None] | None = None,
    max_provider_calls: int = MAX_PROVIDER_CALLS,
    max_product_attempts: int = MAX_PRODUCT_ATTEMPTS,
    adaptive: bool = True,
    controlled_dynamic: bool = False,
    product_ids: Sequence[str] | None = None,
    supplemental_root_596: Path | None = None,
    ocr_output_path: Path | None = None,
) -> V5ProviderTrialRun:
    max_calls_limit = MAX_MICROBATCH_PROVIDER_CALLS if controlled_dynamic else MAX_PROVIDER_CALLS
    max_attempts_limit = (
        MAX_MICROBATCH_PRODUCT_ATTEMPTS if controlled_dynamic else MAX_PRODUCT_ATTEMPTS
    )
    if not 1 <= max_provider_calls <= max_calls_limit:
        raise ProviderTrialError("V5_PROVIDER_CALL_BUDGET_INVALID")
    if not 1 <= max_product_attempts <= max_attempts_limit:
        raise ProviderTrialError("V5_PRODUCT_ATTEMPT_BUDGET_INVALID")
    if controlled_dynamic and (max_provider_calls < 27 or max_product_attempts < 10):
        raise ProviderTrialError("M127_CONTROLLED_BUDGET_INVALID")
    emit = progress or (lambda _: None)
    selected_products = APPROVED_PRODUCTS
    if product_ids is not None:
        requested = tuple(product_ids)
        if not requested or len(set(requested)) != len(requested):
            raise ProviderTrialError("V5_APPROVED_PRODUCT_SET_INVALID")
        selected_by_id = {item.product_id: item for item in APPROVED_PRODUCTS}
        try:
            selected_products = tuple(selected_by_id[product_id] for product_id in requested)
        except KeyError as exc:
            raise ProviderTrialError("V5_APPROVED_PRODUCT_SET_INVALID") from exc
    ocr_client = (
        BailianOcrClient(
            base_url=BAILIAN_BASE_URL,
            api_key=api_key,
            max_calls=2,
        )
        if supplemental_root_596 is not None
        else None
    )
    try:
        prepared_products = prepare_approved_products(
            source_root,
            approved_products=selected_products,
            supplemental_root_596=supplemental_root_596,
            ocr_page_reader=(ocr_client.extract_pdf_page if ocr_client is not None else None),
        )
        if ocr_client is not None:
            if ocr_output_path is None:
                raise ProviderTrialError("M146_OCR_OUTPUT_PATH_REQUIRED")
            write_ocr_receipt_artifact(ocr_output_path, ocr_client.receipts)
            emit(
                "OCR_RECEIPTS_WRITTEN "
                f"model={BAILIAN_OCR_MODEL} calls={ocr_client.call_count} "
                f"output={ocr_output_path}"
            )
    finally:
        if ocr_client is not None:
            ocr_client.close()
    emit(
        "SOURCE_MANIFESTS_VALID "
        f"products={len(prepared_products)} "
        f"pdfs={sum(len(product.files) for product in prepared_products)}"
    )
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    catalog = load_v5_catalog()
    completion = OpenAICompatibleCompletion(
        base_url=BAILIAN_BASE_URL,
        api_key=api_key,
        model=BAILIAN_MODEL,
        model_family="qwen",
        timeout_seconds=300.0,
        max_calls=max_provider_calls,
    )
    product_results: list[ProviderTrialProduct] = []
    try:
        for prepared in prepared_products:
            if controlled_dynamic:
                product_results.append(
                    _run_controlled_product(
                        prepared=prepared,
                        completion=completion,
                        emit=emit,
                        max_product_attempts=max_product_attempts,
                    )
                )
                continue
            approved = prepared.approved
            schema = catalog.schema_for(approved.insurance_class)
            request = IngestRequest(
                source_revision_id=prepared.source_revision_id,
                catalog_id="insurance-product-schema-v5",
                schema_id=schema.schema_id,
                product_id=approved.product_id,
                product_version_id=approved.product_version_id,
                product_display_name=approved.product_display_name,
                reviewed_insurance_class=approved.insurance_class,
                source_text=prepared.source_text,
            )
            attempts: list[ProviderAttemptReceipt] = []
            metadata_preview = _compiler(
                MetadataMappingPlugin(
                    metadata=prepared.metadata,
                    source_pages=prepared.pages,
                )
            ).compile(request)
            # Metadata is only a merge base. A provider/network failure must not
            # turn that base into a successful extraction preview.
            preview: V5CandidatePreview | None = None
            review_required = False
            terminal_error: str | None = None
            repair_hint: str | None = None
            primary_preview: V5CandidatePreview | None = None
            repair_target_ids: tuple[str, ...] = ()
            eligible_field_ids = tuple(
                field.field_id for field in schema.fields if is_pdf_extractable_field(field)
            )
            located_candidates = locate_field_candidates(prepared.pages, schema, eligible_field_ids)
            candidate_field_ids = {
                field_id for field_id, candidates in located_candidates.items() if candidates
            }
            for attempt_number in range(1, max_product_attempts + 1):
                emit(
                    f"PROVIDER_CALL_START version={approved.product_version_id} "
                    f"attempt={attempt_number}"
                )
                receipt_count = len(completion.receipts)

                def evidence_resolver(
                    quote: str,
                    advisory_locator: str,
                    pages: tuple[SourcePage, ...] = prepared.pages,
                ) -> EvidenceResolution:
                    return classify_evidence(pages, quote, advisory_locator)

                target_field_ids = repair_target_ids or None
                attempt_source_text = (
                    build_m146_repair_source_text(
                        base_pages=prepared.base_pages,
                        supplemental_pages=prepared.supplemental_pages,
                        schema=schema,
                        target_field_ids=repair_target_ids,
                    )
                    if repair_target_ids and prepared.supplemental_pages
                    else build_candidate_source_text(
                        prepared.pages,
                        schema,
                        repair_target_ids,
                        max_pages=24,
                        max_characters=100_000,
                    )
                    if repair_target_ids
                    else prepared.source_text
                )
                request = _request_for_product(prepared, source_text=attempt_source_text)
                plugin = SchemaGuidedLlmPlugin(
                    completion=completion,
                    evidence_resolver=evidence_resolver,
                    repair_hint=repair_hint,
                    target_field_ids=target_field_ids,
                    synthesis_context=(
                        _content_synthesis_context(preview or metadata_preview)
                        if any(
                            field_id in M144_CONTENT_SYNTHESIS_FIELD_IDS
                            for field_id in repair_target_ids
                        )
                        else None
                    ),
                )
                try:
                    candidate_preview = _compiler(plugin).compile(request)
                    candidate_preview = merge_candidate_previews(
                        preview or metadata_preview,
                        candidate_preview,
                        catalog,
                    )
                    if primary_preview is not None:
                        candidate_preview = merge_candidate_previews(
                            primary_preview,
                            candidate_preview,
                            catalog,
                        )
                    preview = candidate_preview
                    terminal_error = _review_error_code(preview)
                    review_required = terminal_error is not None
                    receipt = (
                        completion.receipts[-1]
                        if len(completion.receipts) > receipt_count
                        else None
                    )
                    attempts.append(
                        _attempt_from_completion(
                            attempt=attempt_number,
                            outcome="PRESERVED" if review_required else "ACCEPTED",
                            receipt=receipt,
                            error_code=terminal_error,
                        )
                    )
                    if (
                        adaptive
                        and primary_preview is None
                        and attempt_number == 1
                        and max_product_attempts > 1
                    ):
                        next_targets = _controlled_repair_targets(
                            preview,
                            schema,
                            max_fields=12 if prepared.supplemental_pages else 24,
                            candidate_field_ids=candidate_field_ids,
                            priority_field_ids=(
                                *M143_SEMANTIC_TARGET_FIELD_IDS,
                                *_content_synthesis_targets(preview, schema),
                                *(M146_SERVICE_FIELD_IDS if prepared.supplemental_pages else ()),
                            ),
                        )
                        next_hint = (
                            _controlled_repair_hint(preview, schema, next_targets)
                            if next_targets
                            else None
                        )
                        if next_hint is not None:
                            primary_preview = preview
                            repair_target_ids = next_targets
                            repair_hint = next_hint
                            emit(
                                "PROVIDER_GAP_REPAIR_SCHEDULED "
                                f"version={approved.product_version_id} "
                                f"attempt={attempt_number}"
                            )
                            continue
                    emit(
                        f"PROVIDER_CALL_{'PRESERVED' if review_required else 'ACCEPTED'} "
                        f"version={approved.product_version_id} attempt={attempt_number}"
                    )
                    break
                except (LlmPluginError, PreviewCompilationError, httpx.HTTPError) as exc:
                    terminal_error = _error_code(exc)
                    receipt = (
                        completion.receipts[-1]
                        if len(completion.receipts) > receipt_count
                        else None
                    )
                    if primary_preview is not None:
                        preview = primary_preview
                        review_required = True
                        terminal_error = _review_error_code(primary_preview)
                        if terminal_error is None:
                            terminal_error = "EXTRACTION_GAP_REVIEW_REQUIRED"
                        attempts.append(
                            _attempt_from_completion(
                                attempt=attempt_number,
                                outcome="REPAIR_REJECTED",
                                receipt=receipt,
                                error_code=_error_code(exc),
                            )
                        )
                        emit(
                            f"PROVIDER_GAP_REPAIR_REJECTED version={approved.product_version_id} "
                            f"attempt={attempt_number} code={_error_code(exc)}"
                        )
                        break
                    attempts.append(
                        _attempt_from_completion(
                            attempt=attempt_number,
                            outcome="REJECTED" if receipt else "ERROR",
                            receipt=receipt,
                            error_code=terminal_error,
                        )
                    )
                    emit(
                        f"PROVIDER_CALL_REJECTED version={approved.product_version_id} "
                        f"attempt={attempt_number} code={terminal_error}"
                    )
                    repair_hint = (
                        f"前次输出被系统拒绝，错误码 {terminal_error}。重新逐项核对完整字段顺序、"
                        "三态和值，并为非 unknown 字段选择只在一个页面出现的逐字唯一引文。"
                    )
            if preview is not None and not any(
                attempt.outcome in {"ACCEPTED", "PRESERVED", "REPAIR_REJECTED"}
                for attempt in attempts
            ):
                # The metadata mapping is a merge base only. Keep provider
                # failures explicit instead of exposing a partial preview.
                preview = None
            if preview is not None:
                preview, completion_receipts = complete_source_supported_fields(
                    preview=preview,
                    source_manifest_sha256=prepared.source_manifest_sha256,
                    pages=prepared.pages,
                )
                if completion_receipts:
                    emit(
                        f"SOURCE_SUPPORTED_COMPLETION version={approved.product_version_id} "
                        f"fields={len(completion_receipts)}"
                    )
                terminal_error = _review_error_code(preview)
                review_required = terminal_error is not None
            material_support, material_support_metrics = _material_support_for_product(
                prepared=prepared,
                schema=schema,
                preview=preview,
            )
            product_results.append(
                ProviderTrialProduct(
                    product_id=approved.product_id,
                    product_version_id=approved.product_version_id,
                    product_display_name=approved.product_display_name,
                    insurance_class=approved.insurance_class,
                    schema_id=schema.schema_id,
                    source_revision_id=prepared.source_revision_id,
                    source_manifest_sha256=prepared.source_manifest_sha256,
                    status=(
                        "REVIEW_REQUIRED"
                        if preview is not None and review_required
                        else "SUCCESS"
                        if preview is not None
                        else "FAILED"
                    ),
                    error_code=terminal_error,
                    files=prepared.files,
                    attempts=tuple(attempts),
                    preview=preview,
                    material_support=material_support,
                    material_support_metrics=material_support_metrics,
                )
            )
    finally:
        completion.close()
    finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    run = seal_provider_trial_run(
        provider=ProviderIdentity(),
        products=tuple(product_results),
        started_at=started_at,
        finished_at=finished_at,
    )
    write_provider_trial_run(output_path, run)
    return run
