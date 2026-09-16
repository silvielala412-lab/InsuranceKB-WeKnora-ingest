from __future__ import annotations

from insurance_harness.v5_preview.contracts import (
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
)
from insurance_harness.v5_preview.llm_plugin import _schema_prompt
from insurance_harness.v5_preview.m156_quality import (
    M156_FOCUS_FIELD_IDS,
    audit_m156_candidate,
    build_m156_field_context,
    choose_m156_replacement,
)
from insurance_harness.v5_preview.m156_run import _project_batch_results
from insurance_harness.v5_preview.provider_trial import SourcePage


def _schema(*field_ids: str) -> InsuranceSchema:
    labels = {
        "coverage_responsibilities": "保险责任",
        "exclusions": "责任免除",
        "premium_payment_term": "缴费期限",
        "premium_payment_frequency": "缴费方式",
        "policyholder_rights": "保单权益",
        "waiting_period": "等待期",
        "disease_definitions_and_criteria": "疾病定义与认定标准",
    }
    return InsuranceSchema(
        ordinal=0,
        insurance_class="重大疾病保险",
        schema_id="insurance-product-schema-v5:重大疾病保险",
        fields=tuple(
            FieldDefinition(
                ordinal=index,
                category_id="07",
                category_display_name="保障责任与额度",
                display_name=labels[field_id],
                value_guidance="",
                field_id=field_id,
                description=labels[field_id],
                source_guidance="全部产品材料",
                formation_modes=("原文抽取",),
                knowledge_role="事实 Fact",
            )
            for index, field_id in enumerate(field_ids)
        ),
    )


def _page(number: int, text: str) -> SourcePage:
    return SourcePage(
        document_name="测试产品条款.pdf",
        document_sha256="a" * 64,
        page_number=number,
        text=text,
    )


def test_all_seven_focus_fields_have_an_all_page_coverage_receipt() -> None:
    pages = tuple(_page(number, f"第{number}页正文") for number in range(1, 13))
    schema = _schema(*M156_FOCUS_FIELD_IDS)

    selection = build_m156_field_context(
        pages,
        schema,
        M156_FOCUS_FIELD_IDS,
        max_characters=20_000,
    )

    assert set(selection.coverage) == set(M156_FOCUS_FIELD_IDS)
    assert all(item.scanned_page_count == 12 for item in selection.coverage.values())
    assert all(item.included_page_count == 12 for item in selection.coverage.values())
    assert all(f"页码：{number}" in selection.text for number in range(1, 13))


def test_long_legal_field_requires_one_evidence_item_per_atomic_fact() -> None:
    decision = audit_m156_candidate(
        field_id="coverage_responsibilities",
        proposed_value="1. 身故保险金\n2. 重大疾病保险金\n3. 轻症疾病保险金",
        evidence_quotes=("身故保险金", "重大疾病保险金"),
        candidate_text="身故保险金。重大疾病保险金。轻症疾病保险金。",
    )

    assert decision.accepted is False
    assert decision.reason == "ATOMIC_EVIDENCE_COUNT_MISMATCH"
    assert decision.atomic_item_count == 3
    assert decision.supported_item_count == 2


def test_payment_term_does_not_accept_one_example_as_the_complete_option_set() -> None:
    material = (
        "交费期间可选择10年、15年、20年或30年交。"
        "下列示例假设投保人选择20年交。"
    )
    decision = audit_m156_candidate(
        field_id="premium_payment_term",
        proposed_value=("20年",),
        evidence_quotes=("下列示例假设投保人选择20年交",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.reason == "PAYMENT_EXAMPLE_OR_INCOMPLETE_SET"
    assert decision.missing_components == ("10年", "15年", "30年")


def test_waiting_period_requires_material_supported_exception_and_consequence() -> None:
    material = (
        "本合同等待期为90日，因意外伤害发生保险事故的无等待期。"
        "等待期内发生疾病，本公司不承担保险责任并退还保险费。"
    )
    decision = audit_m156_candidate(
        field_id="waiting_period",
        proposed_value="等待期为90日",
        evidence_quotes=("本合同等待期为90日",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.reason == "WAITING_PERIOD_COMPONENT_MISSING"
    assert set(decision.missing_components) == {"意外例外", "等待期内后果"}


def test_policy_rights_rejects_an_item_without_direct_support() -> None:
    decision = audit_m156_candidate(
        field_id="policyholder_rights",
        proposed_value=("保单贷款", "自动垫交"),
        evidence_quotes=("您可以申请保单贷款",),
        candidate_text="您可以申请保单贷款。合同未约定自动垫交。",
    )

    assert decision.accepted is False
    assert decision.reason == "POLICY_RIGHT_UNSUPPORTED"
    assert decision.missing_components == ("自动垫交",)


def test_focus_field_prompt_requests_complete_atomic_results_without_expected_answers() -> None:
    schema = _schema(*M156_FOCUS_FIELD_IDS)
    request = IngestRequest(
        source_revision_id="source-1",
        catalog_id="insurance-product-schema-v5",
        product_id="1828",
        product_version_id="1828-1",
        product_display_name="测试重大疾病产品",
        schema_id=schema.schema_id,
        reviewed_insurance_class=schema.insurance_class,
        source_text="全部材料",
    )

    prompt = _schema_prompt(request, schema)

    assert "不得使用‘等’或‘详见条款’省略责任项目" in prompt
    assert "示例或利益演示中的单一交费期间不能当成完整可选集合" in prompt
    assert "意外原因是否例外" in prompt
    assert "每项权益都必须有直接支持该项的独立 Evidence" in prompt


def test_complete_supported_right_set_can_replace_an_unsupported_baseline_item() -> None:
    material = "您可以申请保单贷款。合同未约定自动垫交。"
    decision = choose_m156_replacement(
        field_id="policyholder_rights",
        baseline_state="present",
        baseline_value=("保单贷款", "自动垫交"),
        baseline_evidence_quotes=("您可以申请保单贷款",),
        proposed_state="present",
        proposed_value=("保单贷款",),
        proposed_evidence_quotes=("您可以申请保单贷款",),
        candidate_text=material,
    )

    assert decision.action == "replace"
    assert decision.proposed_audit.accepted is True
    assert decision.baseline_audit is not None
    assert decision.baseline_audit.accepted is False


def test_incomplete_proposal_never_overwrites_a_present_baseline() -> None:
    material = "本合同承担身故保险金、重大疾病保险金和轻症疾病保险金。"
    decision = choose_m156_replacement(
        field_id="coverage_responsibilities",
        baseline_state="present",
        baseline_value="1. 身故保险金\n2. 重大疾病保险金",
        baseline_evidence_quotes=("身故保险金", "重大疾病保险金"),
        proposed_state="present",
        proposed_value="1. 身故保险金\n2. 重大疾病保险金\n3. 轻症疾病保险金",
        proposed_evidence_quotes=("身故保险金",),
        candidate_text=material,
    )

    assert decision.action == "keep_baseline"
    assert decision.proposed_audit.accepted is False


def test_batch_executor_projects_plugin_full_schema_to_requested_fields() -> None:
    """The plugin returns the full schema; M156 merges only its bounded batch."""
    full_schema_ids = ("coverage_responsibilities", "exclusions", "waiting_period")
    requested = ("coverage_responsibilities", "waiting_period")
    results = tuple(
        PluginFieldResult(ordinal=index, field_id=field_id, state="unknown")
        for index, field_id in enumerate(full_schema_ids)
    )
    projected = _project_batch_results(results, requested)
    assert tuple(field.field_id for field in projected) == requested
