from __future__ import annotations

from dataclasses import dataclass

from insurance_harness.v5_preview.contracts import (
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
)
from insurance_harness.v5_preview.dynamic_ingest import build_coverage_summary_source_text
from insurance_harness.v5_preview.llm_plugin import SchemaGuidedLlmPlugin


@dataclass(frozen=True)
class Page:
    document_name: str
    page_number: int
    text: str


def test_coverage_summary_recalls_semantic_responsibilities_without_literal_label() -> None:
    pages = (
        Page("甲类资料.pdf", 1, "本合同约定我们承担住院医疗费用，按约定比例给付。"),
        Page("乙类资料.pdf", 4, "被保险人身故的，我们按合同约定给付身故保险金。"),
    )

    source = build_coverage_summary_source_text(pages)

    assert "住院医疗费用" in source
    assert "身故保险金" in source
    assert "甲类资料.pdf" in source
    assert "乙类资料.pdf" in source


def test_coverage_summary_keeps_all_documents_and_does_not_special_case_product_brochure() -> None:
    pages = (
        Page("随机甲.pdf", 2, "我们承担重大疾病保险金责任。"),
        Page("随机乙.pdf", 8, "合同期满仍生存的，给付满期保险金。"),
        Page("随机丙.pdf", 3, "本页仅为费率表，不含保障责任说明。"),
    )

    source = build_coverage_summary_source_text(pages)

    assert "重大疾病保险金" in source
    assert "满期保险金" in source
    assert "随机甲.pdf" in source
    assert "随机乙.pdf" in source


class Completion:
    model = "qwen-plus"

    def complete(self, *, system: str, user: str) -> str:
        return (
            '{"fields":[{"ordinal":0,"field_id":"coverage_summary",'
            '"state":"present","value":"住院医疗费用保障",'
            '"evidence":[{"locator":"pdf:随机甲.pdf#page=2",'
            '"quote":"这段引文不是当前切片中的逐字文本"}]}]}'
        )


def test_coverage_summary_value_is_preserved_when_evidence_needs_review() -> None:
    field = FieldDefinition(
        ordinal=0,
        category_id="07",
        category_display_name="保障责任与额度",
        display_name="保什么",
        value_guidance="保障责任汇总",
        field_id="coverage_summary",
        description="产品保障责任",
        source_guidance="产品材料",
        formation_modes=("原文抽取", "LLM生成"),
        knowledge_role="内容 Content",
    )
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=(field,),
    )
    request = IngestRequest(
        source_revision_id="revision-m140",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试产品",
        reviewed_insurance_class="医疗险",
        source_text="住院医疗费用保障",
    )

    result = SchemaGuidedLlmPlugin(completion=Completion()).extract(request, schema)

    assert result.fields[0].state == "present"
    assert result.fields[0].value == "住院医疗费用保障"
    assert result.fields[0].evidence[0].verification_status == "UNRESOLVED"


def test_coverage_summary_prompt_separates_coverage_from_policy_maintenance_rights() -> None:
    field = FieldDefinition(
        ordinal=0,
        category_id="07",
        category_display_name="保障责任与额度",
        display_name="保什么",
        value_guidance="保障责任汇总",
        field_id="coverage_summary",
        description="产品保障责任",
        source_guidance="产品条款",
        formation_modes=("原文抽取", "LLM生成"),
        knowledge_role="内容 Content",
    )
    schema = InsuranceSchema(
        ordinal=0,
        insurance_class="终身寿险",
        schema_id="insurance-product-schema-v5:终身寿险",
        fields=(field,),
    )
    request = IngestRequest(
        source_revision_id="revision-m140-prompt",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="5003",
        product_version_id="5003-1",
        product_display_name="测试产品",
        reviewed_insurance_class="终身寿险",
        source_text="保险责任与保单贷款均有说明",
    )
    from insurance_harness.v5_preview import llm_plugin

    rendered = llm_plugin._schema_prompt(request, schema)

    assert "只写保险责任和核心给付" in rendered
    assert "不写保单贷款" in rendered
