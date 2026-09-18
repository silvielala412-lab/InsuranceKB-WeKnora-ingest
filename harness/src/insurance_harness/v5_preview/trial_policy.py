"""Target selection and validation policy used by the V5 extraction runner."""

from __future__ import annotations

import json
from collections.abc import Collection
from typing import Literal

import httpx

from .catalog import load_v5_catalog
from .contracts import IngestRequest, InsuranceSchema, V5CandidatePreview
from .ingest import IngestPluginRegistry, V5IngestPlugin, V5PreviewCompiler
from .llm_plugin import CompletionReceipt
from .material_loader import PreparedProduct
from .material_support import is_pdf_extractable_field
from .trial_contracts import ProviderAttemptReceipt
from .trial_preparation import M146_SERVICE_FIELD_IDS

M143_SEMANTIC_TARGET_FIELD_IDS: tuple[str, ...] = (
    "premium_grace_period",
    "product_conversion_rules",
    "premium_adjustment_rules",
)
M144_CONTENT_SYNTHESIS_FIELD_IDS: tuple[str, ...] = (
    "product_summary",
    "product_overview",
)


def _attempt_from_completion(
    *,
    attempt: int,
    outcome: Literal["ACCEPTED", "PRESERVED", "REJECTED", "ERROR", "REPAIR_REJECTED"],
    receipt: CompletionReceipt | None,
    error_code: str | None,
) -> ProviderAttemptReceipt:
    return ProviderAttemptReceipt(
        attempt=attempt,
        outcome=outcome,
        response_id=receipt.response_id if receipt else None,
        response_model=receipt.response_model if receipt else None,
        finish_reason=receipt.finish_reason if receipt else None,
        prompt_tokens=receipt.prompt_tokens if receipt else None,
        completion_tokens=receipt.completion_tokens if receipt else None,
        total_tokens=receipt.total_tokens if receipt else None,
        error_code=error_code,
    )


def _error_code(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"PROVIDER_HTTP_{error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return "PROVIDER_NETWORK_ERROR"
    value = str(error).strip()
    is_typed_code = all(character.isalnum() or character == "_" for character in value)
    if value and len(value) <= 120 and is_typed_code:
        return value
    return type(error).__name__.upper()


def _review_error_code(preview: V5CandidatePreview) -> str | None:
    if any(
        evidence.verification_status != "VERIFIED"
        for field in preview.fields
        for evidence in field.evidence
    ):
        return "EVIDENCE_REVIEW_REQUIRED"
    if any(field.state == "unknown" for field in preview.fields):
        return "EXTRACTION_GAP_REVIEW_REQUIRED"
    return None


def _compiler(plugin: V5IngestPlugin) -> V5PreviewCompiler:
    registry = IngestPluginRegistry()
    registry.register(catalog_id="insurance-product-schema-v5", plugin=plugin)
    return V5PreviewCompiler(catalog=load_v5_catalog(), registry=registry)


def _request_for_product(
    prepared: PreparedProduct,
    *,
    source_text: str | None = None,
) -> IngestRequest:
    approved = prepared.approved
    schema = load_v5_catalog().schema_for(approved.insurance_class)
    return IngestRequest(
        source_revision_id=prepared.source_revision_id,
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id=approved.product_id,
        product_version_id=approved.product_version_id,
        product_display_name=approved.product_display_name,
        reviewed_insurance_class=approved.insurance_class,
        source_text=prepared.source_text if source_text is None else source_text,
    )


def _controlled_repair_targets(
    preview: V5CandidatePreview,
    schema: InsuranceSchema,
    *,
    max_fields: int = 24,
    candidate_field_ids: Collection[str] | None = None,
    exclude_field_ids: Collection[str] = (),
    priority_field_ids: Collection[str] = (),
) -> tuple[str, ...]:
    excluded = set(exclude_field_ids)
    priority = set(priority_field_ids)
    eligible = {
        field.field_id
        for field in schema.fields
        if (is_pdf_extractable_field(field) or field.field_id in priority)
        and field.field_id not in excluded
    }
    unknown = [
        field.field_id
        for field in preview.fields
        if field.field_id in eligible and field.state == "unknown"
    ]
    weak_evidence = [
        field.field_id
        for field in preview.fields
        if field.field_id in eligible
        and field.state != "unknown"
        and any(evidence.verification_status != "VERIFIED" for evidence in field.evidence)
    ]
    by_ordinal = {field.field_id: field.ordinal for field in schema.fields}
    if candidate_field_ids is None:
        source_hit_unknown = unknown
        source_miss_unknown: list[str] = []
    else:
        source_hit_unknown = [field_id for field_id in unknown if field_id in candidate_field_ids]
        source_miss_unknown = [
            field_id for field_id in unknown if field_id not in candidate_field_ids
        ]
    forced_unknown = [field_id for field_id in priority_field_ids if field_id in unknown]
    priority_buckets = (
        forced_unknown,
        source_hit_unknown,
        source_miss_unknown,
        weak_evidence,
    )
    ordered: list[str] = []
    for bucket in priority_buckets:
        for field_id in sorted(bucket, key=by_ordinal.__getitem__):
            if field_id not in ordered:
                ordered.append(field_id)
        if len(ordered) >= max_fields:
            break
    selected = ordered[:max_fields]
    return tuple(sorted(selected, key=by_ordinal.__getitem__))


def _content_synthesis_targets(
    preview: V5CandidatePreview,
    schema: InsuranceSchema,
) -> tuple[str, ...]:
    """Return missing pure-LLM content fields for the dedicated synthesis pass."""

    content_ids = set(M144_CONTENT_SYNTHESIS_FIELD_IDS)
    definitions = {field.field_id: field for field in schema.fields}
    return tuple(
        field.field_id
        for field in sorted(preview.fields, key=lambda item: item.ordinal)
        if field.field_id in content_ids
        and field.field_id in definitions
        and set(definitions[field.field_id].formation_modes) == {"LLM生成"}
        and field.state == "unknown"
    )


def _content_synthesis_context(
    preview: V5CandidatePreview,
    *,
    max_characters: int = 40_000,
) -> str:
    """Serialize only verified prior facts for the content synthesis pass."""

    if max_characters < 1_000:
        raise ValueError("M144_SYNTHESIS_CONTEXT_LIMIT_INVALID")
    rows: list[dict[str, object]] = []
    for field in preview.fields:
        if field.state != "present":
            continue
        verified_quotes = [
            evidence.quote
            for evidence in field.evidence
            if evidence.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
        ]
        if not verified_quotes:
            continue
        rows.append(
            {
                "field_id": field.field_id,
                "value": field.value,
                "evidence": verified_quotes[:3],
            }
        )
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))[:max_characters]


