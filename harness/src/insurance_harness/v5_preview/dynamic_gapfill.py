from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from threading import Lock
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .catalog import catalog_sha256
from .contracts import (
    CandidateEvidence,
    CandidateField,
    CandidateValue,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
    TriState,
    V5CandidatePreview,
    V5Catalog,
)
from .dynamic_ingest import (
    FieldCandidate,
    FieldCandidateRetriever,
    distributed_page_excerpt,
    locate_field_candidates,
)
from .ingest import preview_digest
from .llm_plugin import CompletionPort, SchemaGuidedLlmPlugin
from .source_evidence import SourcePage, classify_evidence

DynamicAction = Literal["gapfill", "review"]
DynamicScope = Literal["matched_snippets", "adjacent_pages", "all_material"]
StageOutcome = Literal[
    "NO_CANDIDATE",
    "NO_IMPROVEMENT",
    "IMPROVED",
    "CONFIRMED",
    "CONFLICT",
]
FieldOutcome = Literal[
    "FILLED",
    "CONFIRMED",
    "CONFLICT",
    "STILL_UNKNOWN",
    "UNCHANGED",
]
OperationStatus = Literal["IMPROVED", "CONFIRMED", "NEEDS_REVIEW", "NO_CHANGE"]

_SCOPES: tuple[DynamicScope, ...] = (
    "matched_snippets",
    "adjacent_pages",
    "all_material",
)
_EVIDENCE_RANK = {
    "UNRESOLVED": 1,
    "AMBIGUOUS": 2,
    "NORMALIZED_MATCH": 3,
    "VERIFIED": 4,
}


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DynamicFieldGapfillRequest(_ClosedModel):
    contract: Literal["insurance-v5-dynamic-field-gapfill-request.v1"]
    product_version_id: Annotated[str, Field(min_length=1)]
    preview_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    action: DynamicAction
    field_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]

    @field_validator("field_ids", mode="before")
    @classmethod
    def freeze_json_field_ids(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_field_ids(self) -> Self:
        if len(set(self.field_ids)) != len(self.field_ids) or any(
            not field_id or not field_id.replace("_", "a").isalnum()
            for field_id in self.field_ids
        ):
            raise ValueError("M148_FIELD_SET_INVALID")
        return self


class DynamicMaterialPage(_ClosedModel):
    document_name: Annotated[str, Field(min_length=1)]
    document_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_number: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1)]

    @property
    def locator(self) -> str:
        return f"pdf:{self.document_name}#page={self.page_number}"


