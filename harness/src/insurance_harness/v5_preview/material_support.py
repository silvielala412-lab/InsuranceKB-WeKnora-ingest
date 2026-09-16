"""Material availability and support-conditioned extraction accounting."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import FieldDefinition

MaterialSupportStatus = Literal["supported", "ambiguous", "unsupported"]


class MaterialSupportDecision(BaseModel):
    """A field-level, non-authoritative assessment of source material support."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    status: MaterialSupportStatus
    basis: Annotated[str, Field(min_length=1)]
    candidate_locators: tuple[str, ...] = ()


class MaterialSupportMetrics(BaseModel):
    """Support-conditioned recall, kept separate from Evidence quality."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    extractable_field_count: Annotated[int, Field(ge=0)]
    material_supported_field_count: Annotated[int, Field(ge=0)]
    material_supported_present_count: Annotated[int, Field(ge=0)]
    rate: Annotated[float, Field(ge=0, le=1)]
    ambiguous_field_count: Annotated[int, Field(ge=0)]
    unsupported_field_count: Annotated[int, Field(ge=0)]


def is_pdf_extractable_field(field: FieldDefinition) -> bool:
    """Return whether a field belongs in PDF extraction and recall accounting.

    Mixed ``原文抽取 + LLM生成`` fields still have a material-backed extraction arm.
    Only pure external mappings and pure LLM synthesis are excluded.
    """

    modes = set(field.formation_modes)
    return "外部映射" not in modes and modes != {"LLM生成"}


def _compact(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", value).lower()
        if not char.isspace()
    )


_AVAILABLE_SOURCE_MARKERS = (
    "产品条款",
    "保险条款",
    "产品说明书",
    "产品投保规则",
    "投保规则",
    "费率表",
)
_MISSING_SOURCE_MARKERS = (
    "产品宣传海报",
    "产品培训材料",
    "产品销售逻辑",
    "产品销售规则",
    "产品核保规则",
    "特别约定",
    "投保页面",
    "全量产品基础信息",
    "服务手册",
)

_FIELD_SIGNALS: dict[str, tuple[str, ...]] = {
    "eligible_service_packages": (
        "可享服务",
        "服务权益",
        "在线问诊",
        "门诊预约",
        "陪诊",
        "住院照护",
        "专家会诊",
        "特药",
        "康复护理",
    ),
    "medical_service_benefits": (
        "健康服务",
        "增值服务",
        "就医服务",
        "在线问诊",
        "陪诊",
        "直付",
        "垫付",
        "康复护理",
    ),
    "product_faq": ("产品Q&A", "常见问题", "Q1", "Q2", "问答"),
    "target_customer_profile": (
        "适用人群",
        "目标人群",
        "投保年龄",
        "投保范围",
        "被保险人范围",
        "家庭成员",
        "成人",
        "少儿",
        "儿童",
        "家人",
        "家庭生活",
    ),
    "premium_adjustment_rules": (
        "费率可调整",
        "费率调整",
        "调整保险费率",
        "调整费率",
        "费率因子",
        "费率系数",
        "重新定价",
        "提高保险费率",
    ),
    "product_conversion_rules": (
        "险种转换",
        "转换为",
        "转保",
        "可转换",
        "转换权",
    ),
}


def _signal_hits(field: FieldDefinition, pages: Sequence[object]) -> tuple[str, ...]:
    signals = _FIELD_SIGNALS.get(field.field_id, (field.display_name,))
    texts = [_compact(str(getattr(page, "text", ""))) for page in pages]
    return tuple(signal for signal in signals if any(_compact(signal) in text for text in texts))


def classify_material_support(
    field: FieldDefinition,
    pages: Sequence[object],
    candidate_locators: Collection[str] = (),
    *,
    allow_external_source: bool = False,
) -> MaterialSupportDecision:
    """Classify source support without deciding the field value.

    ``ambiguous`` is intentional for phrases that need semantic judgment, such as a
    family rate factor or an underwriting surcharge. The provider remains responsible
    for selecting a value and binding it to Evidence.
    """

    locators = tuple(candidate_locators)
    if "外部映射" in field.formation_modes and not allow_external_source:
        return MaterialSupportDecision(
            field_id=field.field_id,
            status="unsupported",
            basis="字段声明为外部映射，当前 PDF 不作为材料支持来源",
            candidate_locators=locators,
        )
    if set(field.formation_modes) == {"LLM生成"}:
        return MaterialSupportDecision(
            field_id=field.field_id,
            status="unsupported",
            basis="纯 LLM生成字段，当前材料支持率不纳入该字段",
            candidate_locators=locators,
        )

    guidance = _compact(field.source_guidance)
    missing = tuple(
        marker for marker in _MISSING_SOURCE_MARKERS if _compact(marker) in guidance
    )
    available = tuple(
        marker for marker in _AVAILABLE_SOURCE_MARKERS if _compact(marker) in guidance
    )
    hits = _signal_hits(field, pages)

    if allow_external_source and hits:
        return MaterialSupportDecision(
            field_id=field.field_id,
            status="supported",
            basis=f"受控补充材料出现相关服务语义：{'、'.join(hits)}",
            candidate_locators=locators,
        )

    if field.field_id == "premium_adjustment_rules":
        explicit = {"费率可调整", "费率调整", "调整保险费率", "调整费率", "重新定价"}
        ambiguous = {"费率因子", "费率系数", "提高保险费率"}
        if any(item in hits for item in explicit):
            status: MaterialSupportStatus = "supported"
            basis = "材料出现明确的费率调整/重新定价表达"
        elif any(item in hits for item in ambiguous):
            status = "ambiguous"
            basis = "材料有费率相关表达，但不足以证明产品一般费率可调"
        else:
            status = "unsupported" if not available else "ambiguous"
            basis = "未找到明确的产品费率可调规则"
        return MaterialSupportDecision(
            field_id=field.field_id,
            status=status,
            basis=basis,
            candidate_locators=locators,
        )

    if field.field_id == "product_conversion_rules":
        if any(item in hits for item in ("险种转换", "转换为", "转保", "可转换", "转换权")):
            status = "supported"
            basis = "材料出现明确的险种转换/转保表达"
        else:
            status = "unsupported" if not any(item in hits for item in ("续保",)) else "ambiguous"
            basis = "未找到明确的险种转换规则"
        return MaterialSupportDecision(
            field_id=field.field_id,
            status=status,
            basis=basis,
            candidate_locators=locators,
        )

    if missing and not available and not hits:
        return MaterialSupportDecision(
            field_id=field.field_id,
            status="unsupported",
            basis=f"Schema 指向的来源类型未随本次材料提供：{'、'.join(missing)}",
            candidate_locators=locators,
        )
    if hits or locators:
        basis = f"材料页面出现相关语义：{'、'.join(hits) if hits else '候选页已定位'}"
        if missing:
            basis += f"；另有未提供来源类型：{'、'.join(missing)}"
            status = "ambiguous"
        else:
            status = "supported"
        return MaterialSupportDecision(
            field_id=field.field_id,
            status=status,
            basis=basis,
            candidate_locators=locators,
        )
    if available:
        return MaterialSupportDecision(
            field_id=field.field_id,
            status="ambiguous",
            basis="Schema 指向的材料类型已提供，但页面未命中稳定候选语义",
            candidate_locators=locators,
        )
    return MaterialSupportDecision(
        field_id=field.field_id,
        status="unsupported",
        basis="当前提供的材料类型与 Schema 来源说明没有可确认交集",
        candidate_locators=locators,
    )


def compute_material_supported_extraction_rate(
    preview: object,
    decisions: Sequence[MaterialSupportDecision],
) -> MaterialSupportMetrics:
    """Compute ``present ∧ supported / supported`` for PDF-extractable fields."""

    decision_by_id = {decision.field_id: decision for decision in decisions}
    fields = tuple(getattr(preview, "fields", ()))
    supported_ids = {
        field_id
        for field_id, decision in decision_by_id.items()
        if decision.status == "supported"
    }
    present_ids = {
        field.field_id
        for field in fields
        if field.field_id in supported_ids and field.state == "present"
    }
    extractable_count = sum(
        decision.status != "unsupported"
        and decision.field_id in {field.field_id for field in fields}
        for decision in decisions
    )
    return MaterialSupportMetrics(
        extractable_field_count=extractable_count,
        material_supported_field_count=len(supported_ids),
        material_supported_present_count=len(present_ids),
        rate=(len(present_ids) / len(supported_ids)) if supported_ids else 0.0,
        ambiguous_field_count=sum(decision.status == "ambiguous" for decision in decisions),
        unsupported_field_count=sum(
            decision.status == "unsupported" for decision in decisions
        ),
    )


__all__ = [
    "MaterialSupportDecision",
    "MaterialSupportMetrics",
    "classify_material_support",
    "compute_material_supported_extraction_rate",
    "is_pdf_extractable_field",
]
