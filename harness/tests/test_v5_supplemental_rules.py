import json
import pytest

from insurance_harness.v5_preview.catalog import load_v5_catalog
from insurance_harness.v5_preview.contracts import CandidateEvidence, PluginFieldResult
from insurance_harness.v5_preview.source_evidence import SourcePage
from insurance_harness.v5_preview.supplemental_rules import (
    admit_supplemental_rule_field, select_product_rule_pages, SourceBoundSynthesisCompletion,
)


def page(number, text):
    return SourcePage(document_name="rules.pdf", document_sha256="a" * 64,
                      page_number=number, text=text)


def test_only_selected_product_pages_keep_original_numbers():
    pages = (page(1, "本规则仅适用于其他产品，代码594；未涉及"),
             page(3, "本规则仅适用于平安e生保（尊享版）医疗保险，代码596；未涉及"))
    assert select_product_rule_pages(pages, page_numbers=(3,), product_id="596",
        product_display_name="平安e生保（尊享版）医疗保险") == (pages[1],)


def test_mention_in_another_products_body_does_not_grant_scope():
    with pytest.raises(ValueError, match="RULE_PRODUCT_SCOPE_MISMATCH"):
        select_product_rule_pages((page(1, "本规则仅适用于产品A，代码123；未涉及的规则与产品B456无关"),),
                                  page_numbers=(1,), product_id="456", product_display_name="产品B")


def test_continuation_cannot_cross_into_another_product():
    with pytest.raises(ValueError, match="RULE_PRODUCT_SCOPE_MISMATCH"):
        select_product_rule_pages((page(1, "本规则仅适用于产品A(123)；未涉及"),
                                   page(2, "本规则仅适用于产品B(456)；未涉及")),
                                  page_numbers=(1, 2), product_id="123", product_display_name="产品A")


def test_synthesis_permission_does_not_relax_source_fact_validation():
    schema = load_v5_catalog().schema_for("医疗险")
    quote = "可变更社保标识。"
    evidence = CandidateEvidence(source_revision_id="test-revision", locator="pdf:rules.pdf#page=3",
                                 quote=quote, verification_status="VERIFIED", verification_error=None)
    for field_id, expected in (("product_overview", True), ("social_insurance_requirements", False)):
        definition = next(f for f in schema.fields if f.field_id == field_id)
        result = PluginFieldResult(ordinal=definition.ordinal, field_id=field_id,
                                   state="present", value="客户可办理社保标识变更。", evidence=(evidence,))
        accepted, reason = admit_supplemental_rule_field(definition, result,
            candidate_text=quote, product_display_name="测试产品")
        assert bool(accepted) == expected
        if expected:
            assert reason == "SCHEMA_SYNTHESIS_REVIEW_REQUIRED"


def test_partial_fact_array_and_unverified_synthesis_are_rejected():
    schema = load_v5_catalog().schema_for("医疗险")
    definition = next(f for f in schema.fields if f.field_id == "social_insurance_requirements")
    evidence = CandidateEvidence(source_revision_id="test-revision", locator="pdf:rules.pdf#page=3",
                                 quote="可变更社保标识。", verification_status="VERIFIED", verification_error=None)
    result = PluginFieldResult(ordinal=definition.ordinal, field_id=definition.field_id,
        state="present", value=("可变更社保标识。", "可新增附加险。"), evidence=(evidence,))
    assert admit_supplemental_rule_field(definition, result, candidate_text=evidence.quote,
                                       product_display_name="测试产品")[0] is None


def test_synthesis_reference_resolves_to_immutable_source_not_model_quote():
    class Completion:
        model = 'test'
        def complete(self, *, system, user):
            prompt = json.loads(user)
            assert prompt['evidence_bank']['Q001']['quote'] == '本产品不保证续保。'
            return json.dumps({'fields':[{'evidence':[{'evidence_id':'Q001'}]}]})
    adapter = SourceBoundSynthesisCompletion(Completion(), (page(3,'本产品不保证续保。'),))
    response = json.loads(adapter.complete(system='',user=json.dumps({
        'schema_fields':[{'formation_modes':['LLM生成']}],'output_contract':{},
    })))
    assert response['fields'][0]['evidence'] == [{'locator':'pdf:rules.pdf#page=3','quote':'本产品不保证续保。'}]


def test_synthesis_cannot_invent_reference_or_apply_bank_to_fact_field():
    class Completion:
        model = 'test'
        def complete(self, **kwargs):
            return json.dumps({'fields':[{'evidence':[{'evidence_id':'Q999'}]}]})
    adapter = SourceBoundSynthesisCompletion(Completion(), (page(1,'资料'),))
    with pytest.raises(ValueError, match='REFERENCE_UNKNOWN'):
        adapter.complete(system='',user=json.dumps({'schema_fields':[{'formation_modes':['LLM生成']}],'output_contract':{}}))
    with pytest.raises(ValueError, match='FIELD_MODE_INVALID'):
        adapter.complete(system='',user=json.dumps({'schema_fields':[{'formation_modes':['原文抽取']}],'output_contract':{}}))


def test_unverified_synthesis_remains_rejected():
    schema = load_v5_catalog().schema_for('医疗险')
    evidence = CandidateEvidence(source_revision_id='test-revision', locator='pdf:rules.pdf#page=3',
                                 quote='可变更社保标识。', verification_status='VERIFIED', verification_error=None)
    definition = next(f for f in schema.fields if f.field_id == "product_overview")
    result = PluginFieldResult(ordinal=definition.ordinal, field_id=definition.field_id,
        state="present", value="客户可办理社保标识变更。", evidence=(evidence.model_copy(update={
            "verification_status": "UNRESOLVED", "verification_error": "V5_EVIDENCE_PAGE_NOT_FOUND"}),))
    assert admit_supplemental_rule_field(definition, result, candidate_text=evidence.quote,
                                       product_display_name="测试产品")[0] is None
