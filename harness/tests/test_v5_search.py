from __future__ import annotations

import json

from insurance_harness.v5_preview.contracts import (
    CandidateEvidence,
    CandidateField,
    V5CandidatePreview,
)
from insurance_harness.v5_preview.search import (
    V5SearchRequest,
    search_provider_run,
)
from insurance_harness.v5_preview.trial_contracts import (
    ProviderTrialProduct,
    V5ProviderTrialRun,
)


def _preview(product_id: str, name: str, short_name: str) -> V5CandidatePreview:
    source_revision_id = f"source-{product_id}"
    evidence = CandidateEvidence(
        source_revision_id=source_revision_id,
        locator="pdf:rules.pdf#page=1",
        quote=f"产品简称：{short_name}",
    )
    field = CandidateField.model_construct(
        ordinal=0,
        category_id="02",
        category_display_name="产品主数据",
        field_id="product_short_name",
        display_name="产品简称",
        knowledge_role="事实 Fact",
        formation_modes=("原文抽取",),
        output_kind="Fact",
        state="present",
        value=short_name,
        evidence=(evidence,),
    )
    return V5CandidatePreview.model_construct(
        contract="insurance-v5-candidate-preview.v2",
        catalog_id="insurance-product-schema-v5",
        catalog_sha256="a" * 64,
        schema_id="insurance-product-schema-v5:医疗险",
        source_revision_id=source_revision_id,
        insurance_class="医疗险",
        product_id=product_id,
        product_version_id=f"{product_id}@v1",
        product_display_name=name,
        serving_effect="NONE",
        review_publish_admission=False,
        categories=(),
        fields=(field,),
        preview_sha256="b" * 64,
    )


def _run(*previews: V5CandidatePreview) -> V5ProviderTrialRun:
    products = tuple(
        ProviderTrialProduct.model_construct(
            product_id=preview.product_id,
            product_version_id=preview.product_version_id,
            product_display_name=preview.product_display_name,
            insurance_class=preview.insurance_class,
            schema_id=preview.schema_id,
            source_revision_id=preview.source_revision_id,
            source_manifest_sha256="c" * 64,
            status="SUCCESS",
            error_code=None,
            files=(),
            attempts=(),
            preview=preview,
        )
        for preview in previews
    )
    return V5ProviderTrialRun.model_construct(products=products)


class _FakeCompletion:
    model = "qwen-plus"

    def complete(self, *, system: str, user: str) -> str:
        assert "Evidence" in system
        payload = json.loads(user)
        assert payload["query"] == "产品简称"
        return json.dumps({"answer": "两款产品都有产品简称。", "match_indices": [0, 1]})


def test_search_relates_present_fields_and_can_summarize_with_provider() -> None:
    run = _run(
        _preview("596", "平安e生保（尊享版）医疗保险", "e生保尊享"),
        _preview("594", "平安e生保（惠享版）长期医疗保险", "e生保惠享"),
    )

    result = search_provider_run(
        run,
        V5SearchRequest(query="产品简称"),
        completion=_FakeCompletion(),
    )

    assert result.provider == "bailian"
    assert result.answer == "两款产品都有产品简称。"
    assert [match.product_id for match in result.matches] == ["596", "594"]
    assert result.matches[0].evidence[0].quote == "产品简称：e生保尊享"


def test_search_returns_local_answer_without_match() -> None:
    result = search_provider_run(
        _run(_preview("596", "平安e生保（尊享版）医疗保险", "e生保尊享")),
        V5SearchRequest(query="万能账户利率"),
    )

    assert result.provider == "local"
    assert result.matches == ()
    assert "未检索到" in result.answer


def test_search_answers_a_natural_question_from_field_matches() -> None:
    result = search_provider_run(
        _run(_preview("596", "平安e生保（尊享版）医疗保险", "e生保尊享")),
        V5SearchRequest(query="e生保的产品简称是什么？"),
    )

    assert result.provider == "local"
    assert result.matches
    assert "e生保尊享" in result.answer