def _controlled_repair_hint(
    preview: V5CandidatePreview,
    schema: InsuranceSchema,
    target_field_ids: tuple[str, ...],
) -> str:
    existing = {field.field_id: field for field in preview.fields}
    definitions = {field.field_id: field for field in schema.fields}
    targets = [
        {
            "ordinal": definitions[field_id].ordinal,
            "field_id": field_id,
            "label": definitions[field_id].display_name,
            "prior_state": existing[field_id].state,
            "prior_evidence": [
                evidence.verification_status for evidence in existing[field_id].evidence
            ],
        }
        for field_id in target_field_ids
    ]
    has_full_material_target = any(
        field_id
        in (
            *M143_SEMANTIC_TARGET_FIELD_IDS,
            *M144_CONTENT_SYNTHESIS_FIELD_IDS,
            *M146_SERVICE_FIELD_IDS,
        )
        for field_id in target_field_ids
    )
    semantic_scope = (
        "all ordered material pages" if has_full_material_target else "the supplied candidate pages"
    )
    has_content_target = any(
        field_id in M144_CONTENT_SYNTHESIS_FIELD_IDS for field_id in target_field_ids
    )
    has_service_target = any(field_id in M146_SERVICE_FIELD_IDS for field_id in target_field_ids)
    repair_label = (
        "M146_SERVICE_SUPPLEMENT"
        if has_service_target
        else "M144_CONTENT_SYNTHESIS"
        if has_content_target
        else "M143_TARGETED_REPAIR"
    )
    return (
        f"{repair_label}: re-check only these weak fields against "
        f"{semantic_scope}. Return only the ordered target rows. Do not invent values; "
        "an unsupported target remains unknown. For Content/LLM-generated fields, write "
        "a concise material-grounded synthesis and attach supporting verbatim Evidence; "
        "do not introduce facts outside the pages or prior verified facts. A weaker "
        "result cannot replace the preserved candidate. targets="
        + json.dumps(targets, ensure_ascii=False, separators=(",", ":"))
    )


__all__ = [
    "M143_SEMANTIC_TARGET_FIELD_IDS",
    "M144_CONTENT_SYNTHESIS_FIELD_IDS",
]
