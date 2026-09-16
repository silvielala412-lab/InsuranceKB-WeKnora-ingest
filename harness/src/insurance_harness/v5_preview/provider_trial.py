from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import httpx
import pdfplumber
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .catalog import catalog_sha256, load_v5_catalog
from .contracts import (
    EvidenceResolution,
    IngestRequest,
    InsuranceSchema,
    V5CandidatePreview,
)
from .dynamic_ingest import (
    MetadataMappingPlugin,
    build_candidate_source_text,
    build_field_micro_batches,
    build_full_material_field_source_text,
    locate_field_candidates,
)
from .ingest import (
    IngestPluginRegistry,
    PreviewCompilationError,
    V5IngestPlugin,
    V5PreviewCompiler,
    merge_candidate_previews,
    validate_preview_digest,
)
from .llm_plugin import (
    CompletionReceipt,
    LlmPluginError,
    OpenAICompatibleCompletion,
    SchemaGuidedLlmPlugin,
)
from .material_support import (
    MaterialSupportDecision,
    MaterialSupportMetrics,
    classify_material_support,
    compute_material_supported_extraction_rate,
    is_pdf_extractable_field,
)
from .ocr import BAILIAN_OCR_MODEL, BailianOcrClient, OcrPageReceipt

BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BAILIAN_MODEL = "qwen-plus"
MAX_PROVIDER_CALLS = 18
MAX_PRODUCT_ATTEMPTS = 2
# Mission 158 uses a bounded 32-call envelope. Keep the contract aligned with
# the approved provider budget so a valid 31/32-call local preview can seal.
MAX_MICROBATCH_PROVIDER_CALLS = 32
MAX_MICROBATCH_PRODUCT_ATTEMPTS = 12
M143_SEMANTIC_TARGET_FIELD_IDS: tuple[str, ...] = (
    "premium_grace_period",
    "product_conversion_rules",
    "premium_adjustment_rules",
)
M144_CONTENT_SYNTHESIS_FIELD_IDS: tuple[str, ...] = (
    "product_summary",
    "product_overview",
)
M146_SERVICE_FIELD_IDS: tuple[str, ...] = (
    "policyholder_rights",
    "eligible_service_packages",
    "medical_service_benefits",
    "product_faq",
)
_REVIEW_REQUIRED_ERRORS = {
    "EVIDENCE_REVIEW_REQUIRED",
    "EXTRACTION_GAP_REVIEW_REQUIRED",
}
_MAX_PREPARED_SOURCE_CHARACTERS = 200_000


class ProviderTrialError(ValueError):
    """A frozen source, provider response or local artifact is not admissible."""


@dataclass(frozen=True, slots=True)
class ApprovedPdf:
    file_name: str
    sha256: str
    page_count: int


@dataclass(frozen=True, slots=True)
class ApprovedProduct:
    directory_name: str
    metadata_sha256: str
    product_id: str
    product_version_id: str
    product_display_name: str
    insurance_class: str
    pdfs: tuple[ApprovedPdf, ...]


M146_SUPPLEMENTAL_PDFS: tuple[ApprovedPdf, ...] = (
    ApprovedPdf(
        "安有医健康服务手册（尊享版）.pdf",
        "9c9c6343fd0333084345376bec52bf30d2692a7e23ea98fb04a5722a8fa8f8be",
        60,
    ),
    ApprovedPdf(
        "平安添瑞·安有医（安医保尊享版）一页纸.pdf",
        "fa52b05bcf8561fa82d4c24db34585870a4b014f2315e742a9c43db41f91fead",
        2,
    ),
)


