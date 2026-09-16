from __future__ import annotations

from insurance_harness.v5_preview.contracts import (
    CandidateEvidence,
    FieldDefinition,
    InsuranceSchema,
    PluginFieldResult,
)
from insurance_harness.v5_preview.m158_quality import (
    FeedbackIssue,
    admit_verified_evidence_subset,
    assess_feedback_issues,
    audit_payment_pair,
    build_long_field_shards,
    merge_atomic_shard_results,
)
from insurance_harness.v5_preview.provider_trial import (
    MAX_MICROBATCH_PROVIDER_CALLS,
    SourcePage,
)


def _field(field_id: str, display_name: str) -> FieldDefinition:
    return FieldDefinition(
        ordinal=1,
        category_id="07",
        category_display_name="保障责任与额度",
        display_name=display_name,
        value_guidance="",
        field_id=field_id,
        description=display_name,
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
        document_name="保险条款.pdf",
        document_sha256="a" * 64,
        page_number=number,
        text=text,
    )


def _evidence(
    quote: str,
    page: int,
    *,
    status: str = "VERIFIED",
) -> CandidateEvidence:
    return CandidateEvidence(
        source_revision_id="revision-1",
        locator=f"pdf:保险条款.pdf#page={page}",
        quote=quote,
        verification_status=status,  # type: ignore[arg-type]
        verification_error=(
            None if status in {"VERIFIED", "NORMALIZED_MATCH"} else "PAGE_NOT_FOUND"
        ),
    )


def _result(
    field_id: str,
    value: str | tuple[str, ...],
    *evidence: CandidateEvidence,
) -> PluginFieldResult:
    return PluginFieldResult(
        ordinal=1,
        field_id=field_id,
        state="present",
        value=value,
        evidence=evidence,
    )


def test_long_field_shards_keep_full_scan_receipt_and_bound_each_prompt() -> None:
    pages = (
        _page(1, "产品首页"),
        _page(2, "保险责任\n身故保险金" + "甲" * 420),
        _page(3, "身故保险金给付条件" + "乙" * 420),
        _page(4, "责任免除" + "丙" * 420),
        _page(5, "保险责任\n重大疾病保险金" + "丁" * 420),
    )
    shards = build_long_field_shards(
        pages,
        _schema(_field("coverage_responsibilities", "保险责任")),
        "coverage_responsibilities",
        product_display_name="测试重大疾病保险",
        max_characters=1_100,
    )

    assert len(shards) >= 2
    assert all(shard.scanned_page_count == 5 for shard in shards)
    assert all(len(shard.text) <= 1_100 for shard in shards)
    assert {locator for shard in shards for locator in shard.selected_locators} >= {
        "pdf:保险条款.pdf#page=2",
        "pdf:保险条款.pdf#page=5",
    }


def test_disease_definition_continuation_page_is_recalled_without_schema_label() -> None:
    pages = (
        _page(1, "疾病定义与认定标准"),
        _page(2, "严重脑中风后遗症是指被保险人确诊180日后仍有神经功能障碍。"),
        _page(8, "保险费率表"),
    )

    shards = build_long_field_shards(
        pages,
        _schema(_field("disease_definitions_and_criteria", "疾病定义与认定标准")),
        "disease_definitions_and_criteria",
        product_display_name="测试重大疾病保险",
        max_characters=1_100,
        neighbor_pages=0,
    )

    assert "pdf:保险条款.pdf#page=2" in shards[0].candidate_locators
    assert "严重脑中风后遗症" in "\n".join(shard.text for shard in shards)
    assert "保险费率表" not in "\n".join(shard.text for shard in shards)


def test_atomic_shards_merge_without_losing_distinct_definitions() -> None:
    first = _result(
        "disease_definitions_and_criteria",
        "1. 恶性肿瘤：须经组织病理学检查明确诊断",
        _evidence("恶性肿瘤须经组织病理学检查明确诊断。", 10),
    )
    second = _result(
        "disease_definitions_and_criteria",
        "1. 恶性肿瘤：须经组织病理学检查明确诊断\n2. 严重脑中风后遗症：确诊180日后仍有神经功能障碍",
        _evidence("恶性肿瘤须经组织病理学检查明确诊断。", 10),
        _evidence("严重脑中风后遗症须在确诊180日后仍有神经功能障碍。", 18),
    )

    merged = merge_atomic_shard_results(
        "disease_definitions_and_criteria", (first, second)
    )

    assert merged.state == "present"
    assert str(merged.value).count("恶性肿瘤") == 1
    assert "严重脑中风后遗症" in str(merged.value)
    assert len(merged.evidence) == 2


