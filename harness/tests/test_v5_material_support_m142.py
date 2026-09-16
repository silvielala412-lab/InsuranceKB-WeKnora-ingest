from __future__ import annotations

from insurance_harness.v5_preview.contracts import (
    CandidateField,
    FieldDefinition,
    InsuranceSchema,
)
from insurance_harness.v5_preview.dynamic_ingest import locate_field_candidates
from insurance_harness.v5_preview.material_support import (
    classify_material_support,
    compute_material_supported_extraction_rate,
    is_pdf_extractable_field,
)
from insurance_harness.v5_preview.provider_trial import SourcePage, _controlled_repair_targets


def _field(
    field_id: str,
    display_name: str,
    *,
    modes: tuple[str, ...] = ("原文抽取",),
    guidance: str = "产品条款、产品说明书",
) -> FieldDefinition:
    return FieldDefinition(
        ordinal=0,
        category_id="03",
        category_display_name="产品定位与摘要",
        display_name=display_name,
        value_guidance="",
        field_id=field_id,
        description=display_name,
        source_guidance=guidance,
        formation_modes=modes,
        knowledge_role="事实 Fact",
    )


def test_mixed_mode_field_is_pdf_extractable_and_repairable() -> None:
    field = _field(
        "target_customer_profile",
        "适用人群",
        modes=("原文抽取", "LLM生成"),
    )
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=(field,),
    )
    assert is_pdf_extractable_field(field)
    preview = type("Preview", (), {"fields": (type("Field", (), {
        "field_id": field.field_id,
        "state": "unknown",
        "evidence": (),
    })(),)})()
    assert _controlled_repair_targets(preview, schema) == (field.field_id,)


def test_semantic_aliases_create_candidates_without_same_name_heading() -> None:
    fields = (
        _field("target_customer_profile", "适用人群", modes=("原文抽取", "LLM生成")),
        _field("premium_adjustment_rules", "费率可调"),
        _field("product_conversion_rules", "险种转换"),
    )
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=fields,
    )
    digest = "a" * 64
    pages = (
        SourcePage(
            document_name="条款.pdf",
            document_sha256=digest,
            page_number=1,
            text="适合家庭成员投保，成人少儿均可选择；费率因子按人数确定；可转换为其他险种。",
        ),
    )
    located = locate_field_candidates(pages, schema, tuple(field.field_id for field in fields))
    assert all(located[field.field_id] for field in fields)


def test_material_support_is_tri_state_and_rate_uses_supported_denominator() -> None:
    supported = _field("target_customer_profile", "适用人群", modes=("原文抽取", "LLM生成"))
    unavailable = _field(
        "marketing_tagline",
        "产品宣传语",
        guidance="产品宣传海报",
    )
    ambiguous = _field("premium_adjustment_rules", "费率可调")
    digest = "b" * 64
    pages = (
        SourcePage(
            document_name="产品说明书.pdf",
            document_sha256=digest,
            page_number=1,
            text="适合家庭成员投保，费率因子按人数确定。",
        ),
    )
    decisions = tuple(
        classify_material_support(field, pages)
        for field in (supported, unavailable, ambiguous)
    )
    assert decisions[0].status == "supported"
    assert decisions[1].status == "unsupported"
    assert decisions[2].status == "ambiguous"

    preview = type("Preview", (), {"fields": (
        CandidateField(
            ordinal=0,
            category_id="03",
            category_display_name="产品定位与摘要",
            field_id=supported.field_id,
            display_name=supported.display_name,
            knowledge_role=supported.knowledge_role,
            formation_modes=supported.formation_modes,
            output_kind="Content",
            state="present",
            value="家庭成员",
            evidence=(),
        ),
        CandidateField(
            ordinal=0,
            category_id="03",
            category_display_name="产品定位与摘要",
            field_id=unavailable.field_id,
            display_name=unavailable.display_name,
            knowledge_role=unavailable.knowledge_role,
            formation_modes=unavailable.formation_modes,
            output_kind="Content",
            state="unknown",
            value=None,
            evidence=(),
        ),
        CandidateField(
            ordinal=0,
            category_id="03",
            category_display_name="产品定位与摘要",
            field_id=ambiguous.field_id,
            display_name=ambiguous.display_name,
            knowledge_role=ambiguous.knowledge_role,
            formation_modes=ambiguous.formation_modes,
            output_kind="Fact",
            state="present",
            value="是",
            evidence=(),
        ),
    )})()
    metrics = compute_material_supported_extraction_rate(preview, decisions)
    assert metrics.material_supported_field_count == 1
    assert metrics.material_supported_present_count == 1
    assert metrics.rate == 1.0
