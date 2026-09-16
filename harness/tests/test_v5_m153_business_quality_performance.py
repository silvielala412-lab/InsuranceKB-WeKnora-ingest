from __future__ import annotations

from pathlib import Path
from time import sleep

import pytest

from insurance_harness.v5_preview.m153_quality import (
    M153BusinessIssue,
    M153IssueKind,
    M153ValueSnapshot,
    RunExtractionIndex,
    TablePage,
    build_table_context,
    compare_field_value,
    execute_bounded_batches,
    load_business_quality_baselines,
    normalize_issue_types,
    plan_bounded_batches,
    policy_for_issue_types,
)

BUSINESS_ROOT = Path(r"E:\wiki badcase ly")


def test_issue_labels_are_normalized_without_losing_multiple_labels() -> None:
    assert normalize_issue_types("抽取不全；LLM概括不全；显示问题") == (
        "incomplete",
        "summary_incomplete",
        "display_only",
    )


def test_business_workbooks_form_a_frozen_closed_baseline() -> None:
    if not BUSINESS_ROOT.is_dir():
        pytest.skip("business workbook fixture is not mounted")
    baselines = load_business_quality_baselines(BUSINESS_ROOT)
    assert len(baselines) == 4
    assert sum(len(item.issues) for item in baselines) >= 47
    assert sum(item.field_id is not None for item in baselines for item in item.issues) == 47
    assert all(len(item.sha256) == 64 for item in baselines)
    assert any(issue.embedded_asset_sha256 for item in baselines for issue in item.issues)
    assert any(issue.field_id is None for item in baselines for issue in item.issues)
    annuity = next(item for item in baselines if item.product_id == "1830")
    coverage_term = next(
        issue for issue in annuity.issues if issue.field_id == "coverage_term_category"
    )
    assert coverage_term.required_facts == ("长期",)
    assert coverage_term.allowed_values == ("长期",)


def test_table_context_preserves_document_page_table_row_and_cell_coordinates() -> None:
    table_page = TablePage.from_rows(
        document_name="费率表.pdf",
        page_number=12,
        table_index=2,
        headers=("年龄", "年缴保费", "缴费期间"),
        rows=(("30", "1200", "20年"),),
    )
    context = build_table_context((table_page,))
    assert "费率表.pdf#page=12" in context
    assert "table=2" in context
    assert "row=1" in context
    assert "col=2" in context
    assert "年缴保费" in context


def test_rate_table_is_not_routed_to_unrelated_field() -> None:
    table_page = TablePage.from_rows(
        document_name="费率表.pdf",
        page_number=12,
        table_index=1,
        headers=("年龄", "年缴保费"),
        rows=(("30", "1200"),),
    )
    index = RunExtractionIndex(
        pages=(
            {"document_name": "产品说明书.pdf", "page_number": 1, "text": "产品简介"},
            {"document_name": "费率表.pdf", "page_number": 12, "text": "年龄 年缴保费"},
        ),
        table_pages=(table_page,),
    )
    assert "年缴保费" not in index.context_for(("product_name",))
    assert "年缴保费" in index.context_for(("premium_amount",))
    assert index.candidate_build_count == 2


def test_m152_batch_reuses_the_same_candidate_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    from insurance_harness.v5_preview import m152_gapfill
    from insurance_harness.v5_preview.dynamic_gapfill import (
        DynamicMaterialBundle,
        DynamicMaterialPage,
    )

    original = m152_gapfill.locate_field_candidates
    calls = 0

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(m152_gapfill, "locate_field_candidates", counted)
    material = m152_gapfill._LoadedMaterial(
        bundle=DynamicMaterialBundle(
            product_version_id="fixture-1",
            source_revision_id="source-1",
            pages=(
                DynamicMaterialPage(
                    document_name="保险条款.pdf",
                    document_sha256="a" * 64,
                    page_number=1,
                    text="本产品等待期为30日。",
                ),
            ),
        ),
        source_manifest_sha256="c" * 64,
        scanned_page_count=1,
        unreadable_page_locators=(),
        candidate_cache={},
        context_cache={},
    )
    fields = ("waiting_period",)
    first = m152_gapfill._context_for_batch(material, "医疗险", fields)
    second = m152_gapfill._context_for_batch(material, "医疗险", fields)
    assert first == second
    assert calls == 1


def test_regression_comparator_keeps_confirmed_value_when_candidate_is_unknown_or_forbidden(
    ) -> None:
    baseline = M153ValueSnapshot(state="present", value="等待期30天", evidence_quality=4)
    unknown = M153ValueSnapshot(state="unknown", value=None, evidence_quality=0)
    forbidden = M153ValueSnapshot(state="present", value="等待期90天", evidence_quality=4)
    assert compare_field_value(baseline, unknown).decision == "keep_baseline"
    result = compare_field_value(
        baseline,
        forbidden,
        forbidden_facts=("90天",),
    )
    assert result.decision == "regression"
    assert "forbidden" in result.reason


def test_bounded_batches_are_limited_and_merge_in_stable_order() -> None:
    batches = plan_bounded_batches(("b", "a", "c", "d"), batch_size=2, max_workers=2)
    assert batches == (("b", "a"), ("c", "d"))

    def finish_out_of_order(indexed_batch: tuple[int, tuple[str, ...]]) -> str:
        index, batch = indexed_batch
        sleep(0.01 if index == 0 else 0)
        return "".join(batch)

    assert execute_bounded_batches(
        batches, worker=finish_out_of_order, max_workers=2
    ) == ("ba", "cd")


def test_issue_type_controls_reextract_merge_and_summary_strategy() -> None:
    policy = policy_for_issue_types(
        (M153IssueKind.incomplete, M153IssueKind.summary_wrong)
    )
    assert policy.reextract is True
    assert policy.merge_all_candidate_facts is True
    assert policy.atomic_fact_first is True
    assert policy.forbidden_fact_check is True
    assert policy_for_issue_types((M153IssueKind.display_only,)).reextract is False


def test_issue_contract_accepts_business_constraints_without_prompt_text() -> None:
    issue = M153BusinessIssue(
        workbook_name="e生保尊享-问题.xlsx",
        sheet_name="Sheet1",
        row_number=18,
        display_name="宽限期",
        field_id="premium_grace_period",
        issue_kinds=(M153IssueKind.incomplete,),
        note="业务问题记录",
        required_facts=("30天",),
        forbidden_facts=("90天",),
        allowed_values=(),
        embedded_asset_sha256=(),
    )
    assert issue.required_facts == ("30天",)
