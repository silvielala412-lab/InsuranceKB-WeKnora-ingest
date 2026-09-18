"""Shared provider-trial contracts and admission limits.

This module owns the serialized run boundary used by all V5 evaluation runners.
It deliberately has no orchestration or filesystem dependencies so runners can
share the same contract without importing the provider-trial entry point.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import V5CandidatePreview
from .material_support import MaterialSupportDecision, MaterialSupportMetrics

MAX_MICROBATCH_PROVIDER_CALLS: Final = 32
MAX_MICROBATCH_PRODUCT_ATTEMPTS: Final = 12
_REVIEW_REQUIRED_ERRORS: Final[frozenset[str]] = frozenset(
    {"EVIDENCE_REVIEW_REQUIRED", "EXTRACTION_GAP_REVIEW_REQUIRED"}
)


class ProviderTrialError(ValueError):
    """A frozen source, provider response or local artifact is not admissible."""


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceFileReceipt(_ClosedModel):
    file_name: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_count: Annotated[int, Field(ge=1)]


class ProviderIdentity(_ClosedModel):
    family: Literal["qwen"] = "qwen"
    base_url: Literal["https://dashscope.aliyuncs.com/compatible-mode/v1"] = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model: Literal["qwen-plus"] = "qwen-plus"
    mode: Literal["streaming-non-thinking-json"] = "streaming-non-thinking-json"


class ProviderAttemptReceipt(_ClosedModel):
    attempt: Annotated[int, Field(ge=1, le=MAX_MICROBATCH_PRODUCT_ATTEMPTS)]
    outcome: Literal[
        "ACCEPTED",
        "PRESERVED",
        "REJECTED",
        "ERROR",
        "REPAIR_REJECTED",
    ]
    response_id: str | None
    response_model: str | None
    finish_reason: str | None
    prompt_tokens: Annotated[int, Field(ge=0)] | None
    completion_tokens: Annotated[int, Field(ge=0)] | None
    total_tokens: Annotated[int, Field(ge=0)] | None
    error_code: str | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "ACCEPTED" and self.error_code is not None:
            raise ValueError("accepted attempt cannot contain error")
        if self.outcome == "PRESERVED" and self.error_code not in _REVIEW_REQUIRED_ERRORS:
            raise ValueError("preserved attempt requires Evidence review error")
        if self.outcome == "REPAIR_REJECTED" and (self.attempt < 2 or not self.error_code):
            raise ValueError("repair rejection requires second attempt and error")
        if self.outcome in {"REJECTED", "ERROR"} and not self.error_code:
            raise ValueError("failed attempt requires error")
        return self


class ProviderTrialProduct(_ClosedModel):
    product_id: Annotated[str, Field(min_length=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    product_display_name: Annotated[str, Field(min_length=1)]
    insurance_class: Annotated[str, Field(min_length=1)]
    schema_id: Annotated[str, Field(min_length=1)]
    source_revision_id: Annotated[str, Field(min_length=1)]
    source_manifest_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    status: Literal["SUCCESS", "REVIEW_REQUIRED", "FAILED"]
    error_code: str | None
    files: Annotated[tuple[SourceFileReceipt, ...], Field(min_length=1)]
    attempts: Annotated[
        tuple[ProviderAttemptReceipt, ...],
        Field(min_length=1, max_length=MAX_MICROBATCH_PRODUCT_ATTEMPTS),
    ]
    preview: V5CandidatePreview | None
    material_support: tuple[MaterialSupportDecision, ...] = ()
    material_support_metrics: MaterialSupportMetrics | None = None

    @model_validator(mode="after")
    def validate_product_result(self) -> Self:
        if tuple(attempt.attempt for attempt in self.attempts) != tuple(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("attempt order invalid")
        if self.status in {"SUCCESS", "REVIEW_REQUIRED"}:
            expected_outcome = "ACCEPTED" if self.status == "SUCCESS" else "PRESERVED"
            expected_errors = {None} if self.status == "SUCCESS" else _REVIEW_REQUIRED_ERRORS
            if self.error_code not in expected_errors or self.preview is None:
                raise ValueError("preview product status is inconsistent")
            allowed_outcomes = (
                {expected_outcome, "REPAIR_REJECTED"}
                if self.status == "REVIEW_REQUIRED"
                else {expected_outcome}
            )
            if self.attempts[-1].outcome not in allowed_outcomes:
                raise ValueError("preview product attempt outcome is inconsistent")
            if (
                self.preview.product_id != self.product_id
                or self.preview.product_version_id != self.product_version_id
                or self.preview.product_display_name != self.product_display_name
                or self.preview.insurance_class != self.insurance_class
                or self.preview.schema_id != self.schema_id
                or self.preview.source_revision_id != self.source_revision_id
            ):
                raise ValueError("preview identity drift")
        elif self.error_code is None or self.preview is not None:
            raise ValueError("failed product requires typed error and no preview")
        return self


class V5ProviderTrialRun(_ClosedModel):
    contract: Literal["insurance-v5-provider-trial-run.v2"]
    run_id: Annotated[str, Field(min_length=1)]
    run_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    catalog_id: Literal["insurance-product-schema-v5"]
    catalog_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    status: Literal["COMPLETED", "PARTIAL", "FAILED"]
    provider: ProviderIdentity
    call_count: Annotated[int, Field(ge=1, le=MAX_MICROBATCH_PROVIDER_CALLS)]
    started_at: Annotated[str, Field(min_length=1)]
    finished_at: Annotated[str, Field(min_length=1)]
    serving_effect: Literal["NONE"]
    review_publish_admission: Literal[False]
    products: Annotated[tuple[ProviderTrialProduct, ...], Field(min_length=1, max_length=9)]

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        expected_calls = sum(len(product.attempts) for product in self.products)
        if self.call_count != expected_calls:
            raise ValueError("provider call count drift")
        preview_count = sum(product.preview is not None for product in self.products)
        expected_status = (
            "COMPLETED"
            if preview_count == len(self.products)
            else "PARTIAL"
            if preview_count
            else "FAILED"
        )
        if self.status != expected_status:
            raise ValueError("run status drift")
        versions = [product.product_version_id for product in self.products]
        if len(set(versions)) != len(versions):
            raise ValueError("duplicate product version")
        return self


__all__ = [
    "MAX_MICROBATCH_PRODUCT_ATTEMPTS",
    "MAX_MICROBATCH_PROVIDER_CALLS",
    "ProviderAttemptReceipt",
    "ProviderIdentity",
    "ProviderTrialError",
    "ProviderTrialProduct",
    "SourceFileReceipt",
    "V5ProviderTrialRun",
]
