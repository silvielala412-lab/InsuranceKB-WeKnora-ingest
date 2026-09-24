from __future__ import annotations

import json
from dataclasses import dataclass

from insurance_harness.v5_preview.business_field_quality import (
    audit_business_priority_candidate,
    expand_service_table_values,
    normalize_business_field_value,
    supported_special_coverage_tags,
)
from insurance_harness.v5_preview.catalog import load_v5_catalog
from insurance_harness.v5_preview.contracts import (
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
)
from insurance_harness.v5_preview.dynamic_ingest import (
    build_candidate_source_text,
    locate_field_candidates,
)
from insurance_harness.v5_preview.llm_plugin import SchemaGuidedLlmPlugin, _schema_prompt
from insurance_harness.v5_preview.m156_quality import M156_FIELD_STRATEGIES
from insurance_harness.v5_preview.m160_quality import choose_m160_replacement
from insurance_harness.v5_preview.m160_run import (
    M160_FOCUS_FIELD_IDS,
    M160_MAX_COMPACT_FIELDS,
)
from insurance_harness.v5_preview.source_evidence import SourcePage


def _field(field_id: str) -> FieldDefinition:
    return next(
        field
        for field in load_v5_catalog().schema_for("医疗险").fields
        if field.field_id == field_id
    )


def _schema(*field_ids: str) -> InsuranceSchema:
    fields = tuple(_field(field_id) for field_id in field_ids)
    return InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=fields,
    )


def _page(document: str, number: int, text: str) -> SourcePage:
    return SourcePage(
        document_name=document,
        document_sha256="a" * 64,
        page_number=number,
        text=text,
    )


def test_external_drug_context_keeps_terms_brochure_and_clause_continuation() -> None:
    field_id = "out_of_hospital_special_drug_coverage"
    pages = (
        _page("产品说明书.pdf", 2, "外购药服务：可在合作药店购药。"),
        _page("保险条款.pdf", 17, "1.5.4 院外药品费用保险金：须由医院专科医生开具处方。"),
        _page("保险条款.pdf", 18, "申请人须在指定药店购药，并在购药前完成用药审核。"),
        _page("保险条款.pdf", 19, "本责任给付比例为100%，年度限额200万元。"),
    )

    candidates = locate_field_candidates(
        pages,
        _schema(field_id),
        (field_id,),
        max_pages_per_field=2,
    )[field_id]
    context = build_candidate_source_text(
        pages,
        _schema(field_id),
        (field_id,),
        max_pages=4,
        max_characters=12_000,
        max_pages_per_field=2,
    )

    assert {item.document_name for item in candidates} == {"产品说明书.pdf", "保险条款.pdf"}
    assert candidates[0].document_name == "保险条款.pdf"
    assert "1.5.4 院外药品费用保险金" in context
    assert "购药前完成用药审核" in context
    assert "年度限额200万元" in context


def test_priority_prompt_requires_cross_file_detail_for_all_reported_fields() -> None:
    field_ids = (
        "special_coverage_and_exclusion_tags",
        "exclusions",
        "out_of_hospital_special_drug_coverage",
        "reimbursable_expense_scope",
        "reimbursement_rate_rules",
        "claim_application_deadline_and_documents",
        "policyholder_rights",
        "medical_service_benefits",
    )
    schema = _schema(*field_ids)
    request = IngestRequest(
        source_revision_id="source-business-priority",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试医疗保险",
        reviewed_insurance_class="医疗险",
        source_text="测试材料",
    )

    prompt = _schema_prompt(request, schema)

    assert "Schema value_guidance 中的标签只是示例" in prompt
    assert "说明书摘要不能视为完整答案" in prompt
    assert "保险条款中的正式责任必须至少提供一条条款 Evidence" in prompt
    assert "不得只返回‘合理且必要的医疗费用’等摘要" in prompt
    assert "不得把不同责任的比例合并为一个通用比例" in prompt
    assert "申请/诉讼时效" in prompt
    assert "不得把保险公司的核定或给付时效写成客户申请时效" in prompt
    assert "附加险不得继承仅适用于主险的权益" in prompt
    assert "办理材料、处理期限" in prompt
    assert "不要把多个服务压成‘就医服务等’" in prompt