def test_redundant_unresolved_evidence_does_not_veto_supported_field() -> None:
    result = _result(
        "coverage_responsibilities",
        "1. 身故保险金\n2. 重大疾病保险金",
        _evidence("本合同承担身故保险金和重大疾病保险金。", 2),
        _evidence("产品责任摘要。", 99, status="UNRESOLVED"),
    )

    admitted, decision = admit_verified_evidence_subset(
        result,
        candidate_text="本合同承担身故保险金和重大疾病保险金。",
        product_display_name="测试重大疾病保险",
    )

    assert decision.accepted is True
    assert admitted is not None
    assert len(admitted.evidence) == 1


def test_unique_unsupported_atom_still_fails_closed() -> None:
    result = _result(
        "coverage_responsibilities",
        "1. 身故保险金\n2. 重大疾病保险金",
        _evidence("本合同承担身故保险金。", 2),
        _evidence("产品责任摘要。", 99, status="UNRESOLVED"),
    )

    admitted, decision = admit_verified_evidence_subset(
        result,
        candidate_text="本合同承担身故保险金。",
        product_display_name="测试重大疾病保险",
    )

    assert admitted is None
    assert decision.accepted is False
    assert "重大疾病保险金" in decision.missing_components


def test_payment_pair_understands_jiao_variants_and_detects_missing_options() -> None:
    text = "交费期间可选择10年、20年、30年；交费方式可选择趸缴或年缴。"
    incomplete = audit_payment_pair(
        term_value=("10年", "20年"),
        term_evidence=("交费期间可选择10年、20年、30年。",),
        frequency_value=("年缴",),
        frequency_evidence=("交费方式可选择趸缴或年缴。",),
        candidate_text=text,
    )
    assert incomplete.term.accepted is False
    assert incomplete.term.missing_components == ("30年",)
    assert incomplete.frequency.accepted is False
    assert incomplete.frequency.missing_components == ("趸交",)

    complete = audit_payment_pair(
        term_value=("10年", "20年", "30年"),
        term_evidence=("交费期间可选择10年、20年、30年。",),
        frequency_value=("趸缴", "年缴"),
        frequency_evidence=("交费方式可选择趸缴或年缴。",),
        candidate_text=text,
    )
    assert complete.term.accepted is True
    assert complete.frequency.accepted is True


def test_feedback_assessment_keeps_unreadable_answers_out_of_extraction() -> None:
    fields = {
        ("596", "policyholder_rights"): _result(
            "policyholder_rights",
            ("现金价值",),
            _evidence("解除合同时按照合同约定退还现金价值。", 30),
        )
    }
    issues = tuple(
        FeedbackIssue(
            issue_id=index,
            product_id="596",
            field_id="policyholder_rights",
            field_name="保单权益",
            problem_label="LLM概括错误",
            business_note=("无保单贷款" if index == 1 else "截图批注，请回看源文件"),
            workbook_row=index + 1,
        )
        for index in range(1, 31)
    )

    assessment = assess_feedback_issues(issues, fields)

    assert len(assessment) == 30
    assert assessment[0].status == "RESOLVED"
    assert all(item.status == "NOT_SCORABLE" for item in assessment[1:])


def test_feedback_short_explicit_answer_is_machine_scorable() -> None:
    fields = {
        ("1814", "policyholder_rights"): _result(
            "policyholder_rights",
            ("现金价值", "退保"),
            _evidence("解除合同时按照合同约定退还现金价值。", 30),
        )
    }
    issue = FeedbackIssue(
        issue_id=60,
        product_id="1814",
        field_id="policyholder_rights",
        field_name="保单权益",
        problem_label="未抽取",
        business_note="现金价值",
        workbook_row=61,
    )

    assessment = assess_feedback_issues((issue,), fields)

    assert assessment[0].status == "RESOLVED"
    assert assessment[0].required_terms == ("现金价值",)


def test_m158_call_envelope_matches_approved_budget() -> None:
    assert MAX_MICROBATCH_PROVIDER_CALLS >= 32
