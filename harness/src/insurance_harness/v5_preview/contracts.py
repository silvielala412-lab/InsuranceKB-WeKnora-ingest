from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TriState = Literal["present", "absent_explicitly", "unknown"]
OutputKind = Literal["Fact", "Relation", "Derived", "Content"]
FormationMode = Literal["外部映射", "规则衍生", "LLM生成", "原文抽取"]
ReviewState = Literal["accepted", "unreviewed", "rejected"]
EvidenceVerificationStatus = Literal[
    "VERIFIED", "NORMALIZED_MATCH", "UNRESOLVED", "AMBIGUOUS"
]
CandidateValue = str | int | float | bool | tuple[str, ...]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CategoryDefinition(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    category_id: Annotated[str, Field(pattern=r"^\d{2}$")]
    display_name: Annotated[str, Field(min_length=1)]


class FieldDefinition(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    category_id: Annotated[str, Field(pattern=r"^\d{2}$")]
    category_display_name: Annotated[str, Field(min_length=1)]
    display_name: Annotated[str, Field(min_length=1)]
    value_guidance: str
    field_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    description: Annotated[str, Field(min_length=1)]
    source_guidance: Annotated[str, Field(min_length=1)]
    formation_modes: Annotated[tuple[FormationMode, ...], Field(min_length=1)]
    knowledge_role: Literal[
        "事实 Fact",
        "关系 Relation",
        "内容 Content",
        "衍生 Derived",
    ]

    @property
    def output_kind(self) -> OutputKind:
        return self.knowledge_role.rsplit(" ", 1)[-1]  # type: ignore[return-value]


class InsuranceSchema(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    insurance_class: Annotated[str, Field(min_length=1)]
    schema_id: Annotated[str, Field(min_length=1)]
    fields: Annotated[tuple[FieldDefinition, ...], Field(min_length=1)]


class ImportDiagnostic(_ClosedModel):
    code: Literal["INVALID_OTHER_INSURANCE_CLASS_VALUE"]
    sheet_name: Annotated[str, Field(min_length=1)]
    cell_address: Annotated[str, Field(pattern=r"^J[1-9][0-9]*$")]
    rejected_value: Literal["320"]


class V5Catalog(_ClosedModel):
    contract: Literal["insurance-v5-schema-catalog.v1"]
    catalog_id: Literal["insurance-product-schema-v5"]
    source_file_name: Annotated[str, Field(min_length=1)]
    source_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    categories: Annotated[tuple[CategoryDefinition, ...], Field(min_length=1)]
    schemas: Annotated[tuple[InsuranceSchema, ...], Field(min_length=1)]
    import_diagnostics: tuple[ImportDiagnostic, ...]

    def schema_for(self, insurance_class: str) -> InsuranceSchema:
        for schema in self.schemas:
            if schema.insurance_class == insurance_class:
                return schema
        raise KeyError(insurance_class)


class CandidateEvidence(_ClosedModel):
    source_revision_id: Annotated[str, Field(min_length=1)]
    locator: Annotated[str, Field(min_length=1, max_length=500)]
    quote: Annotated[str, Field(min_length=1, max_length=2000)]
    verification_status: EvidenceVerificationStatus = "VERIFIED"
    verification_error: str | None = None

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        if self.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}:
            if self.verification_error is not None:
                raise ValueError("matched Evidence cannot contain verification error")
        elif not self.verification_error:
            raise ValueError("unverified Evidence requires verification error")
        return self


class EvidenceResolution(_ClosedModel):
    locator: Annotated[str, Field(min_length=1, max_length=500)]
    verification_status: EvidenceVerificationStatus
    verification_error: str | None = None

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        if self.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}:
            if self.verification_error is not None:
                raise ValueError("matched Evidence cannot contain verification error")
        elif not self.verification_error:
            raise ValueError("unverified Evidence requires verification error")
        return self


class ClassificationDecision(_ClosedModel):
    insurance_class: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    signals: tuple[str, ...]
    review_state: ReviewState


class IngestRequest(_ClosedModel):
    source_revision_id: Annotated[str, Field(min_length=1)]
    catalog_id: Literal["insurance-product-schema-v5"]
    schema_id: Annotated[str, Field(min_length=1)]
    product_id: Annotated[str, Field(min_length=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    product_display_name: Annotated[str, Field(min_length=1)]
    reviewed_insurance_class: str | None = None
    classification: ClassificationDecision | None = None
    source_text: Annotated[str, Field(max_length=200_000)] = ""


class PluginFieldResult(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    field_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    state: TriState
    value: CandidateValue | None = None
    evidence: tuple[CandidateEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state == "present" and (self.value is None or not self.evidence):
            raise ValueError("present requires a value and Evidence")
        if self.state == "absent_explicitly" and (self.value is not None or not self.evidence):
            raise ValueError("absent_explicitly requires Evidence and no value")
        if self.state == "unknown" and (self.value is not None or self.evidence):
            raise ValueError("unknown requires no value and no Evidence")
        return self


@dataclass(frozen=True, slots=True)
class PluginResult:
    plugin_id: str
    source_revision_id: str
    insurance_class: str
    product_id: str
    product_version_id: str
    schema_id: str
    fields: tuple[PluginFieldResult, ...]


class CandidateField(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    category_id: Annotated[str, Field(pattern=r"^\d{2}$")]
    category_display_name: Annotated[str, Field(min_length=1)]
    field_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    display_name: Annotated[str, Field(min_length=1)]
    knowledge_role: Annotated[str, Field(min_length=1)]
    formation_modes: tuple[FormationMode, ...]
    output_kind: OutputKind
    state: TriState
    value: CandidateValue | None
    evidence: tuple[CandidateEvidence, ...]


class V5CandidatePreview(_ClosedModel):
    contract: Literal["insurance-v5-candidate-preview.v2"]
    catalog_id: Literal["insurance-product-schema-v5"]
    catalog_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    schema_id: Annotated[str, Field(min_length=1)]
    source_revision_id: Annotated[str, Field(min_length=1)]
    insurance_class: Annotated[str, Field(min_length=1)]
    product_id: Annotated[str, Field(min_length=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    product_display_name: Annotated[str, Field(min_length=1)]
    serving_effect: Literal["NONE"]
    review_publish_admission: Literal[False]
    categories: tuple[CategoryDefinition, ...]
    fields: tuple[CandidateField, ...]
    preview_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