def test_priority_fields_are_in_the_m160_context_and_run_targets() -> None:
    target_ids = {
        "special_coverage_and_exclusion_tags",
        "out_of_hospital_special_drug_coverage",
        "reimbursable_expense_scope",
        "reimbursement_rate_rules",
        "claim_application_deadline_and_documents",
        "medical_service_benefits",
    }

    assert target_ids <= set(M156_FIELD_STRATEGIES)
    assert target_ids <= set(M160_FOCUS_FIELD_IDS)
    assert M160_MAX_COMPACT_FIELDS <= 4


@dataclass
class _PolarityCompletion:
    model: str = "qwen-plus"

    def complete(self, *, system: str, user: str) -> str:
        field = json.loads(user)["schema_fields"][0]
        return json.dumps(
            {
                "fields": [
                    {
                        "ordinal": field["ordinal"],
                        "field_id": field["field_id"],
                        "state": "present",
                        "value": ["既往症可赔"],
                        "evidence": [
                            {
                                "locator": "pdf:保险条款.pdf#page=12",
                                "quote": "被保险人因既往症导致的医疗费用，本公司不承担保险责任。",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )


def test_negative_evidence_corrects_a_positive_special_coverage_tag() -> None:
    schema = _schema("special_coverage_and_exclusion_tags")
    source = "被保险人因既往症导致的医疗费用，本公司不承担保险责任。"
    request = IngestRequest(
        source_revision_id="source-polarity",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试医疗保险",
        reviewed_insurance_class="医疗险",
        source_text=source,
    )

    result = SchemaGuidedLlmPlugin(completion=_PolarityCompletion()).extract(request, schema)

    assert result.fields[0].value == ("既往症不可赔",)


def test_negative_evidence_canonicalizes_an_exclusion_special_coverage_tag() -> None:
    assert normalize_business_field_value(
        "special_coverage_and_exclusion_tags",
        ("既往症除外不保",),
        ("被保险人所患既往症引起的费用，我们不承担给付责任。",),
    ) == ("既往症不可赔",)


def test_equivalent_negative_tag_canonicalization_can_replace_complete_baseline() -> None:
    evidence = ("既往症相关医疗费用，我们不承担给付保险金的责任。",)

    decision = choose_m160_replacement(
        field_id="special_coverage_and_exclusion_tags",
        baseline_state="present",
        baseline_value=("既往症除外不保",),
        baseline_evidence_quotes=evidence,
        proposed_state="present",
        proposed_value=("既往症不可赔",),
        proposed_evidence_quotes=evidence,
        candidate_text=evidence[0],
        product_display_name="测试医疗保险",
    )

    assert decision.action == "replace"
    assert decision.reason == "SUPPORTED_EQUIVALENT_TAG_CANONICALIZATION"


def test_special_tag_admission_keeps_only_evidence_supported_items() -> None:
    tags = supported_special_coverage_tags(
        ("既往症不可赔", "无证据疾病不可赔"),
        ("被保险人所患既往症引起的费用，我们不承担给付责任。",),
    )

    assert tags == ("既往症不可赔",)


def test_service_table_expands_material_names_and_frequencies() -> None:
    table = (
        "服务场景 服务权益 服务次数\n"
        "在线问诊 不限次\n"
        "院前就医 就医陪诊 1次/年\n"
        "院中治疗 一码垫付 不限次\n"
        "院后康复 上门康复护理 1次/住院"
    )

    value = expand_service_table_values(("就医绿通", "费用垫付"), (table,))

    assert value == (
        "在线问诊：不限次",
        "就医陪诊：1次/年",
        "一码垫付：不限次",
        "上门康复护理：1次/住院",
    )


@dataclass
class _LongEvidenceCompletion:
    model: str = "qwen-plus"

    def complete(self, *, system: str, user: str) -> str:
        field = json.loads(user)["schema_fields"][0]
        quote = "等待期材料。" * 400
        return json.dumps(
            {
                "fields": [
                    {
                        "ordinal": field["ordinal"],
                        "field_id": field["field_id"],
                        "state": "present",
                        "value": "等待期材料",
                        "evidence": [{"locator": "pdf:保险条款.pdf#page=1", "quote": quote}],
                    }
                ]
            },
            ensure_ascii=False,
        )


def test_long_evidence_is_chunked_without_dropping_the_field() -> None:
    schema = _schema("waiting_period")
    source = "等待期材料。" * 400
    request = IngestRequest(
        source_revision_id="source-long-evidence",
        catalog_id="insurance-product-schema-v5",
        schema_id=schema.schema_id,
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试医疗保险",
        reviewed_insurance_class="医疗险",
        source_text=source,
    )

    result = SchemaGuidedLlmPlugin(completion=_LongEvidenceCompletion()).extract(request, schema)

    field = result.fields[0]
    assert field.state == "present"
    assert len(field.evidence) > 1
    assert all(len(item.quote) <= 2000 for item in field.evidence)


def test_reimbursement_summary_fails_when_material_lists_more_expense_items() -> None:
    material = (
        "合理且必要并实际发生的床位费、药品费、检查费、治疗费、手术费和护理费，"
        "不限基本医疗保险目录。"
    )
    decision = audit_business_priority_candidate(
        field_id="reimbursable_expense_scope",
        proposed_value="合理且必要并实际发生的床位费、药品费",
        evidence_quotes=("合理且必要并实际发生的床位费、药品费",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.reason == "BUSINESS_FIELD_COMPONENTS_INCOMPLETE"
    assert {"检查检验费", "治疗费", "手术费", "护理费"} <= set(
        decision.missing_components
    )


def test_detailed_reimbursement_accepts_component_level_evidence() -> None:
    material = (
        "合理且必要并实际发生的床位费、药品费、材料费、检查检验费、治疗费、"
        "手术费和护理费，包含目录外费用。"
    )
    decision = audit_business_priority_candidate(
        field_id="reimbursable_expense_scope",
        proposed_value=(
            "住院费用包括床位费、药品费、医用材料费、检查费、检验费、治疗费、"
            "手术费及护理费；以合理且必要、实际发生的费用为限，并覆盖目录外项目。"
        ),
        evidence_quotes=(material,),
        candidate_text=material,
    )

    assert decision.accepted is True
    assert decision.reason == "BUSINESS_FIELD_COMPLETE"


def test_reimbursement_rate_requires_terms_evidence_and_all_material_conditions() -> None:
    value = (
        "一般医疗：使用社会医疗保险结算按100%给付，未使用社会医疗保险按60%给付；"
        "院外购药：预审核通过按100%给付，未预审核按60%给付；"
        "特药：医保目录内药品未经医保结算按60%给付，其余按100%给付。"
    )
    material = (
        "【文档：产品说明书.pdf｜页码：18】\n" + value + "\n"
        "【文档：保险条款.pdf｜页码：9】\n" + value
    )
    brochure_only = audit_business_priority_candidate(
        field_id="reimbursement_rate_rules",
        proposed_value=value,
        evidence_quotes=(value,),
        evidence_locators=("pdf:产品说明书.pdf#page=18",),
        candidate_text=material,
    )
    terms_supported = audit_business_priority_candidate(
        field_id="reimbursement_rate_rules",
        proposed_value=value,
        evidence_quotes=(value,),
        evidence_locators=("pdf:保险条款.pdf#page=9",),
        candidate_text=material,
    )

    assert brochure_only.accepted is False
    assert brochure_only.reason == "BUSINESS_FIELD_AUTHORITATIVE_SOURCE_MISSING"
    assert terms_supported.accepted is True


def test_reimbursement_rate_cannot_drop_social_insurance_condition() -> None:
    material = (
        "使用社会医疗保险结算按100%给付，未使用社会医疗保险按60%给付；"
        "院外购药预审核通过按100%给付，未预审核按60%给付。"
    )
    decision = audit_business_priority_candidate(
        field_id="reimbursement_rate_rules",
        proposed_value="本产品按100%给付",
        evidence_quotes=("本产品按100%给付",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.reason == "BUSINESS_FIELD_COMPONENTS_INCOMPLETE"
    assert {"社会医疗保险结算条件", "未使用社会医疗保险结算", "预审核条件"} <= set(
        decision.missing_components
    )


def test_claim_materials_must_keep_deadline_and_document_groups() -> None:
    material = (
        "保险事故发生后10日内通知本公司。请求给付保险金的诉讼时效为二年。"
        "申请人应提交保险金申请书、有效身份证件、诊断证明、病历、费用票据和费用清单。"
    )
    decision = audit_business_priority_candidate(
        field_id="claim_application_deadline_and_documents",
        proposed_value="保险事故发生后10日内通知本公司",
        evidence_quotes=("保险事故发生后10日内通知本公司。",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert "申请或诉讼时效" in decision.missing_components
    assert "保险金申请书" in decision.missing_components
    assert "身份或关系证明" in decision.missing_components


def test_claim_processing_deadline_cannot_be_labelled_as_application_deadline() -> None:
    material = (
        "保险事故发生后10日内通知我们。收到保险金申请书后5日内作出核定，"
        "情形复杂的30日内作出核定；达成给付协议后10日内履行给付义务。"
        "申请人还应提交有效身份证件、诊断证明、病历、费用票据和结算清单。"
    )
    decision = audit_business_priority_candidate(
        field_id="claim_application_deadline_and_documents",
        proposed_value=(
            "保险事故通知时限：10日内；理赔申请时效：收到申请后5日内核定，"
            "复杂情形30日内核定，协议后10日内给付；申请材料：保险金申请书、"
            "有效身份证件、诊断证明、病历、费用票据和结算清单。"
        ),
        evidence_quotes=(material,),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.reason == "CLAIM_DEADLINE_SEMANTIC_CONFLATION"


def test_claim_processing_and_payment_deadlines_accept_separate_labels() -> None:
    material = (
        "保险事故发生后10日内通知我们。收到保险金申请书后5日内作出核定，"
        "情形复杂的30日内作出核定；达成给付协议后10日内履行给付义务。"
        "申请人还应提交有效身份证件、诊断证明、病历、费用票据和结算清单。"
    )
    decision = audit_business_priority_candidate(
        field_id="claim_application_deadline_and_documents",
        proposed_value=(
            "保险事故通知时限：10日内；保险公司核定时效：收到申请后5日内核定，"
            "复杂情形30日内核定；保险金给付时效：达成协议后10日内给付；"
            "申请材料：保险金申请书、有效身份证件、诊断证明、病历、费用票据和结算清单。"
        ),
        evidence_quotes=(material,),
        candidate_text=material,
    )

    assert decision.accepted is True


def test_policy_rights_cannot_drop_materials_and_refund_deadline() -> None:
    evidence = (
        "解除合同时，您需要填写解除合同通知书，并提供保险合同及有效身份证件。"
        "我们自收到解除合同通知书之日起30日内退还合同的现金价值。",
    )
    decision = audit_business_priority_candidate(
        field_id="policyholder_rights",
        proposed_value="现金价值、退保",
        evidence_quotes=evidence,
        evidence_locators=("pdf:保险条款.pdf#page=26",),
        candidate_text="【文档：保险条款.pdf｜页码：26】\n" + evidence[0],
    )

    assert decision.accepted is False
    assert decision.reason == "POLICY_RIGHT_DETAILS_INCOMPLETE"
    assert {"解除合同通知书", "保险合同", "有效身份证件", "30日"} <= set(
        decision.missing_components
    )


def test_policy_rights_accepts_supported_process_materials_and_deadline() -> None:
    evidence = (
        "解除合同时，您需要填写解除合同通知书，并提供保险合同及有效身份证件。"
        "我们自收到解除合同通知书之日起30日内退还合同的现金价值。",
    )
    decision = audit_business_priority_candidate(
        field_id="policyholder_rights",
        proposed_value=(
            "退保及现金价值：填写解除合同通知书并提供保险合同和有效身份证件，"
            "收到通知书之日起30日内退还现金价值"
        ),
        evidence_quotes=evidence,
        evidence_locators=("pdf:保险条款.pdf#page=26",),
        candidate_text="【文档：保险条款.pdf｜页码：26】\n" + evidence[0],
    )

    assert decision.accepted is True


def test_external_drug_requires_terms_evidence_when_terms_are_available() -> None:
    value = (
        "院外特定药品责任：适用特定药品清单；须由专科医生开具处方；"
        "在指定药店购药并事前申请审核；保险金额200万元；给付比例100%。"
    )
    material = (
        "【文档：产品说明书.pdf｜页码：6】\n" + value + "\n"
        "【文档：保险条款.pdf｜页码：8】\n1.5.4 " + value
    )
    brochure_only = audit_business_priority_candidate(
        field_id="out_of_hospital_special_drug_coverage",
        proposed_value=value,
        evidence_quotes=(value,),
        evidence_locators=("pdf:产品说明书.pdf#page=6",),
        candidate_text=material,
    )
    terms_supported = audit_business_priority_candidate(
        field_id="out_of_hospital_special_drug_coverage",
        proposed_value=value,
        evidence_quotes=(value,),
        evidence_locators=("pdf:保险条款.pdf#page=8",),
        candidate_text=material,
    )

    assert brochure_only.accepted is False
    assert brochure_only.reason == "BUSINESS_FIELD_AUTHORITATIVE_SOURCE_MISSING"
    assert terms_supported.accepted is True


def test_same_value_can_upgrade_from_brochure_to_terms_evidence() -> None:
    value = (
        "院外特定药品责任：适用特定药品清单；须由专科医生开具处方；"
        "在指定药店购药并事前申请审核；保险金额200万元；给付比例100%。"
    )
    candidate_text = (
        "【文档：产品说明书.pdf｜页码：6】\n" + value + "\n"
        "【文档：保险条款.pdf｜页码：8】\n1.5.4 " + value
    )
    decision = choose_m160_replacement(
        field_id="out_of_hospital_special_drug_coverage",
        baseline_state="present",
        baseline_value=value,
        baseline_evidence_quotes=(value,),
        baseline_evidence_locators=("pdf:产品说明书.pdf#page=6",),
        proposed_state="present",
        proposed_value=value,
        proposed_evidence_quotes=(value,),
        proposed_evidence_locators=("pdf:保险条款.pdf#page=8",),
        candidate_text=candidate_text,
        product_display_name="测试医疗保险",
    )

    assert decision.action == "replace"
    assert decision.reason == "SUPPORTED_PROPOSAL_REPAIRS_INCOMPLETE_BASELINE"


def test_service_list_cannot_drop_a_material_supported_service() -> None:
    material = "本产品提供就医绿通、在线问诊和费用垫付服务。"
    decision = audit_business_priority_candidate(
        field_id="medical_service_benefits",
        proposed_value=("就医绿通", "费用垫付"),
        evidence_quotes=("本产品提供就医绿通、在线问诊和费用垫付服务。",),
        candidate_text=material,
    )

    assert decision.accepted is False
    assert decision.missing_components == ("在线问诊",)
