from __future__ import annotations

from insurance_harness.v5_preview.contracts import (
    CandidateField,
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
)
from insurance_harness.v5_preview.dynamic_ingest import (
    build_candidate_source_text,
    build_full_material_field_source_text,
)
from insurance_harness.v5_preview.llm_plugin import _schema_prompt
from insurance_harness.v5_preview.provider_trial import (
    M144_CONTENT_SYNTHESIS_FIELD_IDS,
    SourcePage,
    _content_synthesis_targets,
    _controlled_repair_targets,
)

TARGETS = (
    "premium_grace_period",
    "product_conversion_rules",
    "premium_adjustment_rules",
)


def _schema() -> InsuranceSchema:
    return InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=tuple(
            FieldDefinition(
                ordinal=index,
                category_id="06" if index else "05",
                category_display_name="续保与费率规则",
                display_name=label,
                value_guidance="是、否" if index else "",
                field_id=field_id,
                description=label,
                source_guidance="产品条款",
                formation_modes=("原文抽取",),
                knowledge_role="事实 Fact",
            )
            for index, (field_id, label) in enumerate(
                zip(TARGETS, ("宽限期", "险种转换", "费率可调"), strict=True)
            )
        ),
    )


def test_target_context_keeps_all_pages_when_no_keyword_candidate() -> None:
    digest = "a" * 64
    pages = tuple(
        SourcePage(
            document_name="保险条款.pdf",
            document_sha256=digest,
            page_number=page,
            text=f"第{page}页正文，没有字段同名标题。",
        )
        for page in range(1, 4)
    )

    context = build_full_material_field_source_text(
        pages,
        _schema(),
        TARGETS,
        max_characters=10_000,
    )

    assert "页码：1" in context
    assert "页码：2" in context
    assert "页码：3" in context


def test_unknown_target_fields_are_forced_into_repair_without_candidates() -> None:
    schema = _schema()
    preview = type(
        "Preview",
        (),
        {
            "fields": tuple(
                CandidateField(
                    ordinal=field.ordinal,
                    category_id=field.category_id,
                    category_display_name=field.category_display_name,
                    field_id=field.field_id,
                    display_name=field.display_name,
                    knowledge_role=field.knowledge_role,
                    formation_modes=field.formation_modes,
                    output_kind="Fact",
                    state="unknown",
                    value=None,
                    evidence=(),
                )
                for field in schema.fields
            )
        },
    )()

    assert _controlled_repair_targets(
        preview,
        schema,
        candidate_field_ids=(),
        priority_field_ids=TARGETS,
    ) == TARGETS


def test_target_prompt_keeps_the_three_semantics_distinct() -> None:
    request = IngestRequest(
        source_revision_id="revision-1",
        catalog_id="insurance-product-schema-v5",
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试产品",
        schema_id="insurance-product-schema-v5:医疗险",
        reviewed_insurance_class="医疗险",
        source_text="全材料页文本",
    )
    prompt = _schema_prompt(request, _schema())

    assert "等待期、保险期间届满后的重新投保窗口不属于宽限期" in prompt
    assert "普通续保、附加险或保险期间届满不等于险种转换" in prompt
    assert "家庭费率因子、核保加费、年龄错误导致提高费率，不等于一般费率可调" in prompt


def test_pure_llm_content_fields_are_forced_into_a_second_pass() -> None:
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=(
            FieldDefinition(
                ordinal=0,
                category_id="03",
                category_display_name="产品定位与摘要",
                display_name="产品简介",
                value_guidance="",
                field_id="product_summary",
                description="根据材料归纳产品简介",
                source_guidance="产品说明书",
                formation_modes=("LLM生成",),
                knowledge_role="内容 Content",
            ),
            FieldDefinition(
                ordinal=1,
                category_id="03",
                category_display_name="产品定位与摘要",
                display_name="产品概览",
                value_guidance="",
                field_id="product_overview",
                description="根据材料归纳产品概览",
                source_guidance="产品说明书",
                formation_modes=("LLM生成",),
                knowledge_role="内容 Content",
            ),
        ),
    )
    preview = type(
        "Preview",
        (),
        {
            "fields": tuple(
                CandidateField(
                    ordinal=field.ordinal,
                    category_id=field.category_id,
                    category_display_name=field.category_display_name,
                    field_id=field.field_id,
                    display_name=field.display_name,
                    knowledge_role=field.knowledge_role,
                    formation_modes=field.formation_modes,
                    output_kind="Content",
                    state="unknown",
                    value=None,
                    evidence=(),
                )
                for field in schema.fields
            )
        },
    )()

    assert _content_synthesis_targets(preview, schema) == M144_CONTENT_SYNTHESIS_FIELD_IDS
    assert _controlled_repair_targets(
        preview,
        schema,
        priority_field_ids=M144_CONTENT_SYNTHESIS_FIELD_IDS,
    ) == M144_CONTENT_SYNTHESIS_FIELD_IDS


def test_content_context_is_all_page_and_prompt_is_material_bounded() -> None:
    digest = "c" * 64
    pages = tuple(
        SourcePage(
            document_name="任意文件.pdf",
            document_sha256=digest,
            page_number=page,
            text=f"第{page}页包含保障责任、投保规则和产品特点。",
        )
        for page in range(1, 4)
    )
    content_schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=(
            FieldDefinition(
                ordinal=0,
                category_id="03",
                category_display_name="产品定位与摘要",
                display_name="产品简介",
                value_guidance="",
                field_id="product_summary",
                description="根据材料归纳产品简介",
                source_guidance="产品说明书",
                formation_modes=("LLM生成",),
                knowledge_role="内容 Content",
            ),
            FieldDefinition(
                ordinal=1,
                category_id="03",
                category_display_name="产品定位与摘要",
                display_name="产品概览",
                value_guidance="",
                field_id="product_overview",
                description="根据材料归纳产品概览",
                source_guidance="产品说明书",
                formation_modes=("LLM生成",),
                knowledge_role="内容 Content",
            ),
        ),
    )
    context = build_candidate_source_text(
        pages,
        content_schema,
        ("product_summary", "product_overview"),
        max_characters=10_000,
    )
    assert all(f"页码：{page}" in context for page in range(1, 4))

    request = IngestRequest(
        source_revision_id="revision-2",
        catalog_id="insurance-product-schema-v5",
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试产品",
        schema_id=content_schema.schema_id,
        reviewed_insurance_class="医疗险",
        source_text=context,
    )
    prompt = _schema_prompt(
        request,
        content_schema,
        target_fields=content_schema.fields,
        synthesis_context="保险责任：住院医疗费用；投保年龄：出生满28日-65周岁",
    )
    assert "产品简介：基于所有输入材料归纳" in prompt
    assert "产品概览：基于所有输入材料整理" in prompt
    assert "保险责任：住院医疗费用" in prompt
