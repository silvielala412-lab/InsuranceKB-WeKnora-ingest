from __future__ import annotations

from dataclasses import dataclass

from insurance_harness.v5_preview.contracts import (
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
)
from insurance_harness.v5_preview.llm_plugin import SchemaGuidedLlmPlugin
from insurance_harness.v5_preview.value_constraints import (
    ValueConstraintKind,
    normalize_field_value,
    parse_value_guidance,
)


def test_value_guidance_parses_single_choice() -> None:
    constraint = parse_value_guidance("是、否")

    assert constraint.kind == ValueConstraintKind.SINGLE
    assert constraint.allowed_values == ("是", "否")
    assert constraint.multi_select is False
    assert constraint.nullable is False


def test_value_guidance_parses_multi_select_and_nullable() -> None:
    constraint = parse_value_guidance("保单红利、现金价值、保单贷款（多选，可为空）")

    assert constraint.kind == ValueConstraintKind.MULTI
    assert constraint.allowed_values == ("保单红利", "现金价值", "保单贷款")
    assert constraint.multi_select is True
    assert constraint.nullable is True


def test_open_ended_multi_select_examples_do_not_become_a_closed_enum() -> None:
    special = parse_value_guidance(
        "条件承保、除外不保、猝死可赔、既往症可赔等（标签化，多选）"
    )
    services = parse_value_guidance("就医绿通、费用垫付、线上理赔等（多选）")

    assert special.kind == ValueConstraintKind.MULTI
    assert special.allow_other is True
    assert services.allow_other is True


def test_open_ended_multi_select_preserves_specific_values() -> None:
    definition = FieldDefinition(
        ordinal=0,
        category_id="07",
        category_display_name="保障责任与额度",
        display_name="特殊承保与除外标签",
        value_guidance="既往症不可赔、除外不保、加费承保等（标签化，多选）",
        field_id="special_coverage_and_exclusion_tags",
        description="具体对象和承保方向",
        source_guidance="产品条款",
        formation_modes=("规则衍生",),
        knowledge_role="衍生 Derived",
    )

    value = normalize_field_value(
        definition,
        ["既往症除外不保", "遗传性疾病除外不保"],
    )

    assert value == ("既往症除外不保", "遗传性疾病除外不保")


def test_value_guidance_preserves_semantic_parentheticals_and_compound_options() -> None:
    age_constraint = parse_value_guidance(
        "儿童（0-17岁）、成人（18-59岁）、老年人（60岁及以上）（可多选）"
    )
    facility_constraint = parse_value_guidance("特需部/国际部、私立医院（多选）")

    assert age_constraint.allowed_values == (
        "儿童（0-17岁）",
        "成人（18-59岁）",
        "老年人（60岁及以上）",
    )
    assert facility_constraint.allowed_values == ("特需部/国际部", "私立医院")


def test_normalization_maps_unambiguous_values_and_preserves_ambiguous_text() -> None:
    definition = FieldDefinition(
        ordinal=0,
        category_id="06",
        category_display_name="续保与费率规则",
        display_name="费率可调",
        value_guidance="是、否",
        field_id="premium_adjustment_rules",
        description="费率是否可调整",
        source_guidance="产品条款",
        formation_modes=("原文抽取",),
        knowledge_role="事实 Fact",
    )

    assert normalize_field_value(definition, "是") == "是"
    assert normalize_field_value(definition, "本产品费率不可调整") == "否"
    assert normalize_field_value(definition, "是或否，需结合具体计划") == "是或否，需结合具体计划"

    payment = definition.model_copy(
        update={
            "display_name": "缴费方式",
            "field_id": "premium_payment_frequency",
            "value_guidance": "趸缴、年缴、半年缴、季缴、月缴",
        }
    )
    assert normalize_field_value(payment, "趸交") == "趸缴"
    assert normalize_field_value(payment, ("趸交", "年缴")) == ("趸缴", "年缴")


@dataclass
class Completion:
    model: str = "qwen-plus"

    def complete(self, *, system: str, user: str) -> str:
        self.user = user
        return (
            '{"fields":[{"ordinal":0,"field_id":"premium_adjustment_rules",'
            '"state":"present","value":"本产品费率不可调整",'
            '"evidence":[{"locator":"pdf:条款.pdf#page=2",'
            '"quote":"本产品费率不可调整"}]}]}'
        )


def test_prompt_carries_structured_value_constraint_and_plugin_normalizes() -> None:
    completion = Completion()
    field = FieldDefinition(
        ordinal=0,
        category_id="06",
        category_display_name="续保与费率规则",
        display_name="费率可调",
        value_guidance="是、否",
        field_id="premium_adjustment_rules",
        description="费率是否可调整",
        source_guidance="产品条款",
        formation_modes=("原文抽取",),
        knowledge_role="事实 Fact",
    )
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=(field,),
    )
    request = IngestRequest(
        source_revision_id="revision-m141",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试产品",
        reviewed_insurance_class="医疗险",
        source_text="本产品费率不可调整",
    )

    result = SchemaGuidedLlmPlugin(completion=completion).extract(request, schema)

    assert '"kind":"single_choice"' in completion.user
    assert result.fields[0].value == "否"