APPROVED_PRODUCTS: tuple[ApprovedProduct, ...] = (
    ApprovedProduct(
        directory_name="平安e生保（尊享版）医疗保险",
        metadata_sha256="0550999d9541722a38173ad25396878f0c9b3592dd590dd9999ad3f7d1b82979",
        product_id="596",
        product_version_id="596-1",
        product_display_name="平安e生保（尊享版）医疗保险",
        insurance_class="医疗险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "5e2aef32d319b5aca6d37268e99ee5252ea0c7a56885b1e4dfa1ebb0308e4279",
                27,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "88b784c61f52a2e21a2a12f96ba5d73412de95e68a4453af03a27e8ab1245edc",
                39,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "7b35fa3b0e1820860dafc2fec9858949d387f2aab19006d3d3e02b92e0bb75fb",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安创享盛世金越（尊享版26）终身寿险（分红型）",
        metadata_sha256="02f2ff44cb5481852b3ea495f4822030cccd7ac42762433d2bc1df8460b071d0",
        product_id="5003",
        product_version_id="5003-1",
        product_display_name="平安创享盛世金越（尊享版26）终身寿险（分红型）",
        insurance_class="终身寿险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "38720048d356a9c0ece11c8cf35f175d3bd98115ad76c39533e7610db1823c80",
                10,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "b2260a6162930fc01341ac988aa830116c6092efca079926556b3ce58d3718de",
                15,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "ac99d646fe63e8256c65dc0c38513cd03fe7001f446ee7f1fdfd2beb6fb8ebbf",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安守护百分百（2026）两全保险",
        metadata_sha256="e6f62472a211d408d02361e29117af0807a3d2c26c7277393b5b0d4827fd30cb",
        product_id="1826",
        product_version_id="1826-1",
        product_display_name="平安守护百分百（2026）两全保险",
        insurance_class="两全保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "d4c9611b7a0b0f59e9b37aef6ff0e5d12d42b00ba20daff670630f2d04e5c08a",
                7,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "829346499a67156e77e2778a4c5542e88456f8918beda055162f85ab3a30d007",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "9ea421ad68d443e5e6572b7c2c91fcd2302ab18103a7b85f733c0ea29439ea19",
                6,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安e生保（惠享版）长期医疗保险（费率可调）",
        metadata_sha256="9bdde7c27c56b9034c88cce1ff288b1681cf6e3986a338c5ed3a3db0793c3c1d",
        product_id="594",
        product_version_id="594-1",
        product_display_name="平安e生保（惠享版）长期医疗保险（费率可调）",
        insurance_class="医疗险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "3c7b24cd12e1c6bb04c714be511077f85fa6e5c820ed18dde3f025e9e71b320f",
                17,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "7bfac182fe11866e9d4c6f2b970a3a56db79833476f51e83ddcafe127b4c9ce5",
                44,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "fbc9adca68254427541afa594508f7b2e9c75d7c9b23b4804f9436a3a35a0f44",
                7,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安爱满分（2026）两全保险",
        metadata_sha256="4cd29c76d84104720ba4a8be72372d3e0442b4c548de648e1e083cd8fc50ad17",
        product_id="1818",
        product_version_id="1818-1",
        product_display_name="平安爱满分（2026）两全保险",
        insurance_class="两全保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "d2119896e15b0fed076db80a2f780fd08ffd2498b260eb95fc7f1957c5169208",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "2e31eaf4dd259c4a04c04d5870bc6f6fdc2f4e3019d2d93b273db3f4a16bb932",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "48f4e5ba20c270947e9473a95bf12f4861d0ec6d3d9625565c94ac4f08e79ac4",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安盛世金越（尊享版26）终身寿险",
        metadata_sha256="ec2cff56d3f67946272ffa45f10cac5bb29ca217c81460bbed808a4b610fc8d5",
        product_id="1824",
        product_version_id="1824-1",
        product_display_name="平安盛世金越（尊享版26）终身寿险",
        insurance_class="终身寿险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "a484e0757d1989ef2fd3f3700273a081b30f026547b4f965a77854c028a713f6",
                7,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "42c9536acddd41d77e3d56e238bb47060cb36ac96a798317d875ec51cd967911",
                9,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "9811367acd0d3875260e926fe64901e3423c07569ae06bf1438926769860c66f",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安盛世金越（至尊版26）年金保险（分红型）",
        metadata_sha256="3b48b3d24151b7e972b21940321fd8a18e572e7964c891510bab022218a0f96b",
        product_id="1830",
        product_version_id="1830-2",
        product_display_name="平安盛世金越（至尊版26）年金保险（分红型）",
        insurance_class="年金险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "7025fd26e5c6e37c3f861a46036935bbc516b747a3f9074199599deed4afd5be",
                10,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "ad56b02e0c25599e26cd409f9d5e216af9582ea95967ec81a14a236043b59c8c",
                11,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "bf8951ca84880229cef503191ce78db14b16fdfa4313dfb4deccfd4ff96683e9",
                68,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安附加（2026）意外伤害保险",
        metadata_sha256="75e2c64f92760dd73f195f40254919f8f6e7908f8e26d619ca2f30b3db3ffca5",
        product_id="1814",
        product_version_id="1814-1",
        product_display_name="平安附加（2026）意外伤害保险",
        insurance_class="意外险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "68105656802ea7ad267d9d1def1f78c1fb706a807bc75fc93ba8ef1aeae83abf",
                12,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "0ef33683ec95d5b0976cf6b567956333aedf32eaf5f49aeae7012b00d50b795c",
                12,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "72224c36ed2455365fcbcd361444d3f26b50ee88d62aba7673d41525c27b99c7",
                10,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安附加（2026）失能收入损失保险",
        metadata_sha256="23c1a56861c1141a4c0388afdeab307e12ca28a2cffa50f613a478810530034c",
        product_id="1816",
        product_version_id="1816-1",
        product_display_name="平安附加（2026）失能收入损失保险",
        insurance_class="失能收入损失保险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "c156596bb234188ec324a5a9e56efb905e91804ee5bc29fd4ece1bc62dbc7db7",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "5da2822c7367682d64d7f2f2b4b5564891018a0ee714a464fb45833f6c4b492f",
                44,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "b081ec26d0f318921c0374bdf86da3a13e057c1b4fa41cb46fa8e6c53d95043a",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安安佑福（全能版）重大疾病保险",
        metadata_sha256="6842f82ada88bc4780a227633a96bbff793411875068898a99e65b7f7486aac6",
        product_id="1828",
        product_version_id="1828-1",
        product_display_name="平安安佑福（全能版）重大疾病保险",
        insurance_class="重疾险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "1c3e868b8d2acbf018087af5e345f70f0a934f94e75c2dc5a09fd9c41190b933",
                11,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "d68c2d3f88af277b392d4c8f3f8665620b9873a31d8411ce5e1763b8e129d474",
                43,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "600e95faf04a8268c90a2a0d08448c140b8a323f6e24bccfce186d96e0c9aa52",
                2,
            ),
        ),
    ),
    ApprovedProduct(
        directory_name="平安个人重大疾病保险",
        metadata_sha256="c26c39d72186e6c13ebc351e9cf87b7f9598adcb58d7846936abcad9f880e228",
        product_id="L2332",
        product_version_id="L2332-1",
        product_display_name="平安个人重大疾病保险",
        insurance_class="重疾险",
        pdfs=(
            ApprovedPdf(
                "产品说明书.pdf",
                "ce551adb217da6f3b54600d7523888c848145f54c9fa5012a73c30b8996db6a3",
                8,
            ),
            ApprovedPdf(
                "保险条款.pdf",
                "3964e686450e7b5bf332965f120397cda58ac55780b1b9ba68c37fc3dfe77d45",
                33,
            ),
            ApprovedPdf(
                "费率表.pdf",
                "ac288709d7dc4be2984f550df68f063a0aebfdf533acd975fdce56693817d297",
                1,
            ),
        ),
    ),
)

