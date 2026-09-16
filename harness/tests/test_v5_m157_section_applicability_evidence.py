from __future__ import annotations

from insurance_harness.v5_preview.contracts import FieldDefinition, InsuranceSchema
from insurance_harness.v5_preview.m157_quality import (
    audit_m157_candidate,
    build_m157_field_context,
    classify_m157_evidence,
    plan_m157_batches,
)
from insurance_harness.v5_preview.m157_run import (
    M157_BASELINE_FILE_SHA256,
    M157_BASELINE_RUN_SHA256,
)
from insurance_harness.v5_preview.provider_trial import SourcePage


def _field(field_id: str, label: str) -> FieldDefinition:
    return FieldDefinition(
        ordinal=1,
        category_id="07",
        category_display_name="保障责任与额度",
        display_name=label,
        value_guidance="",
        field_id=field_id,
        description=label,
        source_guidance="全部产品材料",
        formation_modes=("原文抽取",),
        knowledge_role="事实 Fact",
    )


def _schema(*fields: FieldDefinition) -> InsuranceSchema:
    return InsuranceSchema(
        ordinal=0,
        insurance_class="重大疾病保险",
        schema_id="insurance-product-schema-v5:重大疾病保险",
        fields=fields,
    )


def _page(number: int, text: str) -> SourcePage:
    return SourcePage(
        document_name="测试附加险条款.pdf",
        document_sha256="a" * 64,
        page_number=number,
        text=text,
    )


def test_long_fields_are_isolated_and_six_products_need_twenty_primary_calls() -> None:
    critical = plan_m157_batches("重疾险")
    long_fields = {
        "coverage_responsibilities",
        "exclusions",
        "disease_definitions_and_criteria",
    }
    assert all(batch == (batch[0],) for batch in critical if batch[0] in long_fields)
    assert sum(
        len(plan_m157_batches(insurance_class))
        for insurance_class in (
            "医疗险",
            "年金险",
            "意外险",
            "终身寿险",
            "失能收入损失保险",
            "重疾险",
        )
    ) == 20


def test_one_long_quote_may_support_multiple_atomic_items() -> None:
    decision = audit_m157_candidate(
        field_id="coverage_responsibilities",
        proposed_value="1. 身故保险金\n2. 重大疾病保险金",
        evidence_quotes=("本合同承担身故保险金和重大疾病保险金。",),
        candidate_text="本合同承担身故保险金和重大疾病保险金。",
        product_display_name="测试重大疾病保险",
    )
    assert decision.accepted is True
    assert decision.atomic_item_count == 2
    assert decision.supported_item_count == 2


def test_rider_cannot_claim_a_right_that_only_applies_to_main_contract() -> None:
    decision = audit_m157_candidate(
        field_id="policyholder_rights",
        proposed_value=("自动垫交",),
        evidence_quotes=("自动垫交保险费条款适用主险合同。",),
        candidate_text="自动垫交保险费条款适用主险合同。",
        product_display_name="测试附加重大疾病保险",
    )
    assert decision.accepted is False
    assert decision.reason == "POLICY_RIGHT_WRONG_PRODUCT_SCOPE"


def test_field_context_scans_every_page_and_marks_product_scope() -> None:
    pages = tuple(_page(index, f"第{index}页正文") for index in range(1, 9))
    schema = _schema(_field("coverage_responsibilities", "保险责任"))
    context = build_m157_field_context(
        pages,
        schema,
        ("coverage_responsibilities",),
        product_display_name="测试附加重大疾病保险",
        max_characters=20_000,
    )
    assert context.coverage["coverage_responsibilities"].scanned_page_count == 8
    assert context.coverage["coverage_responsibilities"].included_page_count == 8
    assert "当前产品作用域：附加险" in context.text
    assert all(f"页码：{index}" in context.text for index in range(1, 9))


def test_unique_high_confidence_layout_variant_relocates_to_the_right_page() -> None:
    pages = (
        _page(1, "无关说明。"),
        _page(2, "等待期为90日。因意外伤害发生保险事故的，\n不受等待期限制。"),
    )
    resolution = classify_m157_evidence(
        pages,
        "等待期为90日，因意外伤害发生保险事故的，不受等待期限制。",
        "pdf:测试附加险条款.pdf#page=1",
    )
    assert resolution.verification_status == "NORMALIZED_MATCH"
    assert resolution.locator == "pdf:测试附加险条款.pdf#page=2"


def test_near_duplicate_fuzzy_pages_remain_ambiguous() -> None:
    quote = "等待期为90日，因意外伤害发生保险事故的，不受等待期限制。"
    pages = (
        _page(2, "等待期为90日。因意外伤害发生保险事故的，不受等待期限制。"),
        _page(3, "等待期为90日；因意外伤害发生保险事故的，不受等待期限制。"),
    )
    resolution = classify_m157_evidence(pages, quote, "unresolved:evidence")
    assert resolution.verification_status == "AMBIGUOUS"
    assert resolution.verification_error == "V5_EVIDENCE_PAGE_AMBIGUOUS"


def test_m157_is_pinned_to_the_independent_m156_rerun_identity() -> None:
    assert M157_BASELINE_FILE_SHA256 == (
        "f7da53d153b05f965bb4357bd7302c91b65351f3f39874ba0c0e0128fc709e86"
    )
    assert M157_BASELINE_RUN_SHA256 == (
        "cee87b1772333d263e4ffff9424daeafd303ea26189ab4aab7d627aed92e3360"
    )
