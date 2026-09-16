from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Final, Literal, Protocol

from .catalog import catalog_sha256
from .contracts import (
    CandidateField,
    IngestRequest,
    InsuranceSchema,
    PluginResult,
    V5CandidatePreview,
    V5Catalog,
)

_MIN_CLASSIFICATION_CONFIDENCE: Final = 0.80
_DEFAULT_GAP_FIELD_LIMIT: Final = 24
_EVIDENCE_STATUS_RANK: Final = {
    "UNRESOLVED": 1,
    "AMBIGUOUS": 2,
    "NORMALIZED_MATCH": 3,
    "VERIFIED": 4,
}

GapReason = Literal[
    "extracted",
    "source_not_found",
    "source_found_not_extracted",
    "evidence_unverified",
    "not_applicable",
]


class PreviewCompilationError(ValueError):
    """A fail-closed v5 routing or plugin-contract error."""


class V5IngestPlugin(Protocol):
    plugin_id: str

    def extract(self, request: IngestRequest, schema: InsuranceSchema) -> PluginResult: ...


class IngestPluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, V5IngestPlugin] = {}

    def register(self, *, catalog_id: str, plugin: V5IngestPlugin) -> None:
        if catalog_id in self._plugins:
            raise ValueError("V5_INGEST_PLUGIN_ALREADY_REGISTERED")
        self._plugins[catalog_id] = plugin

    def resolve(self, catalog_id: str) -> V5IngestPlugin:
        try:
            return self._plugins[catalog_id]
        except KeyError as exc:
            raise PreviewCompilationError("V5_INGEST_PLUGIN_NOT_REGISTERED") from exc


def _select_insurance_class(request: IngestRequest, catalog: V5Catalog) -> str:
    known = {schema.insurance_class for schema in catalog.schemas}
    reviewed = request.reviewed_insurance_class
    decision = request.classification

    if reviewed is not None:
        if reviewed not in known:
            raise PreviewCompilationError("INSURANCE_CLASS_SELECTION_BLOCKED")
        if decision is not None and decision.insurance_class != reviewed:
            raise PreviewCompilationError("INSURANCE_CLASS_SELECTION_BLOCKED")
        return reviewed

    if (
        decision is None
        or decision.review_state != "accepted"
        or decision.confidence < _MIN_CLASSIFICATION_CONFIDENCE
        or decision.insurance_class not in known
    ):
        raise PreviewCompilationError("INSURANCE_CLASS_SELECTION_BLOCKED")
    return decision.insurance_class


def _validate_plugin_result(
    *, request: IngestRequest, schema: InsuranceSchema, result: PluginResult
) -> None:
    if (
        result.source_revision_id != request.source_revision_id
        or result.insurance_class != schema.insurance_class
        or result.product_id != request.product_id
        or result.product_version_id != request.product_version_id
        or result.schema_id != schema.schema_id
    ):
        raise PreviewCompilationError("PLUGIN_RESULT_IDENTITY_DRIFT")

    expected = tuple((field.ordinal, field.field_id) for field in schema.fields)
    actual = tuple((field.ordinal, field.field_id) for field in result.fields)
    if actual != expected:
        raise PreviewCompilationError("PLUGIN_RESULT_SCHEMA_TOPOLOGY_DRIFT")
    for field in result.fields:
        for evidence in field.evidence:
            if evidence.source_revision_id != request.source_revision_id:
                raise PreviewCompilationError("PLUGIN_RESULT_EVIDENCE_IDENTITY_DRIFT")


def preview_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_preview_digest(preview: V5CandidatePreview) -> None:
    payload = preview.model_dump(mode="json")
    claimed = payload.pop("preview_sha256")
    if preview_digest(payload) != claimed:
        raise PreviewCompilationError("V5_PREVIEW_DIGEST_INVALID")


