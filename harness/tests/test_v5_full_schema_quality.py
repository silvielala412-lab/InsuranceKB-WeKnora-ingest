from dataclasses import replace
from types import SimpleNamespace

from insurance_harness.v5_preview.contracts import CandidateEvidence, PluginFieldResult
from insurance_harness.v5_preview.dynamic_gapfill import DynamicMaterialPage
from insurance_harness.v5_preview.full_schema_quality import (
    admit_full_schema_evidence_subset,
    audit_full_schema_candidate,
    build_full_schema_field_context,
    choose_full_schema_replacement,
)
from insurance_harness.v5_preview.m156_run import M156Material
from insurance_harness.v5_preview.m158_run import M158RunPolicy, _plan_product_batches
from insurance_harness.v5_preview.m158_quality import audit_m158_candidate
from insurance_harness.v5_preview.catalog import load_v5_catalog
from insurance_harness.v5_preview.value_constraints import normalize_field_value


def test_multiple_source_sentences_can_use_separate_verified_quotes():
    quotes = ("给付身故保险金，本合同终止。", "两名被保险人均生存时，可以申请减少一名被保险人。")
    decision = audit_full_schema_candidate(
        field_id="benefit_interaction_rules",
        proposed_value="\n".join(quotes),
        evidence_quotes=quotes,
    )
    assert decision.accepted


def test_shared_numbers_and_words_do_not_prove_an_added_fact():
    decision = audit_full_schema_candidate(
        field_id="sum_assured_range",
        proposed_value="最低保额为100万元，最高保额为500万元。",
        evidence_quotes=("示例年交保险费为100万元，累计500万元。",),
    )
    assert not decision.accepted


def test_only_documented_footnotes_are_normalized_not_business_numbers():
    quote = "同一保单年度1内减少金额不得超过20%。"
    source = quote + "\n1 保单年度指合同生效日至下一周年日期间。"
    accepted = audit_full_schema_candidate(
        field_id="sum_assured_reduction_rules",
        proposed_value="同一保单年度内减少金额不得超过20%。",
        evidence_quotes=(quote,), candidate_text=source,
    )
    rejected = audit_full_schema_candidate(
        field_id="sum_assured_reduction_rules",
        proposed_value="同一保单年度内减少金额不得超过30%。",
        evidence_quotes=(quote,), candidate_text=source,
    )
    assert accepted.accepted
    assert not rejected.accepted


def test_full_schema_does_not_bypass_waiting_period_components():
    quote = "自合同生效之日起90日为等待期，适用于疾病责任。"
    proposal = PluginFieldResult(
        ordinal=1, field_id="waiting_period", state="present", value=quote,
        evidence=(CandidateEvidence(
            source_revision_id="source-test", locator="pdf:条款.pdf#page=1", quote=quote,
            verification_status="VERIFIED",
        ),),
    )
    admitted, decision = admit_full_schema_evidence_subset(
        proposal, candidate_text=quote, product_display_name="测试产品",
    )
    assert admitted is None
    assert "within_wait_consequence" in decision.missing_components


def test_bad_independent_array_item_does_not_erase_verified_fact():
    quote = "若被保险人为一人，给付身故保险金，本合同终止。"
    proposal = PluginFieldResult(
        ordinal=49, field_id="benefit_interaction_rules", state="present",
        value=(quote, "未成年人身故额外给付50万元。"),
        evidence=(CandidateEvidence(
            source_revision_id="source-test", locator="pdf:条款.pdf#page=1", quote=quote,
            verification_status="VERIFIED",
        ),),
    )
    admitted, decision = admit_full_schema_evidence_subset(
        proposal, candidate_text=quote, product_display_name="测试产品",
    )
    assert admitted is not None
    assert admitted.value == (quote,)
    assert decision.reason == "SOURCE_PARTIAL_EVIDENCE_ADMITTED"
    assert decision.missing_components == ("未成年人身故额外给付50万元。",)


def test_explicit_negative_baseline_requires_conflict_review():
    decision = choose_full_schema_replacement(
        field_id="coverage_increase_rules", baseline_state="absent_explicitly",
        baseline_value=None, baseline_evidence_quotes=("不接受增加基本保险金额。",),
        proposed_state="present", proposed_value="允许增加基本保险金额。",
        proposed_evidence_quotes=("允许增加基本保险金额。",),
        candidate_text="允许增加基本保险金额。", product_display_name="测试产品",
    )
    assert decision.action == "keep_baseline"
    assert decision.reason == "SOURCE_CONFLICT_REQUIRES_REVIEW"


def test_keyword_miss_does_not_remove_source_field_from_plan():
    page = DynamicMaterialPage(
        document_name="条款.pdf", document_sha256="a" * 64,
        page_number=1, text="这是一段未命中目标关键词的产品文字。",
    )
    policy = replace(
        M158RunPolicy.default(), source_fields_only=True,
        focus_field_ids=("health_declaration_requirements",),
        field_context_builder=build_full_schema_field_context,
    )
    batches = _plan_product_batches(
        SimpleNamespace(insurance_class="终身寿险", product_display_name="测试产品"),
        M156Material((page,), 1, ()), policy=policy,
    )
    assert len(batches) == 1
    assert batches[0].field_ids == ("health_declaration_requirements",)
    assert batches[0].coverage["health_declaration_requirements"]["candidate_page_count"] == 0
    assert page.text in batches[0].context


def test_calendar_year_in_example_is_not_a_required_payment_option():
    quote = "交费期间为3年、6年、10年。"
    decision = audit_m158_candidate(
        field_id="premium_payment_term", proposed_value=("3年", "6年", "10年"),
        evidence_quotes=(quote,),
        candidate_text=quote + "\n2027年9月1日为最后一个保险费约定支付日，交费期间为3年。",
        product_display_name="测试产品",
    )
    assert decision.accepted


def test_unrelated_negative_word_does_not_reverse_joint_insured_support():
    definition = next(f for f in load_v5_catalog().schema_for("终身寿险").fields if f.field_id == "multiple_insured_rules")
    value = "支持双被保人设计；若两名被保险人同时身故，或者无法确定先后顺序，按约定给付。"
    assert normalize_field_value(definition, value) == value
    question = "是否满18周岁应按条款判断。"
    assert normalize_field_value(definition, question) == question
    assert not audit_full_schema_candidate(
        field_id="multiple_insured_rules", proposed_value="否", evidence_quotes=(question,),
    ).accepted
    assert audit_full_schema_candidate(
        field_id="multiple_insured_rules", proposed_value="支持双被保人/联合被保人",
        evidence_quotes=("一张保单可同时设置两名被保险人。",),
    ).accepted
