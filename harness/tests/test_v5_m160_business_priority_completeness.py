from __future__ import annotations

from pathlib import Path

from insurance_harness.v5_preview import m160_run
from insurance_harness.v5_preview.catalog import load_v5_catalog
from insurance_harness.v5_preview.m154_concurrency import ProductConcurrencyProfile
from insurance_harness.v5_preview.m160_quality import (
    audit_waiting_period_components,
    parse_waiting_period_components,
)


def test_waiting_period_keeps_all_business_components() -> None:
    text = (
        "自合同生效之日起（含生效当日）90日内，被保险人因疾病确诊，"
        "我们不承担给付责任；因意外伤害发生的，不受90日等待期限制。"
        "等待期内确诊重大疾病的，返还所交保险费，合同终止。"
        "续保或重新投保经审核同意的，无等待期。"
    )

    components = parse_waiting_period_components(text)

    assert components.duration == "90日"
    assert components.start
    assert components.applicability
    assert components.accident_exception
    assert components.within_wait_consequence
    assert components.special_exceptions
    decision = audit_waiting_period_components(components, text)
    assert decision.accepted is True
    assert decision.missing_components == ()


def test_waiting_period_missing_consequence_fails_closed() -> None:
    text = "等待期为90日，自合同生效之日起计算，疾病责任适用，意外伤害无等待期。"

    components = parse_waiting_period_components(text)
    decision = audit_waiting_period_components(components, text)

    assert decision.accepted is False
    assert "within_wait_consequence" in decision.missing_components


def test_single_product_preview_does_not_require_feedback_workbook(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = (object(), {}, {})

    def fake_run_m158(**kwargs: object) -> tuple[object, dict[object, object], dict[object, object]]:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(m160_run._base, "run_m158", fake_run_m158)

    result = m160_run.run_m160(
        baseline_path=Path("baseline.json"),
        sample_root=Path("samples"),
        serious_illness_root=Path("illness"),
        supplemental_root_596=Path("supplemental"),
        business_feedback_path=None,
        output_path=Path("result.json"),
        audit_output_path=Path("audit.json"),
        assessment_output_path=Path("assessment.json"),
        completion_factory=lambda: object(),  # type: ignore[return-value]
        concurrency_profile=ProductConcurrencyProfile(max_products=1),
        product_ids=("596",),
    )

    assert result == expected
    assert captured["product_ids"] == ("596",)
    assert captured["business_feedback_path"] is None


def test_compact_retry_scope_excludes_long_fields() -> None:
    assert "coverage_responsibilities" not in m160_run.M160_COMPACT_FIELD_IDS
    assert "exclusions" not in m160_run.M160_COMPACT_FIELD_IDS
    assert "waiting_period" in m160_run.M160_COMPACT_FIELD_IDS
    assert "reimbursable_expense_scope" in m160_run.M160_COMPACT_FIELD_IDS

    medical_schema = load_v5_catalog().schema_for("医疗险")
    applicable_long = tuple(
        field.field_id
        for field in medical_schema.fields
        if field.field_id in m160_run.M158_LONG_FIELD_IDS
        and field.field_id in m160_run.M160_COMPACT_FIELD_IDS
    )
    assert applicable_long == ()
