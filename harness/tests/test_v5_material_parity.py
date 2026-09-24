from dataclasses import replace

from insurance_harness.v5_preview.full_schema_quality import audit_full_schema_candidate
from insurance_harness.v5_preview.m158_quality import audit_m158_candidate
from insurance_harness.v5_preview.m158_run import M158RunPolicy
from insurance_harness.v5_preview.m160_run import material_backed_policy
from insurance_harness.v5_preview.source_evidence import SourcePage, classify_evidence


def test_payment_pdf_spaces_preserve_all_options_but_not_changed_amounts():
    quote = "交费年期：趸交、3 年、6 年、10 年、15 年、20 年交；"
    args = dict(
        field_id="premium_payment_term",
        evidence_quotes=(quote,),
        candidate_text=quote,
        product_display_name="测试产品",
    )
    assert audit_m158_candidate(
        proposed_value=("趸缴", "3年", "6年", "10年", "15年", "20年"), **args
    ).accepted
    assert not audit_m158_candidate(
        proposed_value=("趸缴", "3年", "6年", "10年", "15年"), **args
    ).accepted
    assert not audit_m158_candidate(
        proposed_value=("趸缴", "3年", "6年", "10年", "15年", "20年", "30年"), **args
    ).accepted


def test_list_glyph_normalization_never_normalizes_business_numbers_or_polarity():
    page = SourcePage(
        document_name="规则.pdf",
        document_sha256="a" * 64,
        page_number=1,
        text="最低保费：\n\uf06c 趸交：100 万元；\n\uf06c 3 年交：2 万元；",
    )
    quote = page.text.replace("\uf06c", "•")
    assert (
        classify_evidence((page,), quote, "pdf:规则.pdf#page=1").verification_status
        == "NORMALIZED_MATCH"
    )
    assert (
        classify_evidence(
            (page,), quote.replace("100", "10"), "pdf:规则.pdf#page=1"
        ).verification_status
        == "UNRESOLVED"
    )
    assert (
        classify_evidence(
            (page,), quote.replace("最低", "最高"), "pdf:规则.pdf#page=1"
        ).verification_status
        == "UNRESOLVED"
    )


def test_health_enum_requires_explicit_health_source_not_generic_disclosure():
    args = dict(field_id="health_declaration_requirements", proposed_value="需要健康告知")
    assert audit_full_schema_candidate(
        evidence_quotes=("健康告知事项如下：您是否患有下列疾病？",), **args
    ).accepted
    assert not audit_full_schema_candidate(
        evidence_quotes=("您应当如实告知有关情况。",), **args
    ).accepted
    assert not audit_full_schema_candidate(evidence_quotes=("无需健康告知。",), **args).accepted


def test_prepared_products_and_e_life_use_identical_policy_dependencies():
    policy = material_backed_policy(
        replace(M158RunPolicy.default(), focus_field_ids=("premium_payment_term",))
    )
    from insurance_harness.v5_preview.full_schema_quality import (
        admit_full_schema_evidence_subset,
        choose_full_schema_replacement,
    )
    from insurance_harness.v5_preview.prepared_trial import prepared_material_policy

    assert policy.evidence_admitter is admit_full_schema_evidence_subset
    assert policy.replacement_selector is choose_full_schema_replacement
    assert policy.evidence_classifier is classify_evidence
    prepared = prepared_material_policy(("premium_payment_term",))
    for name in ("evidence_admitter", "replacement_selector", "evidence_classifier",
                 "field_context_builder", "repair_hint_builder", "source_fields_only"):
        assert getattr(prepared, name) == getattr(policy, name)


def test_literal_cross_reference_keeps_clause_but_generated_omission_fails():
    source = "投保人故意伤害不承担保险责任。其他免责条款详见3.3效力中止与恢复。"
    args = dict(
        field_id="exclusions", evidence_quotes=(source,), candidate_text=source,
        product_display_name="测试寿险",
    )
    assert audit_m158_candidate(proposed_value=source, **args).accepted
    assert not audit_m158_candidate(proposed_value="故意伤害等情形详见条款", **args).accepted
    assert not audit_m158_candidate(proposed_value="详见3.3效力中止与恢复。", **args).accepted


def test_claim_check_does_not_require_underwriting_health_tests():
    from insurance_harness.v5_preview.business_field_quality import (
        audit_business_priority_candidate,
    )

    claim = "申请身故保险金须提供保险金申请书、有效身份证件、死亡证明。"
    context = (
        "【文档：保险条款.pdf｜页码：10】\n" + claim
        + "\n【文档：产品投保规则.pdf｜页码：2】\n健康告知：是否接受病理活检？"
    )
    args = dict(field_id="claim_application_deadline_and_documents",
                proposed_value=claim, evidence_quotes=(claim,))
    assert audit_business_priority_candidate(candidate_text=context, **args).accepted
    # A medical claim clause still requires the diagnosis materials it states.
    medical = "【文档：保险条款.pdf｜页码：11】\n申请疾病保险金还须提供诊断证明、病历。"
    assert not audit_business_priority_candidate(candidate_text=context + medical, **args).accepted


def test_one_verified_paragraph_can_support_multiple_literal_facts():
    from insurance_harness.v5_preview.m156_quality import audit_m156_candidate

    quote = "1. 年满18岁赔付100万元\n2. 未满18岁退还已交保费\n3. 合同终止"
    args = dict(field_id="coverage_responsibilities", evidence_quotes=(quote,),
                candidate_text=quote)
    assert audit_m156_candidate(proposed_value=quote, **args).accepted
    assert not audit_m156_candidate(
        proposed_value=quote.replace("100万元", "200万元"), **args
    ).accepted


def test_defined_footnote_reference_is_not_a_changed_business_number():
    from insurance_harness.v5_preview.business_field_quality import (
        audit_business_priority_candidate,
    )
    from insurance_harness.v5_preview.source_evidence import strip_defined_footnote_references

    source = "被保险人酒后驾驶\n15\n机动车\n16\n；\n15\n酒后驾驶指饮酒驾驶。\n16\n机动车指车辆。"
    assert strip_defined_footnote_references("保额15万元", source) == "保额15万元"
    assert strip_defined_footnote_references("酒后驾驶150", source) == "酒后驾驶150"
    args = dict(
        field_id="exclusions", proposed_value="被保险人酒后驾驶机动车；",
        evidence_quotes=("被保险人酒后驾驶机动车；", source),
        evidence_locators=("pdf:产品说明书.pdf#page=1", "pdf:保险条款.pdf#page=8"),
        candidate_text="【文档：保险条款.pdf｜页码：8】\n" + source,
    )
    assert audit_business_priority_candidate(**args).accepted


def test_full_verbatim_value_keeps_standalone_footnote_digits():
    quote = "向身故保险金受益人\n9\n给付100万元。"
    context = quote + "\n9 身故保险金受益人指依法享有请求权的人。"
    args = dict(field_id="death_benefit_rules", evidence_quotes=(quote,),
                candidate_text=context)
    assert audit_full_schema_candidate(proposed_value=(quote,), **args).accepted
    assert not audit_full_schema_candidate(
        proposed_value=(quote.replace("100万元", "200万元"),), **args
    ).accepted
