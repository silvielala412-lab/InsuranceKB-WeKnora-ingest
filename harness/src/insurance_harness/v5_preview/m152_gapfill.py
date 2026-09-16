from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Final, Literal, Self

import httpx
import pdfplumber
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import catalog_sha256, load_v5_catalog
from .contracts import (
    CandidateField,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
    V5CandidatePreview,
)
from .dynamic_gapfill import DynamicFieldSnapshot, DynamicMaterialBundle, DynamicMaterialPage
from .dynamic_ingest import (
    CandidateSourcePage,
    FieldCandidate,
    FieldCandidateRetriever,
    build_candidate_source_text,
    locate_field_candidates,
)
from .ingest import preview_digest
from .llm_plugin import (
    CompletionReceipt,
    LlmPluginError,
    OpenAICompatibleCompletion,
    SchemaGuidedLlmPlugin,
)
from .m153_quality import (
    M153IssueKind,
    TableExtractionDiagnostic,
    TablePage,
    build_table_context,
    field_needs_table_context,
    normalize_issue_types,
    select_table_pages,
)
from .m154_concurrency import (
    AdaptiveProviderGate,
    GlobalCallBudget,
    M154RunTimingReceipt,
    ProductConcurrencyProfile,
    ProductWork,
    ProviderAttemptTiming,
    RetryBudgetUnavailable,
    RunTimingRecorder,
    execute_products_ordered,
    invoke_provider_attempt,
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

M152_PRODUCT_IDS: tuple[str, ...] = (
    "596",
    "5003",
    "1826",
    "1830",
    "1814",
    "1816",
    "1828",
    "L2332",
)
M152_BASELINE_SHA256 = "87d6faf3e578daf75010d75c388116d9f9c6316d8b370ba3abeb74654f5557a8"
M152_MAX_CALLS: Final = 18
M152_MAX_FIELDS_PER_BATCH = 8

M152_WORKBOOK_SHA256: Mapping[str, str] = {
    "e生保尊享-问题.xlsx": "ced2804eb6ea274aeeadb10a7af5511986ff3cf0d5d4e3527a35217e29d25b1b",
    "年金-问题(1).xlsx": "be321b4edd84c8db130d7f5baa3f0abfd3512440336bd78b5d66ce2ed98bc7ae",
    "意外伤害-问题(1).xlsx": "91496a8c4503aa4f265218e345a6fb2de8baf2b2cb5d6d675a53279351bb604d",
    "盛世金越-问题.xlsx": "ef322a5dd17999669fc8a21f2806492e877f48ea65ef603438e2cfc9ba2c6a0a",
}


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class M152FieldIssue(_ClosedModel):
    display_name: Annotated[str, Field(min_length=1)]
    issue_labels: Annotated[tuple[str, ...], Field(min_length=1)]


FieldSource = Literal["business_xlsx", "retriever"]
FieldAction = Literal["gapfill", "review", "not_run"]
FieldStatus = Literal[
    "FILLED",
    "CONFIRMED",
    "CONFLICT",
    "STILL_UNKNOWN",
    "UNCHANGED",
    "ABSENCE_NEEDS_REVIEW",
    "PROVIDER_ERROR",
    "SCHEMA_FIELD_NOT_DEFINED",
]


class M152FieldReceipt(_ClosedModel):
    field_id: str | None
    display_name: Annotated[str, Field(min_length=1)]
    issue_labels: Annotated[tuple[str, ...], Field(min_length=1)]
    source: FieldSource
    action: FieldAction
    status: FieldStatus
    candidate_locators: tuple[str, ...]
    batch_index: Annotated[int, Field(ge=1)] | None
    provider_call: Annotated[int, Field(ge=1, le=M152_MAX_CALLS)] | None
    changed: bool
    before: DynamicFieldSnapshot | None
    proposed: DynamicFieldSnapshot | None
    after: DynamicFieldSnapshot | None
    reason: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_topology(self) -> Self:
        if self.field_id is None:
            if (
                self.status != "SCHEMA_FIELD_NOT_DEFINED"
                or self.action != "not_run"
                or any((self.before, self.proposed, self.after))
            ):
                raise ValueError("M152_UNMAPPED_FIELD_RECEIPT_INVALID")
        elif self.before is None or self.after is None or self.batch_index is None:
            raise ValueError("M152_MAPPED_FIELD_RECEIPT_INVALID")
        if self.changed and self.before == self.after:
            raise ValueError("M152_FIELD_CHANGE_FLAG_INVALID")
        if self.status == "CONFLICT" and (
            self.proposed is None or self.changed or self.before != self.after
        ):
            raise ValueError("M152_CONFLICT_OVERWRITE_FORBIDDEN")
        return self


class M152ProviderCallReceipt(_ClosedModel):
    provider_call: Annotated[int, Field(ge=1, le=M152_MAX_CALLS)]
    product_attempt: Annotated[int, Field(ge=1, le=12)]
    product_version_id: Annotated[str, Field(min_length=1)]
    batch_index: Annotated[int, Field(ge=1)]
    target_field_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]
    scanned_page_count: Annotated[int, Field(ge=1)]
    readable_page_count: Annotated[int, Field(ge=1)]
    context_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    outcome: Literal["ACCEPTED", "ERROR"]
    completion: CompletionReceipt | None
    error_code: str | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "ACCEPTED" and self.error_code is not None:
            raise ValueError("M152_ACCEPTED_CALL_HAS_ERROR")
        if self.outcome == "ERROR" and not self.error_code:
            raise ValueError("M152_ERROR_CALL_MISSING_CODE")
        return self