class V5PreviewCompiler:
    def __init__(self, *, catalog: V5Catalog, registry: IngestPluginRegistry) -> None:
        self._catalog = catalog
        self._registry = registry

    def compile(self, request: IngestRequest) -> V5CandidatePreview:
        if request.catalog_id != self._catalog.catalog_id:
            raise PreviewCompilationError("V5_CATALOG_IDENTITY_DRIFT")
        insurance_class = _select_insurance_class(request, self._catalog)
        schema = self._catalog.schema_for(insurance_class)
        if request.schema_id != schema.schema_id:
            raise PreviewCompilationError("V5_SCHEMA_IDENTITY_DRIFT")

        result = self._registry.resolve(request.catalog_id).extract(request, schema)
        _validate_plugin_result(request=request, schema=schema, result=result)

        candidate_fields = tuple(
            CandidateField(
                ordinal=definition.ordinal,
                category_id=definition.category_id,
                category_display_name=definition.category_display_name,
                field_id=definition.field_id,
                display_name=definition.display_name,
                knowledge_role=definition.knowledge_role,
                formation_modes=definition.formation_modes,
                output_kind=definition.output_kind,
                state=extracted.state,
                value=extracted.value,
                evidence=extracted.evidence,
            )
            for definition, extracted in zip(schema.fields, result.fields, strict=True)
        )
        present_category_ids = {field.category_id for field in candidate_fields}
        categories = tuple(
            category
            for category in self._catalog.categories
            if category.category_id in present_category_ids
        )
        identity_payload: dict[str, object] = {
            "contract": "insurance-v5-candidate-preview.v2",
            "catalog_id": self._catalog.catalog_id,
            "catalog_sha256": catalog_sha256(self._catalog),
            "schema_id": schema.schema_id,
            "source_revision_id": request.source_revision_id,
            "insurance_class": insurance_class,
            "product_id": request.product_id,
            "product_version_id": request.product_version_id,
            "product_display_name": request.product_display_name,
            "serving_effect": "NONE",
            "review_publish_admission": False,
        }
        digest_payload = {
            **identity_payload,
            "categories": [category.model_dump(mode="json") for category in categories],
            "fields": [field.model_dump(mode="json") for field in candidate_fields],
        }
        return V5CandidatePreview.model_validate(
            {
                **identity_payload,
                "categories": categories,
                "fields": candidate_fields,
                "preview_sha256": preview_digest(digest_payload),
            }
        )


def gap_field_ids(
    preview: V5CandidatePreview,
    *,
    max_fields: int = _DEFAULT_GAP_FIELD_LIMIT,
) -> tuple[str, ...]:
    """Return an ordered, bounded list of fields worth a second look."""
    if max_fields < 1:
        raise ValueError("M126_GAP_FIELD_LIMIT_INVALID")
    gaps = [
        field.field_id
        for field in preview.fields
        if field.state == "unknown"
        or any(
            evidence.verification_status != "VERIFIED"
            for evidence in field.evidence
        )
    ]
    return tuple(gaps[:max_fields])


def diagnose_gap_reasons(
    preview: V5CandidatePreview,
    candidate_page_counts: Mapping[str, int],
) -> dict[str, GapReason]:
    """Separate source recall misses from extraction and Evidence failures."""
    reasons: dict[str, GapReason] = {}
    for field in preview.fields:
        if field.state == "absent_explicitly":
            reasons[field.field_id] = "not_applicable"
        elif field.state == "unknown":
            reasons[field.field_id] = (
                "source_found_not_extracted"
                if candidate_page_counts.get(field.field_id, 0) > 0
                else "source_not_found"
            )
        elif any(
            evidence.verification_status not in {"VERIFIED", "NORMALIZED_MATCH"}
            for evidence in field.evidence
        ):
            reasons[field.field_id] = "evidence_unverified"
        else:
            reasons[field.field_id] = "extracted"
    return reasons


