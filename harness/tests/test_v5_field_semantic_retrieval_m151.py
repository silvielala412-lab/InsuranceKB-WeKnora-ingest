from __future__ import annotations

from collections.abc import Sequence

from insurance_harness.v5_preview.catalog import load_v5_catalog
from insurance_harness.v5_preview.contracts import FieldDefinition, InsuranceSchema
from insurance_harness.v5_preview.dynamic_gapfill import (
    DynamicMaterialPage,
    _context_plan,
)
from insurance_harness.v5_preview.dynamic_ingest import (
    AllPageFieldCandidateRetriever,
    CandidateSourcePage,
    FieldCandidate,
    build_candidate_source_text,
    locate_field_candidates,
)
from insurance_harness.v5_preview.provider_trial import SourcePage


def _schema_with(field: FieldDefinition, *, insurance_class: str = "年金险") -> InsuranceSchema:
    return InsuranceSchema(
        ordinal=0,
        insurance_class=insurance_class,
        schema_id=f"insurance-product-schema-v5:{insurance_class}",
        fields=(field,),
    )


def _field(insurance_class: str, field_id: str) -> FieldDefinition:
    return next(
        field
        for field in load_v5_catalog().schema_for(insurance_class).fields
        if field.field_id == field_id
    )


def _pages(rows: Sequence[tuple[str, int, str]]) -> tuple[SourcePage, ...]:
    digest = "a" * 64
    return tuple(
        SourcePage(
            document_name=document_name,
            document_sha256=digest,
            page_number=page_number,
            text=text,
        )
        for document_name, page_number, text in rows
    )


def test_schema_semantics_recall_annuity_frequency_without_field_label() -> None:
    field = _field("年金险", "annuity_payment_frequency")
    pages = _pages(
        (
            ("保险条款.pdf", 1, "其他合同说明。"),
            (
                "保险条款.pdf",
                7,
                "生存保险金可以选择按年领取或者按月领取，具体领取日以合同约定为准。",
            ),
        )
    )

    located = locate_field_candidates(pages, _schema_with(field), (field.field_id,))

    assert located[field.field_id]
    candidate = located[field.field_id][0]
    assert candidate.page_number == 7
    assert candidate.start_offset <= pages[1].text.index("按年领取") < candidate.end_offset
    assert any(reason.startswith("schema_") for reason in candidate.reasons)


def test_weak_rate_table_pages_do_not_fill_payment_top_five() -> None:
    field = _field("年金险", "premium_payment_frequency")
    rows = [
        ("费率表.pdf", page, f"年交保险费率示例 第{page}页 1000 2000 3000")
        for page in range(1, 9)
    ]
    rows.append(
        (
            "保险条款.pdf",
            4,
            "保险费可以趸交或分期支付，分期支付可以选择年交、半年交、季交或月交。",
        )
    )

    candidates = locate_field_candidates(
        _pages(rows),
        _schema_with(field),
        (field.field_id,),
        max_pages_per_field=5,
    )[field.field_id]

    assert candidates[0].document_name == "保险条款.pdf"
    assert sum(candidate.document_name == "费率表.pdf" for candidate in candidates) <= 2


def test_answer_shaped_payment_term_outranks_period_status_wording() -> None:
    field = _field("终身寿险", "premium_payment_term")
    pages = _pages(
        (
            ("保险条款.pdf", 3, "身故时交费期间未届满，按合同约定给付保险金。"),
            ("产品说明书.pdf", 9, "投保示例：交费期6年，年交保费10万元。"),
        )
    )

    candidates = locate_field_candidates(
        pages,
        _schema_with(field, insurance_class="终身寿险"),
        (field.field_id,),
    )[field.field_id]

    assert candidates[0].page_number == 9
    assert "field_value_signal" in candidates[0].reasons


def test_all_material_fallback_keeps_middle_window_of_very_long_page() -> None:
    field = FieldDefinition(
        ordinal=1,
        category_id="03",
        category_display_name="产品定位与摘要",
        display_name="自定义信息",
        value_guidance="",
        field_id="custom_information",
        description="材料中没有固定标题的自定义信息",
        source_guidance="任意材料",
        formation_modes=("原文抽取",),
        knowledge_role="事实 Fact",
    )
    marker = "唯一支持事实位于超长页面中段"
    text = "甲" * 103_000 + marker + "乙" * 77_000
    page = DynamicMaterialPage(
        document_name="长页.pdf",
        document_sha256="b" * 64,
        page_number=1,
        text=text,
    )

    plan = _context_plan((page,), _schema_with(field), (field.field_id,), "all_material")

    assert marker in plan.text
    assert plan.scanned_page_count == 1
    assert plan.selected_page_count == 1


class _InjectedRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(
        self,
        pages: Sequence[CandidateSourcePage],
        schema: InsuranceSchema,
        field_ids: Sequence[str],
        *,
        max_pages_per_field: int | None = None,
    ) -> dict[str, tuple[FieldCandidate, ...]]:
        self.calls += 1
        field_id = field_ids[0]
        page = pages[-1]
        return {
            field_id: (
                FieldCandidate(
                    field_id=field_id,
                    document_name=page.document_name,
                    page_number=page.page_number,
                    score=999,
                    matched_keywords=("注入命中",),
                    start_offset=0,
                    end_offset=len(page.text),
                    reasons=("semantic_port",),
                ),
            )
        }


def test_candidate_source_accepts_a_pluggable_retriever() -> None:
    field = _field("年金险", "annuity_start_time")
    pages = _pages(
        (
            ("保险条款.pdf", 1, "普通文字。"),
            ("保险条款.pdf", 9, "注入命中的目标段落。"),
        )
    )
    retriever = _InjectedRetriever()

    context = build_candidate_source_text(
        pages,
        _schema_with(field),
        (field.field_id,),
        retriever=retriever,
        max_pages=1,
        max_characters=2_000,
    )

    assert retriever.calls == 1
    assert "页码：9" in context
    assert "注入命中的目标段落" in context

    dynamic_pages = tuple(
        DynamicMaterialPage(**page.model_dump())
        for page in pages
    )
    plan = _context_plan(
        dynamic_pages,
        _schema_with(field),
        (field.field_id,),
        "matched_snippets",
        retriever,
    )

    assert retriever.calls == 2
    assert "页码：9" in plan.text


class _SemanticSimilarity:
    def score(self, *, query: str, documents: Sequence[str]) -> Sequence[float]:
        assert "自定义语义事实" in query
        assert len(documents) == 2
        return (0.1, 0.91)


def test_optional_semantic_port_can_recall_a_label_free_page() -> None:
    field = FieldDefinition(
        ordinal=1,
        category_id="03",
        category_display_name="产品定位与摘要",
        display_name="自定义语义事实",
        value_guidance="",
        field_id="custom_semantic_fact",
        description="需要通过含义而不是固定标题定位的事实",
        source_guidance="任意材料",
        formation_modes=("原文抽取",),
        knowledge_role="事实 Fact",
    )
    pages = _pages(
        (
            ("材料.pdf", 1, "没有相关内容。"),
            ("材料.pdf", 2, "这段话只通过外部向量适配器获得相似度。"),
        )
    )
    retriever = AllPageFieldCandidateRetriever(
        semantic_similarity=_SemanticSimilarity()
    )

    candidates = retriever.retrieve(
        pages,
        _schema_with(field),
        (field.field_id,),
    )[field.field_id]

    assert candidates[0].page_number == 2
    assert "semantic_similarity" in candidates[0].reasons