class M152ProductAudit(_ClosedModel):
    product_id: Annotated[str, Field(min_length=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    product_display_name: Annotated[str, Field(min_length=1)]
    source_manifest_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    scanned_page_count: Annotated[int, Field(ge=1)]
    readable_page_count: Annotated[int, Field(ge=1)]
    unreadable_page_locators: tuple[str, ...]
    planned_target_count: Annotated[int, Field(ge=1)]
    batch_count: Annotated[int, Field(ge=1)]
    calls: Annotated[tuple[M152ProviderCallReceipt, ...], Field(min_length=1)]
    fields: Annotated[tuple[M152FieldReceipt, ...], Field(min_length=1)]


class M152Metrics(_ClosedModel):
    product_count: Literal[8]
    schema_target_count: Annotated[int, Field(ge=1)]
    unmapped_business_field_count: Annotated[int, Field(ge=0)]
    candidate_hit_count: Annotated[int, Field(ge=0)]
    candidate_hit_rate: Annotated[float, Field(ge=0, le=1)]
    gapfill_target_count: Annotated[int, Field(ge=0)]
    gapfill_filled_count: Annotated[int, Field(ge=0)]
    gapfill_success_rate: Annotated[float, Field(ge=0, le=1)]
    review_target_count: Annotated[int, Field(ge=0)]
    review_proposal_count: Annotated[int, Field(ge=0)]
    review_proposal_rate: Annotated[float, Field(ge=0, le=1)]
    conflict_count: Annotated[int, Field(ge=0)]
    evidence_proposal_count: Annotated[int, Field(ge=0)]
    evidence_pass_count: Annotated[int, Field(ge=0)]
    evidence_pass_rate: Annotated[float, Field(ge=0, le=1)]
    baseline_present_count: Annotated[int, Field(ge=0)]
    result_present_count: Annotated[int, Field(ge=0)]
    present_delta: int
    material_supported_field_count: Annotated[int, Field(ge=0)]
    material_supported_present_count: Annotated[int, Field(ge=0)]
    material_supported_extraction_rate: Annotated[float, Field(ge=0, le=1)]


class M152RunAudit(_ClosedModel):
    contract: Literal["insurance-v5-m152-gapfill-audit.v1"]
    artifact_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    baseline_file_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    baseline_run_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    result_run_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    catalog_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    workbook_sha256: Mapping[str, str]
    provider: ProviderIdentity
    max_calls: Literal[18]
    prior_failed_call_count: Annotated[int, Field(ge=0, le=17)]
    call_count: Annotated[int, Field(ge=1, le=M152_MAX_CALLS)]
    mission_call_count: Annotated[int, Field(ge=1, le=M152_MAX_CALLS)]
    started_at: Annotated[str, Field(min_length=1)]
    finished_at: Annotated[str, Field(min_length=1)]
    serving_effect: Literal["NONE"]
    review_publish_admission: Literal[False]
    performance: M154RunTimingReceipt | None = None
    metrics: M152Metrics
    products: Annotated[tuple[M152ProductAudit, ...], Field(min_length=8, max_length=8)]

    @model_validator(mode="after")
    def validate_calls(self) -> Self:
        calls = tuple(call for product in self.products for call in product.calls)
        if self.call_count != len(calls):
            raise ValueError("M152_CALL_COUNT_DRIFT")
        if tuple(sorted(call.provider_call for call in calls)) != tuple(
            range(1, len(calls) + 1)
        ) or len({call.provider_call for call in calls}) != len(calls):
            raise ValueError("M152_PROVIDER_CALL_ORDER_DRIFT")
        if self.mission_call_count != self.prior_failed_call_count + self.call_count:
            raise ValueError("M152_MISSION_CALL_COUNT_DRIFT")
        return self


@dataclass(frozen=True, slots=True)
class _BusinessTarget:
    display_name: str
    issue: str
    field_id: str | None


@dataclass(frozen=True, slots=True)
class _LoadedMaterial:
    bundle: DynamicMaterialBundle
    source_manifest_sha256: str
    scanned_page_count: int
    unreadable_page_locators: tuple[str, ...]
    table_pages: tuple[TablePage, ...] = ()
    table_diagnostics: tuple[TableExtractionDiagnostic, ...] = ()
    candidate_cache: (
        dict[
            tuple[str, str, tuple[str, ...]], Mapping[str, tuple[FieldCandidate, ...]]
        ]
        | None
    ) = None
    context_cache: (
        dict[
            tuple[str, str, tuple[str, ...]],
            tuple[str, Mapping[str, tuple[str, ...]]],
        ]
        | None
    ) = None


@dataclass(frozen=True, slots=True)
class _PlannedBatch:
    index: int
    field_ids: tuple[str, ...]
    issues: Mapping[str, M152FieldIssue]
    source: FieldSource


@dataclass(frozen=True, slots=True)
class _ProductExecutionResult:
    product: ProviderTrialProduct
    audit: M152ProductAudit
    attempt_timings: tuple[ProviderAttemptTiming, ...]


@dataclass(frozen=True, slots=True)
class _FrozenCandidateRetriever(FieldCandidateRetriever):
    candidates: Mapping[str, tuple[FieldCandidate, ...]]

    def retrieve(
        self,
        pages: Sequence[CandidateSourcePage],
        schema: InsuranceSchema,
        field_ids: Sequence[str],
        *,
        max_pages_per_field: int | None = None,
    ) -> dict[str, tuple[FieldCandidate, ...]]:
        del pages, schema
        return {
            field_id: self.candidates.get(field_id, ())[:max_pages_per_field]
            if max_pages_per_field is not None
            else self.candidates.get(field_id, ())
            for field_id in field_ids
        }


_BUSINESS_TARGETS: Mapping[str, tuple[_BusinessTarget, ...]] = {
    "596": (
        _BusinessTarget("投保地区与常住地限制", "记录待定，可能需要新增字段", None),
        _BusinessTarget("等待期", "抽取不全", "waiting_period"),
        _BusinessTarget(
            "犹豫期及合同解除（退保）",
            "LLM概括不全",
            "surrender_and_cancellation_terms",
        ),
        _BusinessTarget("保险责任", "LLM概括错误、显示问题", "coverage_responsibilities"),
        _BusinessTarget("保什么", "显示问题", "coverage_summary"),
        _BusinessTarget("特殊承保与除外标签", "LLM概括错误", "special_coverage_and_exclusion_tags"),
        _BusinessTarget("外购药/特药责任", "抽取不全", "out_of_hospital_special_drug_coverage"),
        _BusinessTarget("责任免除", "抽取不全", "exclusions"),
        _BusinessTarget("报销范围", "抽取不全", "reimbursable_expense_scope"),
        _BusinessTarget("报销比例", "LLM概括错误", "reimbursement_rate_rules"),
        _BusinessTarget(
            "理赔申请时效与申请材料",
            "抽取不全、LLM概括不全",
            "claim_application_deadline_and_documents",
        ),
        _BusinessTarget("保单权益", "LLM概括错误", "policyholder_rights"),
        _BusinessTarget("增值服务", "LLM概括错误", "medical_service_benefits"),
        _BusinessTarget("产品Q&A", "抽取错误、LLM概括错误", "product_faq"),
    ),
    "1830": (
        _BusinessTarget("缴费期限", "抽取不全", "premium_payment_term"),
        _BusinessTarget("缴费方式", "抽取不全", "premium_payment_frequency"),
        _BusinessTarget("保障期间分类", "未识别", "coverage_term_category"),
        _BusinessTarget("保险责任", "LLM概括不全", "coverage_responsibilities"),
        _BusinessTarget("保什么", "抽取不全", "coverage_summary"),
        _BusinessTarget("保额形态", "未识别", "sum_assured_pattern"),
        _BusinessTarget("责任免除", "抽取不全", "exclusions"),
        _BusinessTarget("受益人规则", "LLM概括不全", "beneficiary_rules"),
        _BusinessTarget("领取型保险金类别", "未抽取", "annuity_benefit_types"),
        _BusinessTarget("年金开始领取时间", "未抽取", "annuity_start_time"),
        _BusinessTarget("起领年龄", "未抽取", "annuity_start_age"),
        _BusinessTarget("领取频率", "未抽取", "annuity_payment_frequency"),
        _BusinessTarget("减保规则", "未抽取", "sum_assured_reduction_rules"),
    ),
    "1814": (
        _BusinessTarget("缴费期限", "未抽取", "premium_payment_term"),
        _BusinessTarget("缴费方式", "未抽取", "premium_payment_frequency"),
        _BusinessTarget(
            "犹豫期及合同解除（退保）",
            "LLM概括错误",
            "surrender_and_cancellation_terms",
        ),
        _BusinessTarget("保险责任", "LLM概括不全", "coverage_responsibilities"),
        _BusinessTarget("责任免除", "抽取不全", "exclusions"),
        _BusinessTarget(
            "理赔申请时效与申请材料",
            "未抽取",
            "claim_application_deadline_and_documents",
        ),
        _BusinessTarget("保单权益", "未抽取", "policyholder_rights"),
    ),
    "5003": (
        _BusinessTarget("产品简介", "LLM概括不全", "product_summary"),
        _BusinessTarget("产品特色", "LLM概括不全", "official_product_features"),
        _BusinessTarget("缴费期限", "未抽取", "premium_payment_term"),
        _BusinessTarget("缴费方式", "未抽取", "premium_payment_frequency"),
        _BusinessTarget("保障期间", "抽取不全", "coverage_period"),
        _BusinessTarget("保险责任", "抽取不全", "coverage_responsibilities"),
        _BusinessTarget("全残保障", "未识别", "total_disability_coverage_flag"),
        _BusinessTarget("意外身故", "未识别", "accidental_death_coverage_flag"),
        _BusinessTarget("疾病身故", "未识别", "disease_death_coverage_flag"),
        _BusinessTarget("特殊承保与除外标签", "LLM概括错误", "special_coverage_and_exclusion_tags"),
        _BusinessTarget("责任免除", "抽取不全", "exclusions"),
        _BusinessTarget("身故给付规则", "抽取不全、LLM概括不全", "death_benefit_rules"),
        _BusinessTarget("加保规则", "LLM概括错误", "coverage_increase_rules"),
        _BusinessTarget("分红规则", "抽取不全", "dividend_rules"),
    ),
}

_BUSINESS_BATCH_GROUPS: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "596": (
        (
            "waiting_period",
            "surrender_and_cancellation_terms",
            "special_coverage_and_exclusion_tags",
            "policyholder_rights",
        ),
        (
            "coverage_responsibilities",
            "reimbursement_rate_rules",
            "medical_service_benefits",
        ),
        (
            "coverage_summary",
            "out_of_hospital_special_drug_coverage",
            "reimbursable_expense_scope",
        ),
        (
            "exclusions",
            "claim_application_deadline_and_documents",
            "product_faq",
        ),
    ),
    "1830": (
        (
            "premium_payment_term",
            "premium_payment_frequency",
            "coverage_term_category",
            "sum_assured_pattern",
            "annuity_benefit_types",
            "annuity_start_time",
            "annuity_start_age",
            "annuity_payment_frequency",
        ),
        (
            "coverage_responsibilities",
            "coverage_summary",
            "exclusions",
            "beneficiary_rules",
            "sum_assured_reduction_rules",
        ),
    ),
    "1814": (
        (
            "premium_payment_term",
            "premium_payment_frequency",
            "surrender_and_cancellation_terms",
            "policyholder_rights",
        ),
        (
            "coverage_responsibilities",
            "exclusions",
            "claim_application_deadline_and_documents",
        ),
    ),
    "5003": (
        (
            "product_summary",
            "official_product_features",
            "premium_payment_term",
            "premium_payment_frequency",
            "coverage_period",
        ),
        (
            "coverage_responsibilities",
            "total_disability_coverage_flag",
            "accidental_death_coverage_flag",
            "disease_death_coverage_flag",
            "special_coverage_and_exclusion_tags",
        ),
        (
            "exclusions",
            "death_benefit_rules",
            "coverage_increase_rules",
            "dividend_rules",
        ),
    ),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_digest(domain: str, payload: object) -> str:
    encoded = json.dumps(
        {"domain": domain, "payload": payload},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


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


def _evidence_quality(field: CandidateField | PluginFieldResult) -> int:
    rank = {"UNRESOLVED": 1, "AMBIGUOUS": 2, "NORMALIZED_MATCH": 3, "VERIFIED": 4}
    return max((rank[evidence.verification_status] for evidence in field.evidence), default=0)


def _same_value(left: CandidateField, right: PluginFieldResult) -> bool:
    return left.state == right.state and _normalized(left.value) == _normalized(right.value)


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
    payload = preview.model_dump(mode="json")
    payload.pop("preview_sha256")
    payload["fields"] = [field.model_dump(mode="json") for field in fields]
    return preview.model_copy(
        update={"fields": fields, "preview_sha256": preview_digest(payload)}
    )


def split_target_batches(
    field_ids: Sequence[str],
    *,
    max_fields: int = M152_MAX_FIELDS_PER_BATCH,
) -> tuple[tuple[str, ...], ...]:
    ordered = tuple(field_ids)
    if (
        not ordered
        or len(set(ordered)) != len(ordered)
        or not 1 <= max_fields <= M152_MAX_FIELDS_PER_BATCH
    ):
        raise ValueError("M152_TARGET_FIELD_SET_INVALID")
    return tuple(
        ordered[index : index + max_fields]
        for index in range(0, len(ordered), max_fields)
    )


def merge_m152_batch(
    *,
    preview: V5CandidatePreview,
    results: Sequence[PluginFieldResult],
    issues: Mapping[str, M152FieldIssue],
    candidate_locators: Mapping[str, Sequence[str]],
    batch_index: int,
    provider_call: int,
    source: FieldSource = "business_xlsx",
) -> tuple[V5CandidatePreview, tuple[M152FieldReceipt, ...]]:
    requested = tuple(issues)
    result_by_id = {result.field_id: result for result in results}
    before_by_id = {field.field_id: field for field in preview.fields}
    if tuple(result.field_id for result in results) != requested:
        raise ValueError("M152_PROVIDER_FIELD_TOPOLOGY_DRIFT")
    if any(field_id not in before_by_id for field_id in requested):
        raise ValueError("M152_TARGET_FIELD_SET_INVALID")

    updates: dict[str, PluginFieldResult] = {}
    receipts: list[M152FieldReceipt] = []
    for field_id in requested:
        original = before_by_id[field_id]
        result = result_by_id[field_id]
        if result.ordinal != original.ordinal:
            raise ValueError("M152_PROVIDER_FIELD_TOPOLOGY_DRIFT")
        before = _snapshot(original)
        proposed = _snapshot(result) if result.state != "unknown" else None
        action: FieldAction = "gapfill" if original.state == "unknown" else "review"
        status: FieldStatus
        if original.state == "unknown" and result.state == "absent_explicitly":
            status = "ABSENCE_NEEDS_REVIEW"
            after = before
            reason = (
                "explicit absence requires semantic human review; unknown baseline was preserved"
            )
        elif original.state == "unknown" and result.state == "present":
            status = "FILLED"
            updates[field_id] = result
            after = _snapshot(result)
            reason = "unknown field received a material-bound proposal"
        elif original.state == "unknown":
            status = "STILL_UNKNOWN"
            after = before
            reason = "provider did not find enough support in the bounded all-material context"
        elif result.state == "unknown":
            status = "UNCHANGED"
            after = before
            reason = "review produced no supported proposal; baseline was preserved"
        elif _same_value(original, result):
            status = "CONFIRMED"
            if _evidence_quality(result) > _evidence_quality(original):
                updates[field_id] = result
                after = _snapshot(result)
                reason = "same value confirmed with stronger Evidence"
            else:
                after = before
                reason = "same normalized value confirmed; baseline Evidence was retained"
        else:
            status = "CONFLICT"
            after = before
            reason = "different review proposal requires human decision; baseline was preserved"
        issue = issues[field_id]
        receipts.append(
            M152FieldReceipt(
                field_id=field_id,
                display_name=issue.display_name,
                issue_labels=issue.issue_labels,
                source=source,
                action=action,
                status=status,
                candidate_locators=tuple(candidate_locators.get(field_id, ())),
                batch_index=batch_index,
                provider_call=provider_call,
                changed=after != before,
                before=before,
                proposed=proposed,
                after=after,
                reason=reason,
            )
        )
    return _replace_preview_fields(preview, updates), tuple(receipts)


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


def _field_error_receipts(
    *,
    preview: V5CandidatePreview,
    batch: _PlannedBatch,
    candidate_locators: Mapping[str, Sequence[str]],
    provider_call: int,
    error_code: str,
) -> tuple[M152FieldReceipt, ...]:
    by_id = {field.field_id: field for field in preview.fields}
    return tuple(
        M152FieldReceipt(
            field_id=field_id,
            display_name=batch.issues[field_id].display_name,
            issue_labels=batch.issues[field_id].issue_labels,
            source=batch.source,
            action="gapfill" if by_id[field_id].state == "unknown" else "review",
            status="PROVIDER_ERROR",
            candidate_locators=tuple(candidate_locators.get(field_id, ())),
            batch_index=batch.index,
            provider_call=provider_call,
            changed=False,
            before=_snapshot(by_id[field_id]),
            proposed=None,
            after=_snapshot(by_id[field_id]),
            reason=f"provider batch failed with {error_code}; baseline was preserved",
        )
        for field_id in batch.field_ids
    )


def _validate_external_inputs(baseline_path: Path, business_root: Path) -> None:
    if _sha256_bytes(baseline_path.read_bytes()) != M152_BASELINE_SHA256:
        raise ProviderTrialError("M152_BASELINE_FILE_SHA256_DRIFT")
    for file_name, expected_sha256 in M152_WORKBOOK_SHA256.items():
        path = business_root / file_name
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != expected_sha256:
            raise ProviderTrialError("M152_BUSINESS_WORKBOOK_SHA256_DRIFT")


def _load_material(
    *,
    product: ProviderTrialProduct,
    roots: Sequence[Path],
    supplemental_root_596: Path,
) -> _LoadedMaterial:
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    approved_by_id = {item.product_id: item for item in APPROVED_PRODUCTS}
    try:
        approved = approved_by_id[product.product_id]
    except KeyError as exc:
        raise ProviderTrialError("M152_APPROVED_PRODUCT_MISSING") from exc
    selected_root = roots[1] if product.product_id in {"1828", "L2332"} else roots[0]
    folder = selected_root / approved.directory_name
    if not folder.is_dir():
        raise ProviderTrialError("M152_PRODUCT_ROOT_MISSING")
    expected_base_names = {"product_meta.json", *(item.file_name for item in approved.pdfs)}
    actual_base_names = {path.name for path in folder.iterdir() if path.is_file()}
    if actual_base_names != expected_base_names:
        raise ProviderTrialError("M152_SOURCE_SET_DRIFT")
    metadata = folder / "product_meta.json"
    if _sha256_bytes(metadata.read_bytes()) != approved.metadata_sha256:
        raise ProviderTrialError("M152_SOURCE_METADATA_SHA256_DRIFT")

    approved_base_names = {item.file_name for item in approved.pdfs}
    pages: list[DynamicMaterialPage] = []
    table_pages: list[TablePage] = []
    table_diagnostics: list[TableExtractionDiagnostic] = []
    unreadable: list[str] = []
    scanned_page_count = 0
    for receipt in product.files:
        path = (
            folder / receipt.file_name
            if receipt.file_name in approved_base_names
            else supplemental_root_596 / receipt.file_name
        )
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != receipt.sha256:
            raise ProviderTrialError("M152_SOURCE_FILE_SHA256_DRIFT")
        with pdfplumber.open(path) as document:
            if len(document.pages) != receipt.page_count:
                raise ProviderTrialError("M152_SOURCE_PAGE_COUNT_DRIFT")
            for page_number, page in enumerate(document.pages, 1):
                scanned_page_count += 1
                text = (page.extract_text() or "").strip()
                try:
                    extracted_tables = page.extract_tables() or ()
                    for table_index, rows in enumerate(extracted_tables, 1):
                        normalized_rows = [
                            tuple(cell or "" for cell in row) for row in rows if row
                        ]
                        if normalized_rows:
                            table_pages.append(
                                TablePage.from_rows(
                                    document_name=receipt.file_name,
                                    page_number=page_number,
                                    table_index=table_index,
                                    headers=normalized_rows[0],
                                    rows=normalized_rows[1:],
                                )
                            )
                    table_diagnostics.append(
                        TableExtractionDiagnostic(
                            document_name=receipt.file_name,
                            page_number=page_number,
                            table_count=len(extracted_tables),
                            status="extracted" if extracted_tables else "no_table",
                        )
                    )
                except Exception as exc:
                    table_diagnostics.append(
                        TableExtractionDiagnostic(
                            document_name=receipt.file_name,
                            page_number=page_number,
                            table_count=0,
                            status="failed",
                            error=type(exc).__name__,
                        )
                    )
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
    return _LoadedMaterial(
        bundle=DynamicMaterialBundle(
            product_version_id=product.product_version_id,
            source_revision_id=product.source_revision_id,
            pages=tuple(pages),
        ),
        source_manifest_sha256=product.source_manifest_sha256,
        scanned_page_count=scanned_page_count,
        unreadable_page_locators=tuple(unreadable),
        table_pages=tuple(table_pages),
        table_diagnostics=tuple(table_diagnostics),
        candidate_cache={},
        context_cache={},
    )


def _business_plan(
    product: ProviderTrialProduct,
) -> tuple[tuple[_PlannedBatch, ...], tuple[M152FieldReceipt, ...]]:
    if product.preview is None:
        raise ProviderTrialError("M152_BASELINE_PREVIEW_MISSING")
    schema_order = {field.field_id: field.ordinal for field in product.preview.fields}
    mapped = tuple(
        target
        for target in _BUSINESS_TARGETS[product.product_id]
        if target.field_id is not None
        and set(normalize_issue_types(target.issue)) != {M153IssueKind.display_only}
    )
    if any(target.field_id not in schema_order for target in mapped):
        raise ProviderTrialError("M152_BUSINESS_FIELD_SCHEMA_DRIFT")
    issue_by_id = {
        str(target.field_id): M152FieldIssue(
            display_name=target.display_name,
            issue_labels=(target.issue,),
        )
        for target in mapped
    }
    allowed_ids = {target.field_id for target in mapped}
    groups = tuple(
        tuple(field_id for field_id in group if field_id in allowed_ids)
        for group in _BUSINESS_BATCH_GROUPS[product.product_id]
    )
    groups = tuple(group for group in groups if group)
    flattened = tuple(field_id for group in groups for field_id in group)
    if set(flattened) != set(issue_by_id) or len(flattened) != len(set(flattened)):
        raise ProviderTrialError("M152_BUSINESS_BATCH_TOPOLOGY_DRIFT")
    if any(
        len(group) > M152_MAX_FIELDS_PER_BATCH
        or tuple(sorted(group, key=schema_order.__getitem__)) != group
        for group in groups
    ):
        raise ProviderTrialError("M152_BUSINESS_BATCH_ORDER_DRIFT")
    batches = tuple(
        _PlannedBatch(
            index=index,
            field_ids=field_ids,
            issues={field_id: issue_by_id[field_id] for field_id in field_ids},
            source="business_xlsx",
        )
        for index, field_ids in enumerate(groups, 1)
    )
    unmapped = tuple(
        M152FieldReceipt(
            field_id=None,
            display_name=target.display_name,
            issue_labels=(target.issue,),
            source="business_xlsx",
            action="not_run",
            status="SCHEMA_FIELD_NOT_DEFINED",
            candidate_locators=(),
            batch_index=None,
            provider_call=None,
            changed=False,
            before=None,
            proposed=None,
            after=None,
            reason="business field has no matching v5 Schema field",
        )
        for target in _BUSINESS_TARGETS[product.product_id]
        if target.field_id is None
    )
    return batches, unmapped


def _retriever_plan(
    product: ProviderTrialProduct,
    material: _LoadedMaterial,
) -> tuple[_PlannedBatch, ...]:
    if product.preview is None:
        raise ProviderTrialError("M152_BASELINE_PREVIEW_MISSING")
    catalog = load_v5_catalog()
    schema = catalog.schema_for(product.insurance_class)
    unknown = tuple(field for field in product.preview.fields if field.state == "unknown")
    located = locate_field_candidates(
        material.bundle.pages,
        schema,
        tuple(field.field_id for field in unknown),
        max_pages_per_field=8,
    )
    support = {item.field_id: item.status for item in product.material_support}
    support_rank = {"supported": 2, "ambiguous": 1, "unsupported": 0}
    ranked = sorted(
        (field for field in unknown if located.get(field.field_id)),
        key=lambda field: (
            -support_rank.get(support.get(field.field_id, "unsupported"), 0),
            -max(candidate.score for candidate in located[field.field_id]),
            -len(located[field.field_id]),
            field.ordinal,
        ),
    )[:M152_MAX_FIELDS_PER_BATCH]
    if not ranked:
        raise ProviderTrialError("M152_RETRIEVER_TARGETS_EMPTY")
    ranked.sort(key=lambda field: field.ordinal)
    field_ids = tuple(field.field_id for field in ranked)
    return (
        _PlannedBatch(
            index=1,
            field_ids=field_ids,
            issues={
                field.field_id: M152FieldIssue(
                    display_name=field.display_name,
                    issue_labels=("baseline unknown with all-page candidate",),
                )
                for field in ranked
            },
            source="retriever",
        ),
    )


def _plans_for_product(
    product: ProviderTrialProduct,
    material: _LoadedMaterial,
) -> tuple[tuple[_PlannedBatch, ...], tuple[M152FieldReceipt, ...]]:
    if product.product_id in _BUSINESS_TARGETS:
        return _business_plan(product)
    return _retriever_plan(product, material), ()


def _context_for_batch(
    material: _LoadedMaterial,
    insurance_class: str,
    field_ids: tuple[str, ...],
) -> tuple[str, Mapping[str, tuple[str, ...]]]:
    cache_key = (material.source_manifest_sha256, insurance_class, field_ids)
    if material.context_cache is not None and cache_key in material.context_cache:
        return material.context_cache[cache_key]
    schema = load_v5_catalog().schema_for(insurance_class)
    if material.candidate_cache is not None and cache_key in material.candidate_cache:
        located = material.candidate_cache[cache_key]
    else:
        located = locate_field_candidates(
            material.bundle.pages,
            schema,
            field_ids,
            max_pages_per_field=8,
        )
        if material.candidate_cache is not None:
            material.candidate_cache[cache_key] = located
    ranked = build_candidate_source_text(
        material.bundle.pages,
        schema,
        field_ids,
        max_pages=36,
        max_characters=120_000,
        max_pages_per_field=8,
        snippet_characters=1_600,
        retriever=_FrozenCandidateRetriever(located),
    )
    context = ranked
    if any(field_needs_table_context(field_id) for field_id in field_ids):
        table_context = build_table_context(select_table_pages(material.table_pages, field_ids))
        if table_context:
            context = f"{context}\n\n{table_context}"
    context = "\n".join(dict.fromkeys(context.splitlines()))[:180_000]
    result = (context, {
        field_id: tuple(candidate.locator for candidate in located.get(field_id, ()))
        for field_id in field_ids
    })
    if material.context_cache is not None:
        material.context_cache[cache_key] = result
    return result


def _repair_hint(batch: _PlannedBatch) -> str:
    rows = [
        {
            "field_id": field_id,
            "display_name": batch.issues[field_id].display_name,
            "known_issue_type": batch.issues[field_id].issue_labels,
            "normalized_issue_type": tuple(
                kind.value
                for label in batch.issues[field_id].issue_labels
                for kind in normalize_issue_types(label)
            ),
        }
        for field_id in batch.field_ids
    ]
    return (
        "M152 bounded all-material re-extraction. Independently re-read the supplied material "
        "for every ordered target. The previous result is not an authority and is intentionally "
        "not shown. For incomplete or wrong fields, return the complete material-supported value; "
        "for unknown fields, fill only when Evidence supports it. Do not infer missing facts. "
        "The business workbook supplies issue types only, never expected answers. targets="
        + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    )


def _execute_batch(
    *,
    product: ProviderTrialProduct,
    preview: V5CandidatePreview,
    material: _LoadedMaterial,
    batch: _PlannedBatch,
    completion: OpenAICompatibleCompletion,
    context: str,
) -> tuple[PluginFieldResult, ...]:
    pages = tuple(
        SourcePage(
            document_name=page.document_name,
            document_sha256=page.document_sha256,
            page_number=page.page_number,
            text=page.text,
        )
        for page in material.bundle.pages
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
    schema = load_v5_catalog().schema_for(preview.insurance_class)
    result = SchemaGuidedLlmPlugin(
        completion=completion,
        evidence_resolver=lambda quote, locator: classify_evidence(pages, quote, locator),
        repair_hint=_repair_hint(batch),
        target_field_ids=batch.field_ids,
    ).extract(request, schema)
    requested = set(batch.field_ids)
    targeted = tuple(field for field in result.fields if field.field_id in requested)
    if tuple(field.field_id for field in targeted) != batch.field_ids:
        raise LlmPluginError("M152_PROVIDER_FIELD_TOPOLOGY_DRIFT")
    return targeted


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


def preserve_unreviewed_absences(
    baseline: V5ProviderTrialRun,
    result: V5ProviderTrialRun,
) -> V5ProviderTrialRun:
    """Undo unknown-to-absence changes that have no semantic absence review."""

    baseline_by_version = {
        product.product_version_id: product for product in baseline.products
    }
    if set(baseline_by_version) != {
        product.product_version_id for product in result.products
    }:
        raise ProviderTrialError("M152_RESULT_PRODUCT_SET_DRIFT")
    products: list[ProviderTrialProduct] = []
    for product in result.products:
        baseline_product = baseline_by_version[product.product_version_id]
        if product.preview is None or baseline_product.preview is None:
            raise ProviderTrialError("M152_RESULT_PREVIEW_MISSING")
        baseline_fields = {
            field.field_id: field for field in baseline_product.preview.fields
        }
        fields = tuple(
            baseline_fields[field.field_id]
            if baseline_fields[field.field_id].state == "unknown"
            and field.state == "absent_explicitly"
            else field
            for field in product.preview.fields
        )
        payload = product.preview.model_dump(mode="json")
        payload.pop("preview_sha256")
        payload["fields"] = [field.model_dump(mode="json") for field in fields]
        preview = product.preview.model_copy(
            update={"fields": fields, "preview_sha256": preview_digest(payload)}
        )
        review_error = _review_error_code(preview)
        metrics = compute_material_supported_extraction_rate(
            preview,
            product.material_support,
        )
        products.append(
            ProviderTrialProduct(
                product_id=product.product_id,
                product_version_id=product.product_version_id,
                product_display_name=product.product_display_name,
                insurance_class=product.insurance_class,
                schema_id=product.schema_id,
                source_revision_id=product.source_revision_id,
                source_manifest_sha256=product.source_manifest_sha256,
                status="SUCCESS" if review_error is None else "REVIEW_REQUIRED",
                error_code=review_error,
                files=product.files,
                attempts=product.attempts,
                preview=preview,
                material_support=product.material_support,
                material_support_metrics=metrics,
            )
        )
    return seal_provider_trial_run(
        provider=result.provider,
        products=tuple(products),
        started_at=result.started_at,
        finished_at=result.finished_at,
    )


def _provider_product(
    *,
    baseline: ProviderTrialProduct,
    preview: V5CandidatePreview,
    calls: Sequence[M152ProviderCallReceipt],
) -> ProviderTrialProduct:
    review_error = _review_error_code(preview)
    status: Literal["SUCCESS", "REVIEW_REQUIRED"] = (
        "SUCCESS" if review_error is None else "REVIEW_REQUIRED"
    )
    attempts = tuple(
        ProviderAttemptReceipt(
            attempt=index,
            outcome="ACCEPTED" if status == "SUCCESS" else "PRESERVED",
            response_id=call.completion.response_id if call.completion else None,
            response_model=call.completion.response_model if call.completion else None,
            finish_reason=call.completion.finish_reason if call.completion else None,
            prompt_tokens=call.completion.prompt_tokens if call.completion else None,
            completion_tokens=call.completion.completion_tokens if call.completion else None,
            total_tokens=call.completion.total_tokens if call.completion else None,
            error_code=review_error,
        )
        for index, call in enumerate(calls, 1)
    )
    material_metrics = compute_material_supported_extraction_rate(
        preview,
        baseline.material_support,
    )
    return ProviderTrialProduct(
        product_id=baseline.product_id,
        product_version_id=baseline.product_version_id,
        product_display_name=baseline.product_display_name,
        insurance_class=baseline.insurance_class,
        schema_id=baseline.schema_id,
        source_revision_id=baseline.source_revision_id,
        source_manifest_sha256=baseline.source_manifest_sha256,
        status=status,
        error_code=review_error,
        files=baseline.files,
        attempts=attempts,
        preview=preview,
        material_support=baseline.material_support,
        material_support_metrics=material_metrics,
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _metrics(
    baseline: V5ProviderTrialRun,
    products: Sequence[ProviderTrialProduct],
    audits: Sequence[M152ProductAudit],
) -> M152Metrics:
    receipts = tuple(receipt for product in audits for receipt in product.fields)
    mapped = tuple(receipt for receipt in receipts if receipt.field_id is not None)
    gapfill = tuple(receipt for receipt in mapped if receipt.action == "gapfill")
    review = tuple(receipt for receipt in mapped if receipt.action == "review")
    proposals = tuple(
        receipt
        for receipt in mapped
        if receipt.proposed is not None and receipt.proposed.state != "unknown"
    )
    evidence_pass = tuple(
        receipt
        for receipt in proposals
        if receipt.proposed is not None
        and receipt.proposed.evidence
        and all(
            evidence.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
            for evidence in receipt.proposed.evidence
        )
    )
    baseline_present = sum(
        field.state == "present"
        for product in baseline.products
        if product.preview is not None
        for field in product.preview.fields
    )
    result_present = sum(
        field.state == "present"
        for product in products
        if product.preview is not None
        for field in product.preview.fields
    )
    material_supported = sum(
        product.material_support_metrics.material_supported_field_count
        for product in products
        if product.material_support_metrics is not None
    )
    material_present = sum(
        product.material_support_metrics.material_supported_present_count
        for product in products
        if product.material_support_metrics is not None
    )
    return M152Metrics(
        product_count=8,
        schema_target_count=len(mapped),
        unmapped_business_field_count=sum(receipt.field_id is None for receipt in receipts),
        candidate_hit_count=sum(bool(receipt.candidate_locators) for receipt in mapped),
        candidate_hit_rate=_rate(
            sum(bool(receipt.candidate_locators) for receipt in mapped), len(mapped)
        ),
        gapfill_target_count=len(gapfill),
        gapfill_filled_count=sum(receipt.status == "FILLED" for receipt in gapfill),
        gapfill_success_rate=_rate(
            sum(receipt.status == "FILLED" for receipt in gapfill), len(gapfill)
        ),
        review_target_count=len(review),
        review_proposal_count=sum(receipt.proposed is not None for receipt in review),
        review_proposal_rate=_rate(
            sum(receipt.proposed is not None for receipt in review), len(review)
        ),
        conflict_count=sum(receipt.status == "CONFLICT" for receipt in mapped),
        evidence_proposal_count=len(proposals),
        evidence_pass_count=len(evidence_pass),
        evidence_pass_rate=_rate(len(evidence_pass), len(proposals)),
        baseline_present_count=baseline_present,
        result_present_count=result_present,
        present_delta=result_present - baseline_present,
        material_supported_field_count=material_supported,
        material_supported_present_count=material_present,
        material_supported_extraction_rate=_rate(material_present, material_supported),
    )


def _write_audit(path: Path, audit: M152RunAudit) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            audit.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_m152_audit(path: Path) -> M152RunAudit:
    raw = json.loads(path.read_text(encoding="utf-8"))
    claimed = raw.pop("artifact_sha256", None)
    expected = _canonical_digest("insurance-v5-m152-gapfill-audit.v1", raw)
    if claimed != expected:
        raise ProviderTrialError("M152_AUDIT_DIGEST_INVALID")
    return M152RunAudit.model_validate_json(
        json.dumps(
            {**raw, "artifact_sha256": claimed},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def run_m152(
    *,
    baseline_path: Path,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
    business_root: Path,
    output_path: Path,
    audit_output_path: Path,
    completion: OpenAICompatibleCompletion | None = None,
    completion_factory: Callable[[], OpenAICompatibleCompletion] | None = None,
    concurrency_profile: ProductConcurrencyProfile | None = None,
    prior_failed_call_count: int = 0,
) -> tuple[V5ProviderTrialRun, M152RunAudit]:
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    timer = RunTimingRecorder()
    if (completion is None) == (completion_factory is None):
        raise ProviderTrialError("M154_COMPLETION_SOURCE_INVALID")
    requested_profile = concurrency_profile or ProductConcurrencyProfile()
    effective_profile = (
        requested_profile
        if completion_factory is not None
        else ProductConcurrencyProfile(max_products=1)
    )
    if output_path.resolve() == baseline_path.resolve():
        raise ProviderTrialError("M152_BASELINE_OVERWRITE_FORBIDDEN")
    _validate_external_inputs(baseline_path, business_root)
    baseline = load_provider_trial_run(baseline_path)
    if tuple(product.product_id for product in baseline.products) != M152_PRODUCT_IDS:
        raise ProviderTrialError("M152_BASELINE_PRODUCT_SET_DRIFT")
    catalog = load_v5_catalog()
    if baseline.catalog_sha256 != catalog_sha256(catalog):
        raise ProviderTrialError("M152_CATALOG_IDENTITY_DRIFT")

    if not 0 <= prior_failed_call_count < M152_MAX_CALLS:
        raise ProviderTrialError("M152_PRIOR_CALL_COUNT_INVALID")
    roots = (sample_root, serious_illness_root)
    with timer.stage("materials_parse"):
        with ProcessPoolExecutor(max_workers=4) as pool:
            material_futures = tuple(
                (
                    product.product_version_id,
                    pool.submit(
                        _load_material,
                        product=product,
                        roots=roots,
                        supplemental_root_596=supplemental_root_596,
                    ),
                )
                for product in baseline.products
            )
            materials = {
                product_version_id: future.result()
                for product_version_id, future in material_futures
            }
    print(
        json.dumps(
            {
                "event": "M152_MATERIALS_VALIDATED",
                "products": len(materials),
                "scanned_pages": sum(item.scanned_page_count for item in materials.values()),
                "readable_pages": sum(len(item.bundle.pages) for item in materials.values()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    with timer.stage("planning"):
        planned = {
            product.product_version_id: _plans_for_product(
                product,
                materials[product.product_version_id],
            )
            for product in baseline.products
        }
        planned_batch_count = sum(len(item[0]) for item in planned.values())
        current_call_budget = M152_MAX_CALLS - prior_failed_call_count
        if planned_batch_count > current_call_budget:
            raise ProviderTrialError("M152_PLANNED_CALL_BUDGET_EXCEEDED")
        prepared_contexts = {
            (product.product_version_id, batch.index): _context_for_batch(
                materials[product.product_version_id],
                product.insurance_class,
                batch.field_ids,
            )
            for product in baseline.products
            for batch in planned[product.product_version_id][0]
        }
    print(
        json.dumps(
            {
                "event": "M152_PLAN_FROZEN",
                "planned_batches": planned_batch_count,
                "current_call_budget": current_call_budget,
                "prior_failed_call_count": prior_failed_call_count,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    started_at = timer.started_at
    budget = GlobalCallBudget(
        total_calls=current_call_budget,
        required_primary_calls=planned_batch_count,
    )
    gate = AdaptiveProviderGate(effective_profile)

    def execute_product(
        work: ProductWork[ProviderTrialProduct],
    ) -> _ProductExecutionResult:
        baseline_product = work.payload
        if baseline_product.preview is None:
            raise ProviderTrialError("M152_BASELINE_PREVIEW_MISSING")
        material = materials[baseline_product.product_version_id]
        batches, pre_receipts = planned[baseline_product.product_version_id]
        preview = baseline_product.preview
        field_receipts = list(pre_receipts)
        call_receipts: list[M152ProviderCallReceipt] = []
        attempt_timings: list[ProviderAttemptTiming] = []
        product_completion = completion_factory() if completion_factory else completion
        if product_completion is None:
            raise ProviderTrialError("M154_PRODUCT_COMPLETION_MISSING")
        owns_completion = completion_factory is not None
        try:
            for batch in batches:
                context, candidate_locators = prepared_contexts[
                    (baseline_product.product_version_id, batch.index)
                ]
                context_sha256 = _sha256_text(context)
                results: tuple[PluginFieldResult, ...] | None = None
                final_error: str | None = None
                final_call = 0
                batch_attempt_count = 0
                while True:
                    batch_attempt_count += 1
                    before_receipts = len(product_completion.receipts)

                    call_provider = partial(
                        _execute_batch,
                        product=baseline_product,
                        preview=preview,
                        material=material,
                        batch=batch,
                        completion=product_completion,
                        context=context,
                    )

                    try:
                        outcome = invoke_provider_attempt(
                            budget=budget,
                            gate=gate,
                            product_version_id=baseline_product.product_version_id,
                            batch_index=batch.index,
                            attempt=batch_attempt_count,
                            retry=batch_attempt_count > 1,
                            call=call_provider,
                        )
                    except RetryBudgetUnavailable:
                        break
                    attempt_timings.append(outcome.timing)
                    final_call = outcome.reservation.provider_call
                    if outcome.error is None:
                        results = outcome.value
                        final_error = None
                    elif isinstance(
                        outcome.error,
                        (LlmPluginError, httpx.HTTPError, ValueError),
                    ):
                        final_error = _typed_error_code(outcome.error)
                    else:
                        raise outcome.error
                    provider_receipt = (
                        product_completion.receipts[-1]
                        if len(product_completion.receipts) > before_receipts
                        else None
                    )
                    call_receipts.append(
                        M152ProviderCallReceipt(
                            provider_call=final_call,
                            product_attempt=len(call_receipts) + 1,
                            product_version_id=baseline_product.product_version_id,
                            batch_index=batch.index,
                            target_field_ids=batch.field_ids,
                            scanned_page_count=material.scanned_page_count,
                            readable_page_count=len(material.bundle.pages),
                            context_sha256=context_sha256,
                            outcome="ACCEPTED" if final_error is None else "ERROR",
                            completion=provider_receipt,
                            error_code=final_error,
                        )
                    )
                    print(
                        json.dumps(
                            {
                                "event": "M152_PROVIDER_CALL",
                                "provider_call": final_call,
                                "mission_call": prior_failed_call_count + final_call,
                                "product_version_id": baseline_product.product_version_id,
                                "batch_index": batch.index,
                                "outcome": (
                                    "ACCEPTED" if final_error is None else "ERROR"
                                ),
                                "error_code": final_error,
                                "active_limit": gate.current_limit,
                                "duration_ms": outcome.timing.duration_ms,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    if final_error is None or batch_attempt_count >= 2:
                        break
                if results is None or final_error is not None:
                    field_receipts.extend(
                        _field_error_receipts(
                            preview=preview,
                            batch=batch,
                            candidate_locators=candidate_locators,
                            provider_call=final_call,
                            error_code=final_error or "M152_PROVIDER_RESULT_MISSING",
                        )
                    )
                else:
                    preview, merged_receipts = merge_m152_batch(
                        preview=preview,
                        results=results,
                        issues=batch.issues,
                        candidate_locators=candidate_locators,
                        batch_index=batch.index,
                        provider_call=final_call,
                        source=batch.source,
                    )
                    field_receipts.extend(merged_receipts)
        finally:
            if owns_completion:
                product_completion.close()

        output_product = _provider_product(
            baseline=baseline_product,
            preview=preview,
            calls=call_receipts,
        )
        product_audit = M152ProductAudit(
            product_id=baseline_product.product_id,
            product_version_id=baseline_product.product_version_id,
            product_display_name=baseline_product.product_display_name,
            source_manifest_sha256=baseline_product.source_manifest_sha256,
            scanned_page_count=material.scanned_page_count,
            readable_page_count=len(material.bundle.pages),
            unreadable_page_locators=material.unreadable_page_locators,
            planned_target_count=sum(len(batch.field_ids) for batch in batches),
            batch_count=len(batches),
            calls=tuple(call_receipts),
            fields=tuple(field_receipts),
        )
        return _ProductExecutionResult(
            product=output_product,
            audit=product_audit,
            attempt_timings=tuple(attempt_timings),
        )

    works = tuple(
        ProductWork(
            ordinal=index,
            product_version_id=product.product_version_id,
            payload=product,
        )
        for index, product in enumerate(baseline.products)
    )
    with timer.stage("provider"):
        execution = execute_products_ordered(
            works,
            worker=execute_product,
            profile=effective_profile,
        )
    output_products = [item.product for item in execution.values]
    product_audits = [item.audit for item in execution.values]
    attempt_timings = tuple(
        timing for item in execution.values for timing in item.attempt_timings
    )

    with timer.stage("merge_write"):
        finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        run = seal_provider_trial_run(
            provider=ProviderIdentity(),
            products=tuple(output_products),
            started_at=started_at,
            finished_at=finished_at,
        )
        write_provider_trial_run(output_path, run)
        metrics = _metrics(baseline, output_products, product_audits)
    performance = timer.finish(
        peak_product_workers=execution.peak_products,
        peak_provider_calls=gate.peak_active,
        product_timings=execution.product_timings,
        provider_attempts=attempt_timings,
        throttle_events=gate.throttle_events,
    )
    audit_payload = {
        "contract": "insurance-v5-m152-gapfill-audit.v1",
        "baseline_file_sha256": M152_BASELINE_SHA256,
        "baseline_run_sha256": baseline.run_sha256,
        "result_run_sha256": run.run_sha256,
        "catalog_sha256": baseline.catalog_sha256,
        "workbook_sha256": dict(M152_WORKBOOK_SHA256),
        "provider": ProviderIdentity().model_dump(mode="json"),
        "max_calls": M152_MAX_CALLS,
        "prior_failed_call_count": prior_failed_call_count,
        "call_count": budget.used,
        "mission_call_count": prior_failed_call_count + budget.used,
        "started_at": started_at,
        "finished_at": finished_at,
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "performance": performance.model_dump(mode="json"),
        "metrics": metrics.model_dump(mode="json"),
        "products": [product.model_dump(mode="json") for product in product_audits],
    }
    audit = M152RunAudit(
        contract="insurance-v5-m152-gapfill-audit.v1",
        artifact_sha256=_canonical_digest(
            "insurance-v5-m152-gapfill-audit.v1", audit_payload
        ),
        baseline_file_sha256=M152_BASELINE_SHA256,
        baseline_run_sha256=baseline.run_sha256,
        result_run_sha256=run.run_sha256,
        catalog_sha256=baseline.catalog_sha256,
        workbook_sha256=dict(M152_WORKBOOK_SHA256),
        provider=ProviderIdentity(),
        max_calls=M152_MAX_CALLS,
        prior_failed_call_count=prior_failed_call_count,
        call_count=budget.used,
        mission_call_count=prior_failed_call_count + budget.used,
        started_at=started_at,
        finished_at=finished_at,
        serving_effect="NONE",
        review_publish_admission=False,
        performance=performance,
        metrics=metrics,
        products=tuple(product_audits),
    )
    _write_audit(audit_output_path, audit)
    return run, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission 152 bounded eight-product gapfill")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--serious-illness-root", type=Path, required=True)
    parser.add_argument("--supplemental-root-596", type=Path, required=True)
    parser.add_argument("--business-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--prior-failed-calls", type=int, default=0)
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    if not 0 <= args.prior_failed_calls < M152_MAX_CALLS:
        raise SystemExit("M152_PRIOR_CALL_COUNT_INVALID")
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit("M152_PROVIDER_API_KEY_NOT_CONFIGURED")

    def completion_factory() -> OpenAICompatibleCompletion:
        return OpenAICompatibleCompletion(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model="qwen-plus",
            model_family="qwen",
            timeout_seconds=240.0,
            max_calls=M152_MAX_CALLS - args.prior_failed_calls,
        )

    run, audit = run_m152(
        baseline_path=args.baseline,
        sample_root=args.sample_root,
        serious_illness_root=args.serious_illness_root,
        supplemental_root_596=args.supplemental_root_596,
        business_root=args.business_root,
        output_path=args.output,
        audit_output_path=args.audit_output,
        completion_factory=completion_factory,
        concurrency_profile=ProductConcurrencyProfile(
            max_products=args.max_product_concurrency
        ),
        prior_failed_call_count=args.prior_failed_calls,
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_sha256": run.run_sha256,
                "call_count": audit.call_count,
                "mission_call_count": audit.mission_call_count,
                "metrics": audit.metrics.model_dump(mode="json"),
                "output": str(args.output.resolve()),
                "audit_output": str(args.audit_output.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "M152FieldIssue",
    "M152FieldReceipt",
    "M152Metrics",
    "M152RunAudit",
    "load_m152_audit",
    "merge_m152_batch",
    "preserve_unreviewed_absences",
    "run_m152",
    "split_target_batches",
]