def build_gap_repair_hint(
    preview: V5CandidatePreview,
    schema: InsuranceSchema,
    *,
    max_fields: int = _DEFAULT_GAP_FIELD_LIMIT,
) -> str | None:
    """Build a deterministic second-pass instruction without changing the Schema."""
    target_ids = gap_field_ids(preview, max_fields=max_fields)
    if not target_ids:
        return None
    definitions = {field.field_id: field for field in schema.fields}
    targets = [
        {
            "ordinal": definitions[field_id].ordinal,
            "field_id": field_id,
            "label": definitions[field_id].display_name,
            "category": definitions[field_id].category_display_name,
        }
        for field_id in target_ids
    ]
    return (
        "M126_GAP_REPAIR_PASS: re-check only the ordered target fields below against "
        "the source. Return the complete ordered Schema response exactly as requested. "
        "Do not invent values; keep unsupported fields unknown and preserve stronger "
        "existing values when the target cannot be improved. targets="
        + json.dumps(targets, ensure_ascii=False, separators=(",", ":"))
    )


def _field_evidence_quality(field: CandidateField) -> int:
    if not field.evidence:
        return 0
    return max(
        _EVIDENCE_STATUS_RANK[evidence.verification_status]
        for evidence in field.evidence
    )


def _should_take_repair(primary: CandidateField, repair: CandidateField) -> bool:
    if repair.state == "unknown":
        return False
    if primary.state == "unknown":
        return True
    if primary.state == "present" and repair.state == "present":
        # The source short-name rule is candidate generation, not final authority.
        # A verified LLM extraction may replace it after reading the supplied PDFs.
        if primary.field_id == "product_short_name" and repair.value != primary.value:
            return _field_evidence_quality(repair) >= _field_evidence_quality(primary)
        return _field_evidence_quality(repair) > _field_evidence_quality(primary)
    if primary.state == "absent_explicitly" and repair.state == "absent_explicitly":
        return _field_evidence_quality(repair) > _field_evidence_quality(primary)
    return False


def merge_candidate_previews(
    primary: V5CandidatePreview,
    repair: V5CandidatePreview,
    catalog: V5Catalog,
) -> V5CandidatePreview:
    """Merge a repair preview without crossing the primary identity boundary."""
    identity_fields = (
        "catalog_id",
        "catalog_sha256",
        "schema_id",
        "source_revision_id",
        "insurance_class",
        "product_id",
        "product_version_id",
        "product_display_name",
        "serving_effect",
        "review_publish_admission",
    )
    if any(getattr(primary, name) != getattr(repair, name) for name in identity_fields):
        raise PreviewCompilationError("M126_MERGE_IDENTITY_DRIFT")
    if tuple(field.field_id for field in primary.fields) != tuple(
        field.field_id for field in repair.fields
    ):
        raise PreviewCompilationError("M126_MERGE_SCHEMA_TOPOLOGY_DRIFT")

    merged_fields = tuple(
        repair_field if _should_take_repair(primary_field, repair_field) else primary_field
        for primary_field, repair_field in zip(primary.fields, repair.fields, strict=True)
    )
    categories = tuple(
        category
        for category in catalog.categories
        if category.category_id in {field.category_id for field in merged_fields}
    )
    identity_payload: dict[str, object] = {
        "contract": "insurance-v5-candidate-preview.v2",
        "catalog_id": primary.catalog_id,
        "catalog_sha256": primary.catalog_sha256,
        "schema_id": primary.schema_id,
        "source_revision_id": primary.source_revision_id,
        "insurance_class": primary.insurance_class,
        "product_id": primary.product_id,
        "product_version_id": primary.product_version_id,
        "product_display_name": primary.product_display_name,
        "serving_effect": "NONE",
        "review_publish_admission": False,
    }
    digest_payload = {
        **identity_payload,
        "categories": [category.model_dump(mode="json") for category in categories],
        "fields": [field.model_dump(mode="json") for field in merged_fields],
    }
    return V5CandidatePreview.model_validate(
        {
            **identity_payload,
            "categories": categories,
            "fields": merged_fields,
            "preview_sha256": preview_digest(digest_payload),
        }
    )


__all__ = [
    "GapReason",
    "IngestPluginRegistry",
    "PreviewCompilationError",
    "V5IngestPlugin",
    "V5PreviewCompiler",
    "build_gap_repair_hint",
    "diagnose_gap_reasons",
    "gap_field_ids",
    "merge_candidate_previews",
    "preview_digest",
    "validate_preview_digest",
]