class DynamicMaterialBundle(_ClosedModel):
    product_version_id: Annotated[str, Field(min_length=1)]
    source_revision_id: Annotated[str, Field(min_length=1)]
    pages: Annotated[tuple[DynamicMaterialPage, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_pages(self) -> Self:
        identities = [(page.document_name, page.page_number) for page in self.pages]
        if len(set(identities)) != len(identities):
            raise ValueError("M148_MATERIAL_PAGE_IDENTITY_DUPLICATED")
        return self


class DynamicFieldSnapshot(_ClosedModel):
    state: TriState
    value: CandidateValue | None
    evidence: tuple[CandidateEvidence, ...]

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state == "present" and (self.value is None or not self.evidence):
            raise ValueError("present snapshot requires value and Evidence")
        if self.state == "absent_explicitly" and (
            self.value is not None or not self.evidence
        ):
            raise ValueError("absent snapshot requires Evidence and no value")
        if self.state == "unknown" and (self.value is not None or self.evidence):
            raise ValueError("unknown snapshot cannot contain value or Evidence")
        return self


class DynamicStageReceipt(_ClosedModel):
    scope: DynamicScope
    scanned_page_count: Annotated[int, Field(ge=1)]
    selected_page_count: Annotated[int, Field(ge=0)]
    context_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    outcome: StageOutcome


class DynamicFieldDiff(_ClosedModel):
    field_id: Annotated[str, Field(min_length=1)]
    status: FieldOutcome
    scope_used: DynamicScope | None
    changed: bool
    before: DynamicFieldSnapshot
    proposed: DynamicFieldSnapshot | None
    after: DynamicFieldSnapshot


class DynamicFieldGapfillResponse(_ClosedModel):
    contract: Literal["insurance-v5-dynamic-field-gapfill-response.v1"]
    operation_id: Annotated[str, Field(min_length=1)]
    action: DynamicAction
    status: OperationStatus
    product_version_id: Annotated[str, Field(min_length=1)]
    base_preview_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    serving_effect: Literal["NONE"]
    review_publish_admission: Literal[False]
    call_count: Annotated[int, Field(ge=0, le=3)]
    stages: Annotated[tuple[DynamicStageReceipt, ...], Field(min_length=1, max_length=3)]
    fields: Annotated[tuple[DynamicFieldDiff, ...], Field(min_length=1, max_length=8)]
    candidate_preview: V5CandidatePreview


class DynamicMaterialRepository(Protocol):
    def get(self, product_version_id: str) -> DynamicMaterialBundle: ...


class DynamicFieldExecutor(Protocol):
    def extract(
        self,
        *,
        preview: V5CandidatePreview,
        field_ids: tuple[str, ...],
        source_text: str,
        scope: DynamicScope,
        action: DynamicAction,
        pages: tuple[DynamicMaterialPage, ...],
    ) -> tuple[PluginFieldResult, ...]: ...


class InMemoryDynamicMaterialRepository:
    def __init__(self, bundles: Sequence[DynamicMaterialBundle]) -> None:
        self._bundles = {bundle.product_version_id: bundle for bundle in bundles}
        if len(self._bundles) != len(bundles):
            raise ValueError("M148_MATERIAL_PRODUCT_IDENTITY_DUPLICATED")

    def get(self, product_version_id: str) -> DynamicMaterialBundle:
        try:
            return self._bundles[product_version_id]
        except KeyError as exc:
            raise ValueError("M148_MATERIAL_NOT_CONFIGURED") from exc


class SchemaGuidedDynamicFieldExecutor:
    """Adapter for the existing schema-guided plugin; it owns Evidence resolution."""

    def __init__(self, *, catalog: V5Catalog, completion: CompletionPort) -> None:
        self._catalog = catalog
        self._completion = completion

    def extract(
        self,
        *,
        preview: V5CandidatePreview,
        field_ids: tuple[str, ...],
        source_text: str,
        scope: DynamicScope,
        action: DynamicAction,
        pages: tuple[DynamicMaterialPage, ...],
    ) -> tuple[PluginFieldResult, ...]:
        request = IngestRequest(
            source_revision_id=preview.source_revision_id,
            catalog_id=preview.catalog_id,
            schema_id=preview.schema_id,
            product_id=preview.product_id,
            product_version_id=preview.product_version_id,
            product_display_name=preview.product_display_name,
            reviewed_insurance_class=preview.insurance_class,
            source_text=source_text,
        )
        schema = self._catalog.schema_for(preview.insurance_class)
        evidence_pages = tuple(
            SourcePage(
                document_name=page.document_name,
                document_sha256=page.document_sha256,
                page_number=page.page_number,
                text=page.text,
            )
            for page in pages
        )
        hint = (
            f"M148_{action.upper()}: evaluate only the ordered target fields using the "
            f"{scope} context. Unsupported fields remain unknown. Return verbatim Evidence."
        )
        result = SchemaGuidedLlmPlugin(
            completion=self._completion,
            evidence_resolver=lambda quote, locator: classify_evidence(
                evidence_pages, quote, locator
            ),
            repair_hint=hint,
            target_field_ids=field_ids,
        ).extract(request, schema)
        requested = set(field_ids)
        return tuple(field for field in result.fields if field.field_id in requested)


class _ContextPlan(_ClosedModel):
    scope: DynamicScope
    text: str
    scanned_page_count: Annotated[int, Field(ge=1)]
    selected_page_count: Annotated[int, Field(ge=0)]
    context_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized(value: object) -> object:
    if isinstance(value, str):
        return "".join(
            character.lower()
            for character in unicodedata.normalize("NFKC", value)
            if not character.isspace()
        )
    if isinstance(value, tuple):
        return tuple(_normalized(item) for item in value)
    return value


def _snapshot(field: CandidateField | PluginFieldResult) -> DynamicFieldSnapshot:
    return DynamicFieldSnapshot(
        state=field.state,
        value=field.value,
        evidence=field.evidence,
    )


def _evidence_quality(field: PluginFieldResult | CandidateField) -> int:
    return max(
        (_EVIDENCE_RANK[evidence.verification_status] for evidence in field.evidence),
        default=0,
    )


def _same_value(
    left: CandidateField | PluginFieldResult,
    right: CandidateField | PluginFieldResult,
) -> bool:
    return left.state == right.state and _normalized(left.value) == _normalized(right.value)


def _page_excerpt(
    page: DynamicMaterialPage,
    *,
    candidates: Sequence[FieldCandidate],
    max_characters: int,
) -> str:
    if len(page.text) <= max_characters:
        return page.text
    positioned = [
        candidate
        for candidate in candidates
        if 0 <= candidate.start_offset < candidate.end_offset <= len(page.text)
    ]
    if positioned:
        best = max(positioned, key=lambda candidate: candidate.score)
        center = (best.start_offset + best.end_offset) // 2
    else:
        keywords = [
            keyword for candidate in candidates for keyword in candidate.matched_keywords
        ]
        offsets = [
            page.text.find(keyword)
            for keyword in keywords
            if page.text.find(keyword) >= 0
        ]
        if not offsets:
            return distributed_page_excerpt(page.text, max_characters=max_characters)
        center = min(offsets)
    start = max(0, center - max_characters // 3)
    return page.text[start : start + max_characters]


def _render_context(
    pages: Sequence[DynamicMaterialPage],
    *,
    scope: DynamicScope,
    candidates_by_page: Mapping[tuple[str, int], Sequence[FieldCandidate]],
    max_characters: int = 100_000,
) -> str:
    if not pages:
        return ""
    marker_size = sum(
        len(f"【文档：{page.document_name}｜页码：{page.page_number}】\n")
        for page in pages
    )
    page_budget = max(120, (max_characters - marker_size) // len(pages))
    parts: list[str] = []
    for page in pages:
        key = (page.document_name, page.page_number)
        text = _page_excerpt(
            page,
            candidates=candidates_by_page.get(key, ()),
            max_characters=page_budget,
        )
        parts.append(f"【文档：{page.document_name}｜页码：{page.page_number}】\n{text}")
    prefix = f"【M148 动态范围：{scope}】\n"
    return (prefix + "\n\n".join(parts))[:max_characters]


def _context_plan(
    pages: tuple[DynamicMaterialPage, ...],
    schema: InsuranceSchema,
    field_ids: tuple[str, ...],
    scope: DynamicScope,
    retriever: FieldCandidateRetriever | None = None,
) -> _ContextPlan:
    located = locate_field_candidates(
        pages,
        schema,
        field_ids,
        retriever=retriever,
    )
    candidates_by_page: dict[tuple[str, int], list[FieldCandidate]] = {}
    for candidates in located.values():
        for candidate in candidates:
            candidates_by_page.setdefault(
                (candidate.document_name, candidate.page_number), []
            ).append(candidate)
    candidate_keys = set(candidates_by_page)
    if scope == "matched_snippets":
        selected = tuple(
            page
            for page in pages
            if (page.document_name, page.page_number) in candidate_keys
        )[:12]
    elif scope == "adjacent_pages":
        adjacent_keys: set[tuple[str, int]] = set()
        for document_name, page_number in candidate_keys:
            adjacent_keys.update(
                (document_name, candidate_page)
                for candidate_page in range(max(1, page_number - 1), page_number + 2)
            )
        selected = tuple(
            page
            for page in pages
            if (page.document_name, page.page_number) in adjacent_keys
        )[:24]
    else:
        selected = pages
    text = _render_context(
        selected,
        scope=scope,
        candidates_by_page=candidates_by_page,
    )
    return _ContextPlan(
        scope=scope,
        text=text,
        scanned_page_count=len(pages),
        selected_page_count=len(selected),
        context_sha256=_canonical_sha256(
            {
                "scope": scope,
                "field_ids": field_ids,
                "selected": [page.locator for page in selected],
                "text": text,
            }
        ),
    )


def _replace_preview_fields(
    preview: V5CandidatePreview,
    updates: Mapping[str, PluginFieldResult],
) -> V5CandidatePreview:
    fields = tuple(
        field.model_copy(
            update={
                "state": update.state,
                "value": update.value,
                "evidence": update.evidence,
            }
        )
        if (update := updates.get(field.field_id)) is not None
        else field
        for field in preview.fields
    )
    digest_payload = preview.model_dump(mode="json")
    digest_payload.pop("preview_sha256")
    digest_payload["fields"] = [field.model_dump(mode="json") for field in fields]
    return V5CandidatePreview(
        contract=preview.contract,
        catalog_id=preview.catalog_id,
        catalog_sha256=preview.catalog_sha256,
        schema_id=preview.schema_id,
        source_revision_id=preview.source_revision_id,
        insurance_class=preview.insurance_class,
        product_id=preview.product_id,
        product_version_id=preview.product_version_id,
        product_display_name=preview.product_display_name,
        serving_effect="NONE",
        review_publish_admission=False,
        categories=preview.categories,
        fields=fields,
        preview_sha256=preview_digest(digest_payload),
    )


def _stage_outcome(outcomes: Sequence[StageOutcome]) -> StageOutcome:
    priority: tuple[StageOutcome, ...] = ("CONFLICT", "IMPROVED", "CONFIRMED")
    for candidate in priority:
        if candidate in outcomes:
            return candidate
    return "NO_IMPROVEMENT"


class DynamicFieldGapfillService:
    def __init__(
        self,
        *,
        catalog: V5Catalog,
        previews: Mapping[str, V5CandidatePreview],
        materials: DynamicMaterialRepository,
        executor: DynamicFieldExecutor,
        retriever: FieldCandidateRetriever | None = None,
    ) -> None:
        self._catalog = catalog
        self._previews = dict(previews)
        self._materials = materials
        self._executor = executor
        self._retriever = retriever
        self._lock = Lock()

    def _validate_request(
        self, request: DynamicFieldGapfillRequest
    ) -> tuple[V5CandidatePreview, InsuranceSchema, DynamicMaterialBundle]:
        try:
            preview = self._previews[request.product_version_id]
        except KeyError as exc:
            raise ValueError("M148_PREVIEW_NOT_CONFIGURED") from exc
        if preview.preview_sha256 != request.preview_sha256:
            raise ValueError("M148_PREVIEW_IDENTITY_DRIFT")
        if preview.catalog_sha256 != catalog_sha256(self._catalog):
            raise ValueError("M148_CATALOG_IDENTITY_DRIFT")
        schema = self._catalog.schema_for(preview.insurance_class)
        if preview.schema_id != schema.schema_id:
            raise ValueError("M148_SCHEMA_IDENTITY_DRIFT")
        by_id = {field.field_id: field for field in preview.fields}
        if any(field_id not in by_id for field_id in request.field_ids):
            raise ValueError("M148_FIELD_SET_INVALID")
        target_states = tuple(by_id[field_id].state for field_id in request.field_ids)
        if request.action == "gapfill" and any(state != "unknown" for state in target_states):
            raise ValueError("M148_GAPFILL_REQUIRES_UNKNOWN")
        if request.action == "review" and any(state == "unknown" for state in target_states):
            raise ValueError("M148_REVIEW_REQUIRES_RESOLVED")
        bundle = self._materials.get(request.product_version_id)
        if (
            bundle.product_version_id != preview.product_version_id
            or bundle.source_revision_id != preview.source_revision_id
        ):
            raise ValueError("M148_MATERIAL_IDENTITY_DRIFT")
        return preview, schema, bundle

    def _validate_results(
        self,
        preview: V5CandidatePreview,
        field_ids: tuple[str, ...],
        results: tuple[PluginFieldResult, ...],
    ) -> None:
        by_id = {field.field_id: field for field in preview.fields}
        if tuple(result.field_id for result in results) != field_ids:
            raise ValueError("M148_EXECUTOR_FIELD_TOPOLOGY_DRIFT")
        if any(result.ordinal != by_id[result.field_id].ordinal for result in results):
            raise ValueError("M148_EXECUTOR_FIELD_TOPOLOGY_DRIFT")
        if any(
            evidence.source_revision_id != preview.source_revision_id
            for result in results
            for evidence in result.evidence
        ):
            raise ValueError("M148_EXECUTOR_EVIDENCE_IDENTITY_DRIFT")

    def run(self, request: DynamicFieldGapfillRequest) -> DynamicFieldGapfillResponse:
        with self._lock:
            return self._run_once(request)

    def _run_once(
        self, request: DynamicFieldGapfillRequest
    ) -> DynamicFieldGapfillResponse:
        preview, schema, bundle = self._validate_request(request)
        before = {
            field.field_id: field
            for field in preview.fields
            if field.field_id in request.field_ids
        }
        active = list(request.field_ids)
        proposals: dict[str, PluginFieldResult] = {}
        proposal_scopes: dict[str, DynamicScope] = {}
        conflicts: dict[str, PluginFieldResult] = {}
        stage_receipts: list[DynamicStageReceipt] = []
        call_count = 0

        for scope in _SCOPES:
            if not active:
                break
            ordered_active = tuple(field_id for field_id in request.field_ids if field_id in active)
            plan = _context_plan(
                bundle.pages,
                schema,
                ordered_active,
                scope,
                retriever=self._retriever,
            )
            if not plan.text:
                stage_receipts.append(
                    DynamicStageReceipt(
                        scope=scope,
                        scanned_page_count=plan.scanned_page_count,
                        selected_page_count=0,
                        context_sha256=plan.context_sha256,
                        outcome="NO_CANDIDATE",
                    )
                )
                continue
            results = self._executor.extract(
                preview=preview,
                field_ids=ordered_active,
                source_text=plan.text,
                scope=scope,
                action=request.action,
                pages=bundle.pages,
            )
            call_count += 1
            self._validate_results(preview, ordered_active, results)
            outcomes: list[StageOutcome] = []
            for result in results:
                if result.state == "unknown":
                    outcomes.append("NO_IMPROVEMENT")
                    continue
                original = before[result.field_id]
                current = proposals.get(result.field_id)
                if current is None or _evidence_quality(result) >= _evidence_quality(current):
                    proposals[result.field_id] = result
                    proposal_scopes[result.field_id] = scope
                if request.action == "gapfill":
                    outcomes.append("IMPROVED")
                    if _evidence_quality(result) >= _EVIDENCE_RANK["NORMALIZED_MATCH"]:
                        active.remove(result.field_id)
                elif _same_value(original, result):
                    proposals[result.field_id] = result
                    proposal_scopes[result.field_id] = scope
                    conflicts.pop(result.field_id, None)
                    outcomes.append("CONFIRMED")
                    if _evidence_quality(result) >= _EVIDENCE_RANK["NORMALIZED_MATCH"]:
                        active.remove(result.field_id)
                else:
                    conflicts[result.field_id] = result
                    outcomes.append("CONFLICT")
            stage_receipts.append(
                DynamicStageReceipt(
                    scope=scope,
                    scanned_page_count=plan.scanned_page_count,
                    selected_page_count=plan.selected_page_count,
                    context_sha256=plan.context_sha256,
                    outcome=_stage_outcome(outcomes),
                )
            )

        updates: dict[str, PluginFieldResult] = {}
        diffs: list[DynamicFieldDiff] = []
        needs_review = False
        confirmed = False
        for field_id in request.field_ids:
            original = before[field_id]
            proposal = proposals.get(field_id)
            if request.action == "gapfill":
                if proposal is None:
                    field_status: FieldOutcome = "STILL_UNKNOWN"
                    after = _snapshot(original)
                else:
                    field_status = "FILLED"
                    updates[field_id] = proposal
                    after = _snapshot(proposal)
                    if _evidence_quality(proposal) < _EVIDENCE_RANK["NORMALIZED_MATCH"]:
                        needs_review = True
            elif field_id in conflicts:
                proposal = conflicts[field_id]
                field_status = "CONFLICT"
                after = _snapshot(original)
                needs_review = True
            elif proposal is not None and _same_value(original, proposal):
                field_status = "CONFIRMED"
                confirmed = True
                if _evidence_quality(proposal) > _evidence_quality(original):
                    updates[field_id] = proposal
                    after = _snapshot(proposal)
                else:
                    after = _snapshot(original)
            else:
                field_status = "UNCHANGED"
                after = _snapshot(original)
                needs_review = True
            diffs.append(
                DynamicFieldDiff(
                    field_id=field_id,
                    status=field_status,
                    scope_used=proposal_scopes.get(field_id),
                    changed=after != _snapshot(original),
                    before=_snapshot(original),
                    proposed=_snapshot(proposal) if proposal is not None else None,
                    after=after,
                )
            )

        candidate_preview = _replace_preview_fields(preview, updates)
        any_change = any(diff.changed for diff in diffs)
        operation_status: OperationStatus = (
            "NEEDS_REVIEW"
            if needs_review
            else "IMPROVED"
            if request.action == "gapfill" and any_change
            else "CONFIRMED"
            if request.action == "review" and confirmed
            else "NO_CHANGE"
        )
        operation_id = "dynamic-field-" + _canonical_sha256(
            {
                "request": request.model_dump(mode="json"),
                "candidate_preview_sha256": candidate_preview.preview_sha256,
                "stages": [receipt.model_dump(mode="json") for receipt in stage_receipts],
                "fields": [diff.model_dump(mode="json") for diff in diffs],
            }
        )[:16]
        response = DynamicFieldGapfillResponse(
            contract="insurance-v5-dynamic-field-gapfill-response.v1",
            operation_id=operation_id,
            action=request.action,
            status=operation_status,
            product_version_id=preview.product_version_id,
            base_preview_sha256=preview.preview_sha256,
            serving_effect="NONE",
            review_publish_admission=False,
            call_count=call_count,
            stages=tuple(stage_receipts),
            fields=tuple(diffs),
            candidate_preview=candidate_preview,
        )
        self._previews[preview.product_version_id] = candidate_preview
        return response


__all__ = [
    "DynamicAction",
    "DynamicFieldExecutor",
    "DynamicFieldGapfillRequest",
    "DynamicFieldGapfillResponse",
    "DynamicFieldGapfillService",
    "DynamicMaterialBundle",
    "DynamicMaterialPage",
    "DynamicMaterialRepository",
    "DynamicScope",
    "InMemoryDynamicMaterialRepository",
    "SchemaGuidedDynamicFieldExecutor",
]