M140_PRODUCT_IDS: tuple[str, ...] = ("596", "5003", "1826")
_EXPECTED_SCHEMA_FIELDS_BY_CLASS: Mapping[str, int] = {
    "医疗险": 67,
    "终身寿险": 75,
    "两全保险": 79,
    "年金险": 82,
    "意外险": 62,
    "失能收入损失保险": 76,
    "重疾险": 67,
}


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourcePage(_ClosedModel):
    document_name: Annotated[str, Field(min_length=1)]
    document_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_number: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1)]


class SourceFileReceipt(_ClosedModel):
    file_name: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_count: Annotated[int, Field(ge=1)]


class ProviderIdentity(_ClosedModel):
    family: Literal["qwen"] = "qwen"
    base_url: Literal[
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
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
        if self.outcome == "REPAIR_REJECTED" and (
            self.attempt < 2 or not self.error_code
        ):
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
            expected_outcome = (
                "ACCEPTED" if self.status == "SUCCESS" else "PRESERVED"
            )
            expected_errors = (
                {None} if self.status == "SUCCESS" else _REVIEW_REQUIRED_ERRORS
            )
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


def _preview_counts(preview: V5CandidatePreview | None) -> dict[str, int]:
    if preview is None:
        return {
            "fields": 0,
            "present": 0,
            "absent_explicitly": 0,
            "unknown": 0,
            "evidence_total": 0,
            "verified": 0,
            "normalized": 0,
            "unresolved": 0,
            "ambiguous": 0,
        }
    evidence = [item for field in preview.fields for item in field.evidence]
    return {
        "fields": len(preview.fields),
        "present": sum(field.state == "present" for field in preview.fields),
        "absent_explicitly": sum(
            field.state == "absent_explicitly" for field in preview.fields
        ),
        "unknown": sum(field.state == "unknown" for field in preview.fields),
        "evidence_total": len(evidence),
        "verified": sum(item.verification_status == "VERIFIED" for item in evidence),
        "normalized": sum(
            item.verification_status == "NORMALIZED_MATCH" for item in evidence
        ),
        "unresolved": sum(
            item.verification_status == "UNRESOLVED" for item in evidence
        ),
        "ambiguous": sum(
            item.verification_status == "AMBIGUOUS" for item in evidence
        ),
    }


def _material_support_for_product(
    *,
    prepared: PreparedProduct,
    schema: InsuranceSchema,
    preview: V5CandidatePreview | None,
) -> tuple[tuple[MaterialSupportDecision, ...], MaterialSupportMetrics | None]:
    """Build source-support diagnostics after extraction, without changing states."""

    if preview is None:
        return (), None
    supplemental_ids = (
        set(M146_SERVICE_FIELD_IDS) if prepared.supplemental_pages else set()
    )
    base_extractable_ids = tuple(
        field.field_id
        for field in schema.fields
        if is_pdf_extractable_field(field)
    )
    base_located = locate_field_candidates(
        prepared.base_pages,
        schema,
        base_extractable_ids,
    )
    base_candidate_locators = {
        field_id: tuple(candidate.locator for candidate in candidates)
        for field_id, candidates in base_located.items()
    }
    supplemental_located = (
        locate_field_candidates(
            prepared.supplemental_pages,
            schema,
            tuple(
                field.field_id
                for field in schema.fields
                if field.field_id in supplemental_ids
            ),
        )
        if supplemental_ids
        else {}
    )
    decisions = tuple(
        classify_material_support(
            field,
            (
                prepared.pages
                if field.field_id in supplemental_ids
                else prepared.base_pages
            ),
            (
                (
                    *base_candidate_locators.get(field.field_id, ()),
                    *tuple(
                        candidate.locator
                        for candidate in supplemental_located.get(field.field_id, ())
                    ),
                )
                if field.field_id in supplemental_ids
                else base_candidate_locators.get(field.field_id, ())
            ),
            allow_external_source=field.field_id in supplemental_ids,
        )
        for field in schema.fields
    )
    return decisions, compute_material_supported_extraction_rate(preview, decisions)


def compare_provider_trials(
    baseline: V5ProviderTrialRun,
    adaptive: V5ProviderTrialRun,
) -> tuple[dict[str, object], ...]:
    """Compare exact product versions without treating either run as approval."""
    baseline_by_version = {product.product_version_id: product for product in baseline.products}
    adaptive_by_version = {product.product_version_id: product for product in adaptive.products}
    if set(baseline_by_version) != set(adaptive_by_version):
        raise ProviderTrialError("M126_COMPARISON_PRODUCT_SET_DRIFT")
    comparison: list[dict[str, object]] = []
    for version in sorted(baseline_by_version):
        before = _preview_counts(baseline_by_version[version].preview)
        after = _preview_counts(adaptive_by_version[version].preview)
        comparison.append(
            {
                "product_version_id": version,
                "baseline_status": baseline_by_version[version].status,
                "adaptive_status": adaptive_by_version[version].status,
                "baseline": before,
                "adaptive": after,
                "delta": {
                    key: after[key] - before[key]
                    for key in before
                },
                "baseline_run_sha256": baseline.run_sha256,
                "adaptive_run_sha256": adaptive.run_sha256,
                "serving_effect": "NONE",
                "review_publish_admission": False,
            }
        )
    return tuple(comparison)


@dataclass(frozen=True, slots=True)
class PreparedProduct:
    approved: ApprovedProduct
    source_revision_id: str
    source_manifest_sha256: str
    files: tuple[SourceFileReceipt, ...]
    pages: tuple[SourcePage, ...]
    base_pages: tuple[SourcePage, ...]
    supplemental_pages: tuple[SourcePage, ...]
    source_text: str
    metadata: Mapping[str, object]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(domain: str, payload: object) -> str:
    encoded = json.dumps(
        {"domain": domain, "payload": payload},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _read_pdf_pages(path: Path) -> tuple[str, ...]:
    with pdfplumber.open(path) as document:
        return tuple(page.extract_text() or "" for page in document.pages)


def load_frozen_pdf_pages(
    path: Path,
    spec: ApprovedPdf,
    *,
    page_reader: Callable[[Path], tuple[str, ...]] = _read_pdf_pages,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> tuple[SourceFileReceipt, tuple[SourcePage, ...]]:
    if path.name != spec.file_name or not path.is_file():
        raise ProviderTrialError("V5_SOURCE_FILE_MISSING")
    actual_sha256 = _sha256_bytes(path.read_bytes())
    if actual_sha256 != spec.sha256:
        raise ProviderTrialError("V5_SOURCE_SHA256_DRIFT")
    texts = page_reader(path)
    if len(texts) != spec.page_count:
        raise ProviderTrialError("V5_SOURCE_PAGE_COUNT_DRIFT")
    if ocr_page_reader is not None:
        texts = tuple(
            text if text.strip() else ocr_page_reader(path, page_number)
            for page_number, text in enumerate(texts, 1)
        )
    if any(not text.strip() for text in texts):
        raise ProviderTrialError("V5_SOURCE_PAGE_TEXT_MISSING")
    receipt = SourceFileReceipt(
        file_name=spec.file_name,
        sha256=spec.sha256,
        page_count=spec.page_count,
    )
    pages = tuple(
        SourcePage(
            document_name=spec.file_name,
            document_sha256=spec.sha256,
            page_number=index,
            text=text,
        )
        for index, text in enumerate(texts, 1)
    )
    return receipt, pages


def build_source_text(pages: Sequence[SourcePage]) -> str:
    return "\n\n".join(
        f"【文档：{page.document_name}｜页码：{page.page_number}】\n{page.text}"
        for page in pages
    )


def build_m146_repair_source_text(
    *,
    base_pages: Sequence[SourcePage],
    supplemental_pages: Sequence[SourcePage],
    schema: InsuranceSchema,
    target_field_ids: Sequence[str],
    max_characters: int = 100_000,
) -> str:
    """Build a repair prompt that cannot leak service sources into other fields."""

    definitions = {field.field_id for field in schema.fields}
    requested = tuple(target_field_ids)
    if (
        not requested
        or len(set(requested)) != len(requested)
        or any(field_id not in definitions for field_id in requested)
    ):
        raise ProviderTrialError("M146_REPAIR_FIELD_SET_INVALID")
    service_ids = tuple(
        field_id for field_id in requested if field_id in M146_SERVICE_FIELD_IDS
    )
    base_ids = tuple(
        field_id for field_id in requested if field_id not in M146_SERVICE_FIELD_IDS
    )
    sections: list[str] = []
    if base_ids:
        sections.append(
            build_candidate_source_text(
                base_pages,
                schema,
                base_ids,
                max_pages=24,
                max_characters=55_000,
            )
        )
    if service_ids:
        service_header = (
            "【M146 服务补充材料仅用于："
            + ",".join(service_ids)
            + "；禁止据此改写其他字段】"
        )
        service_text = build_full_material_field_source_text(
            supplemental_pages,
            schema,
            service_ids,
            max_characters=42_000,
        )
        sections.append(f"{service_header}\n{service_text}")
    return "\n\n".join(section for section in sections if section)[:max_characters]


def _normalized_evidence_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _page_locator(page: SourcePage) -> str:
    return f"pdf:{page.document_name}#page={page.page_number}"


def _select_advisory_page(
    matches: Sequence[SourcePage], advisory_locator: str
) -> SourcePage | None:
    return next(
        (page for page in matches if _page_locator(page) == advisory_locator),
        None,
    )


def classify_evidence(
    pages: Sequence[SourcePage],
    quote: str,
    advisory_locator: str,
) -> EvidenceResolution:
    exact_matches = [page for page in pages if quote in page.text]
    if exact_matches:
        selected = (
            exact_matches[0]
            if len(exact_matches) == 1
            else _select_advisory_page(exact_matches, advisory_locator)
        )
        if selected is not None:
            return EvidenceResolution(
                locator=_page_locator(selected),
                verification_status="VERIFIED",
            )
        return EvidenceResolution(
            locator=advisory_locator,
            verification_status="AMBIGUOUS",
            verification_error="V5_EVIDENCE_PAGE_AMBIGUOUS",
        )

    normalized_quote = _normalized_evidence_text(quote)
    normalized_matches = [
        page
        for page in pages
        if normalized_quote
        and normalized_quote in _normalized_evidence_text(page.text)
    ]
    if normalized_matches:
        selected = (
            normalized_matches[0]
            if len(normalized_matches) == 1
            else _select_advisory_page(normalized_matches, advisory_locator)
        )
        if selected is not None:
            return EvidenceResolution(
                locator=_page_locator(selected),
                verification_status="NORMALIZED_MATCH",
            )
        return EvidenceResolution(
            locator=advisory_locator,
            verification_status="AMBIGUOUS",
            verification_error="V5_EVIDENCE_PAGE_AMBIGUOUS",
        )

    return EvidenceResolution(
        locator=advisory_locator,
        verification_status="UNRESOLVED",
        verification_error="V5_EVIDENCE_PAGE_NOT_FOUND",
    )


def resolve_evidence_locator(
    pages: Sequence[SourcePage],
    quote: str,
    advisory_locator: str | None = None,
) -> str:
    resolution = classify_evidence(
        pages,
        quote,
        advisory_locator or "unresolved:evidence",
    )
    if resolution.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}:
        return resolution.locator
    raise ProviderTrialError(
        resolution.verification_error or "V5_EVIDENCE_PAGE_NOT_FOUND"
    )


def prepare_approved_product(
    root: Path,
    approved: ApprovedProduct,
    *,
    supplemental_root_596: Path | None = None,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> PreparedProduct:
    folder = root / approved.directory_name
    expected_names = {"product_meta.json", *(pdf.file_name for pdf in approved.pdfs)}
    actual_names = (
        {path.name for path in folder.iterdir() if path.is_file()}
        if folder.is_dir()
        else set()
    )
    if actual_names != expected_names:
        raise ProviderTrialError("V5_SOURCE_SET_DRIFT")
    metadata_path = folder / "product_meta.json"
    metadata_bytes = metadata_path.read_bytes()
    if _sha256_bytes(metadata_bytes) != approved.metadata_sha256:
        raise ProviderTrialError("V5_SOURCE_METADATA_SHA256_DRIFT")
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderTrialError("V5_SOURCE_METADATA_INVALID") from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("planCode") != approved.product_id
        or metadata.get("versionNo") != approved.product_version_id
        or metadata.get("clauseName") != approved.product_display_name
    ):
        raise ProviderTrialError("V5_SOURCE_PRODUCT_IDENTITY_DRIFT")

    files: list[SourceFileReceipt] = []
    base_pages: list[SourcePage] = []
    for pdf in approved.pdfs:
        receipt, pdf_pages = load_frozen_pdf_pages(folder / pdf.file_name, pdf)
        files.append(receipt)
        base_pages.extend(pdf_pages)
    supplemental_pages: list[SourcePage] = []
    if supplemental_root_596 is not None and approved.product_id == "596":
        expected_supplement_names = {pdf.file_name for pdf in M146_SUPPLEMENTAL_PDFS}
        actual_supplement_names = (
            {
                path.name
                for path in supplemental_root_596.iterdir()
                if path.is_file()
            }
            if supplemental_root_596.is_dir()
            else set()
        )
        if actual_supplement_names != expected_supplement_names:
            raise ProviderTrialError("M146_SUPPLEMENTAL_SOURCE_SET_DRIFT")
        for pdf in M146_SUPPLEMENTAL_PDFS:
            receipt, pdf_pages = load_frozen_pdf_pages(
                supplemental_root_596 / pdf.file_name,
                pdf,
                ocr_page_reader=ocr_page_reader,
            )
            files.append(receipt)
            supplemental_pages.extend(pdf_pages)
    pages = [*base_pages, *supplemental_pages]
    manifest_payload = {
        "metadata_sha256": approved.metadata_sha256,
        "product_id": approved.product_id,
        "product_version_id": approved.product_version_id,
        "product_display_name": approved.product_display_name,
        "insurance_class": approved.insurance_class,
        "files": [file.model_dump(mode="json") for file in files],
        "supplemental_field_ids": (
            list(M146_SERVICE_FIELD_IDS) if supplemental_pages else []
        ),
        "page_text_sha256": _canonical_digest(
            "v5-provider-page-text.v1",
            [
                {
                    "document_name": page.document_name,
                    "page_number": page.page_number,
                    "text": page.text,
                }
                for page in pages
            ],
        ),
    }
    manifest_sha256 = _canonical_digest("v5-provider-source-manifest.v1", manifest_payload)
    # Supplemental service material is intentionally excluded from the primary
    # all-field prompt. It is exposed only in the scoped repair context below.
    source_text = build_source_text(base_pages)
    if len(source_text) > _MAX_PREPARED_SOURCE_CHARACTERS:
        schema = load_v5_catalog().schema_for(approved.insurance_class)
        eligible_field_ids = tuple(
            field.field_id
            for field in schema.fields
            if is_pdf_extractable_field(field)
        )
        source_text = build_candidate_source_text(
            base_pages,
            schema,
            eligible_field_ids,
            max_pages=36,
            max_characters=180_000,
            max_pages_per_field=8,
            snippet_characters=1_000,
        )
    if len(source_text) > _MAX_PREPARED_SOURCE_CHARACTERS:
        raise ProviderTrialError("V5_BOUNDED_SOURCE_TEXT_TOO_LARGE")
    return PreparedProduct(
        approved=approved,
        source_revision_id=f"v5-source-{manifest_sha256}",
        source_manifest_sha256=manifest_sha256,
        files=tuple(files),
        pages=tuple(pages),
        base_pages=tuple(base_pages),
        supplemental_pages=tuple(supplemental_pages),
        source_text=source_text,
        metadata=metadata,
    )


def prepare_approved_products(
    root: Path,
    *,
    approved_products: Sequence[ApprovedProduct] = APPROVED_PRODUCTS,
    supplemental_root_596: Path | None = None,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> tuple[PreparedProduct, ...]:
    selected = tuple(approved_products)
    if not selected or len({item.product_version_id for item in selected}) != len(selected):
        raise ProviderTrialError("V5_APPROVED_PRODUCT_SET_INVALID")
    prepared = tuple(
        prepare_approved_product(
            root,
            item,
            supplemental_root_596=supplemental_root_596,
            ocr_page_reader=ocr_page_reader,
        )
        for item in selected
    )
    catalog = load_v5_catalog()
    expected = tuple(
        _EXPECTED_SCHEMA_FIELDS_BY_CLASS[item.approved.insurance_class]
        for item in prepared
    )
    actual = tuple(
        len(catalog.schema_for(item.approved.insurance_class).fields) for item in prepared
    )
    if actual != expected:
        raise ProviderTrialError("V5_APPROVED_SCHEMA_TOPOLOGY_DRIFT")
    return prepared


def _run_digest(payload: dict[str, object]) -> str:
    return _canonical_digest("insurance-v5-provider-trial-run.v2", payload)


def seal_provider_trial_run(
    *,
    provider: ProviderIdentity,
    products: tuple[ProviderTrialProduct, ...],
    started_at: str,
    finished_at: str,
) -> V5ProviderTrialRun:
    catalog = load_v5_catalog()
    preview_count = sum(product.preview is not None for product in products)
    status: Literal["COMPLETED", "PARTIAL", "FAILED"] = (
        "COMPLETED"
        if preview_count == len(products)
        else "PARTIAL"
        if preview_count
        else "FAILED"
    )
    run_id_seed = _canonical_digest(
        "v5-provider-trial-run-id.v1",
        {
            "started_at": started_at,
            "source_manifests": [product.source_manifest_sha256 for product in products],
            "provider": provider.model_dump(mode="json"),
        },
    )
    payload: dict[str, object] = {
        "contract": "insurance-v5-provider-trial-run.v2",
        "run_id": f"v5-trial-{run_id_seed[:16]}",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog_sha256(catalog),
        "status": status,
        "provider": provider.model_dump(mode="json"),
        "call_count": sum(len(product.attempts) for product in products),
        "started_at": started_at,
        "finished_at": finished_at,
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "products": [product.model_dump(mode="json") for product in products],
    }
    return V5ProviderTrialRun.model_validate(
        {
            **payload,
            "provider": provider,
            "products": products,
            "run_sha256": _run_digest(payload),
        }
    )


def write_provider_trial_run(path: Path, run: V5ProviderTrialRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            run.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_ocr_receipt_artifact(
    path: Path,
    receipts: Sequence[OcrPageReceipt],
) -> None:
    payload = {
        "contract": "insurance-v5-ocr-receipts.v1",
        "provider": "bailian",
        "model": BAILIAN_OCR_MODEL,
        "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
    }
    sealed = {
        **payload,
        "artifact_sha256": _canonical_digest("insurance-v5-ocr-receipts.v1", payload),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            sealed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_provider_trial_run(path: Path) -> V5ProviderTrialRun:
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ProviderTrialError("V5_PROVIDER_RUN_INVALID")
        claimed = raw_payload.get("run_sha256")
        payload = dict(raw_payload)
        payload.pop("run_sha256", None)
        if _run_digest(payload) != claimed:
            raise ProviderTrialError("V5_PROVIDER_RUN_DIGEST_INVALID")
        run = V5ProviderTrialRun.model_validate_json(path.read_text(encoding="utf-8"))
        if run.catalog_sha256 != catalog_sha256(load_v5_catalog()):
            raise ProviderTrialError("V5_PROVIDER_RUN_CATALOG_DRIFT")
        for product in run.products:
            if product.preview is not None:
                validate_preview_digest(product.preview)
        return run
    except (OSError, UnicodeDecodeError, ValidationError, PreviewCompilationError) as exc:
        raise ProviderTrialError("V5_PROVIDER_RUN_INVALID") from exc
    except ProviderTrialError as exc:
        raise ProviderTrialError("V5_PROVIDER_RUN_INVALID") from exc


def _attempt_from_completion(
    *,
    attempt: int,
    outcome: Literal[
        "ACCEPTED", "PRESERVED", "REJECTED", "ERROR", "REPAIR_REJECTED"
    ],
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
    is_typed_code = all(
        character.isalnum() or character == "_" for character in value
    )
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
        and any(
            evidence.verification_status != "VERIFIED"
            for evidence in field.evidence
        )
    ]
    by_ordinal = {field.field_id: field.ordinal for field in schema.fields}
    if candidate_field_ids is None:
        source_hit_unknown = unknown
        source_miss_unknown: list[str] = []
    else:
        source_hit_unknown = [
            field_id for field_id in unknown if field_id in candidate_field_ids
        ]
        source_miss_unknown = [
            field_id for field_id in unknown if field_id not in candidate_field_ids
        ]
    forced_unknown = [
        field_id for field_id in priority_field_ids if field_id in unknown
    ]
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
                evidence.verification_status
                for evidence in existing[field_id].evidence
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
        "all ordered material pages"
        if has_full_material_target
        else "the supplied candidate pages"
    )
    has_content_target = any(
        field_id in M144_CONTENT_SYNTHESIS_FIELD_IDS for field_id in target_field_ids
    )
    has_service_target = any(
        field_id in M146_SERVICE_FIELD_IDS for field_id in target_field_ids
    )
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
                    error_code=_review_error_code(preview)
                    or "EXTRACTION_GAP_REVIEW_REQUIRED",
                )
            )
            terminal_error = _review_error_code(preview) or "EXTRACTION_GAP_REVIEW_REQUIRED"
            emit(
                f"PROVIDER_GROUP_CALL_REJECTED version={approved.product_version_id} "
                f"attempt={attempt_number} code={error_code}"
            )

    eligible_field_ids = tuple(
        field.field_id
        for field in schema.fields
        if is_pdf_extractable_field(field)
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
                    repair_hint=_controlled_repair_hint(
                        preview, schema, repair_targets
                    ),
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
    max_calls_limit = (
        MAX_MICROBATCH_PROVIDER_CALLS if controlled_dynamic else MAX_PROVIDER_CALLS
    )
    max_attempts_limit = (
        MAX_MICROBATCH_PRODUCT_ATTEMPTS if controlled_dynamic else MAX_PRODUCT_ATTEMPTS
    )
    if not 1 <= max_provider_calls <= max_calls_limit:
        raise ProviderTrialError("V5_PROVIDER_CALL_BUDGET_INVALID")
    if not 1 <= max_product_attempts <= max_attempts_limit:
        raise ProviderTrialError("V5_PRODUCT_ATTEMPT_BUDGET_INVALID")
    if controlled_dynamic and (
        max_provider_calls < 27
        or max_product_attempts < 10
    ):
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
            ocr_page_reader=(
                ocr_client.extract_pdf_page if ocr_client is not None else None
            ),
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
                field.field_id
                for field in schema.fields
                if is_pdf_extractable_field(field)
            )
            located_candidates = locate_field_candidates(
                prepared.pages, schema, eligible_field_ids
            )
            candidate_field_ids = {
                field_id
                for field_id, candidates in located_candidates.items()
                if candidates
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
                request = _request_for_product(
                    prepared, source_text=attempt_source_text
                )
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
                                *(
                                    M146_SERVICE_FIELD_IDS
                                    if prepared.supplemental_pages
                                    else ()
                                ),
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


def provider_trial_main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded V5 three-product trial")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/v5-provider-trial/provider-run.json"),
    )
    parser.add_argument("--max-calls", type=int, default=MAX_PROVIDER_CALLS)
    parser.add_argument("--max-product-attempts", type=int, default=MAX_PRODUCT_ATTEMPTS)
    parser.add_argument("--no-adaptive", action="store_true")
    parser.add_argument("--controlled-dynamic", action="store_true")
    parser.add_argument(
        "--product-ids",
        help="Comma-separated approved product IDs; defaults to all frozen products",
    )
    parser.add_argument(
        "--supplemental-root-596",
        type=Path,
        help="Exact Mission 146 service-material directory for product 596",
    )
    parser.add_argument(
        "--ocr-output",
        type=Path,
        help="Independent qwen-vl-ocr receipt artifact required with supplemental input",
    )
    args = parser.parse_args()
    api_key = os.environ.get("HARNESS_DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("HARNESS_DASHSCOPE_API_KEY_REQUIRED")
    run = run_provider_trial(
        source_root=args.source_root,
        output_path=args.output,
        api_key=api_key,
        progress=lambda message: print(message, flush=True),
        max_provider_calls=args.max_calls,
        max_product_attempts=args.max_product_attempts,
        adaptive=not args.no_adaptive,
        controlled_dynamic=args.controlled_dynamic,
        product_ids=(
            tuple(item.strip() for item in args.product_ids.split(",") if item.strip())
            if args.product_ids
            else None
        ),
        supplemental_root_596=args.supplemental_root_596,
        ocr_output_path=args.ocr_output,
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "status": run.status,
                "call_count": run.call_count,
                "data_products": sum(
                    product.preview is not None for product in run.products
                ),
                "review_required_products": sum(
                    product.status == "REVIEW_REQUIRED" for product in run.products
                ),
                "run_sha256": run.run_sha256,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    if run.status != "COMPLETED":
        raise SystemExit(2)


if __name__ == "__main__":
    provider_trial_main()


__all__ = [
    "APPROVED_PRODUCTS",
    "M140_PRODUCT_IDS",
    "M144_CONTENT_SYNTHESIS_FIELD_IDS",
    "M146_SERVICE_FIELD_IDS",
    "M146_SUPPLEMENTAL_PDFS",
    "_content_synthesis_context",
    "_content_synthesis_targets",
    "M143_SEMANTIC_TARGET_FIELD_IDS",
    "ApprovedPdf",
    "ApprovedProduct",
    "PreparedProduct",
    "ProviderAttemptReceipt",
    "ProviderIdentity",
    "ProviderTrialError",
    "ProviderTrialProduct",
    "SourceFileReceipt",
    "SourcePage",
    "V5ProviderTrialRun",
    "build_source_text",
    "build_m146_repair_source_text",
    "classify_evidence",
    "compare_provider_trials",
    "load_frozen_pdf_pages",
    "load_provider_trial_run",
    "prepare_approved_product",
    "prepare_approved_products",
    "provider_trial_main",
    "resolve_evidence_locator",
    "run_provider_trial",
    "seal_provider_trial_run",
    "write_provider_trial_run",
    "write_ocr_receipt_artifact",
]
