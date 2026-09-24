from types import SimpleNamespace

import pytest

from insurance_harness.v5_preview.contracts import PluginFieldResult
from insurance_harness.v5_preview.extraction_completion import (
    audit_extraction_completion,
    confirmed_material_fields,
    require_complete_execution,
    write_checked_trial,
)


def preview(**states):
    return SimpleNamespace(
        product_version_id="test-1", source_revision_id="source-1",
        fields=tuple(SimpleNamespace(field_id=fid, state=state, formation_modes=("原文抽取",))
                     for fid, state in states.items()),
    )


def result(fid):
    return PluginFieldResult(ordinal=0, field_id=fid, state="unknown")


def test_failed_long_shard_is_not_hidden_by_present_field():
    before = preview(exclusions="unknown")
    report = audit_extraction_completion(
        baseline=before, preview=preview(exclusions="present"),
        expected_field_ids=("exclusions",),
        planned_batches={1: ("exclusions",), 2: ("exclusions",)},
        batch_results={1: (result("exclusions"),), 2: None},
    )
    assert report.retry_batch_ids == (2,)
    with pytest.raises(ValueError, match="EXTRACTION_INCOMPLETE_REPAIR_REQUIRED"):
        require_complete_execution((report,))


def test_unplanned_field_and_missing_batch_response_are_blocking():
    data = preview(exclusions="unknown", waiting_period="unknown")
    report = audit_extraction_completion(
        baseline=data, preview=data,
        expected_field_ids=("exclusions", "waiting_period"),
        planned_batches={1: ("exclusions",)}, batch_results={},
    )
    assert report.unplanned_field_ids == ("waiting_period",)
    assert report.retry_batch_ids == (1,)


def test_known_material_gap_and_baseline_loss_cannot_be_offset_by_other_fields():
    report = audit_extraction_completion(
        baseline=preview(exclusions="present", waiting_period="unknown"),
        preview=preview(exclusions="unknown", waiting_period="present"),
        expected_field_ids=("exclusions", "waiting_period"),
        planned_batches={1: ("exclusions", "waiting_period")},
        batch_results={1: (result("exclusions"), result("waiting_period"))},
        confirmed_field_ids=("exclusions", "waiting_period"),
    )
    assert report.regressed_field_ids == ("exclusions",)
    assert report.confirmed_missing_field_ids == ("exclusions",)
    assert report.confirmed_field_coverage == 0.5


def test_unknown_is_review_required_and_missing_gold_is_not_zero_or_full_recall():
    data = preview(exclusions="unknown")
    report = audit_extraction_completion(
        baseline=data, preview=data, expected_field_ids=("exclusions",),
        planned_batches={1: ("exclusions",)}, batch_results={1: (result("exclusions"),)},
    )
    assert report.status == "REVIEW_REQUIRED"
    assert report.confirmed_field_coverage is None
    require_complete_execution((report,))


def test_successful_retry_closes_batch_but_does_not_claim_semantic_accuracy():
    data = preview(exclusions="present")
    report = audit_extraction_completion(
        baseline=data, preview=data, expected_field_ids=("exclusions",),
        planned_batches={1: ("exclusions",)}, batch_results={1: (result("exclusions"),)},
    )
    assert report.status == "EXECUTION_CHECKS_PASSED"
    assert report.confirmed_field_coverage is None


def test_duplicate_results_and_changed_source_identity_fail_closed():
    data = preview(exclusions="unknown")
    args = dict(baseline=data, preview=data, expected_field_ids=("exclusions",),
                planned_batches={1: ("exclusions",)},
                batch_results={1: (result("exclusions"), result("exclusions"))})
    assert audit_extraction_completion(**args).retry_batch_ids == (1,)
    other = preview(exclusions="unknown")
    other.source_revision_id = "changed-source"
    with pytest.raises(ValueError, match="IDENTITY_DRIFT"):
        audit_extraction_completion(**{**args, "preview": other})


def test_material_regression_expectations_never_apply_to_another_source():
    fields = confirmed_material_fields(
        "216b968732ad66b903e943bb12867c270614a61bf84dc7e534c6d8a3d8ef1ca0"
    )
    assert "coverage_increase_rules" in fields
    assert "exclusions" in fields
    assert confirmed_material_fields("0" * 64) == ()
    with pytest.raises(ValueError, match="EXTRACTION_INCOMPLETE_REPAIR_REQUIRED"):
        require_complete_execution(())


def test_blocked_run_preserves_previous_preview(tmp_path, monkeypatch):
    from insurance_harness.v5_preview import extraction_completion

    output = tmp_path / "preview.json"
    output.write_text("previous verified result", encoding="utf-8")
    written = []
    monkeypatch.setattr(extraction_completion, "write_provider_trial_run",
                        lambda path, run: written.append(path))
    data = preview(exclusions="unknown")
    report = audit_extraction_completion(
        preview=data, baseline=data, expected_field_ids=("exclusions",),
        planned_batches={1: ("exclusions",)}, batch_results={1: None},
    )
    destination = write_checked_trial(output, object(), (report,))
    assert destination == tmp_path / "preview.incomplete.json"
    assert written == [destination]
    assert output.read_text(encoding="utf-8") == "previous verified result"
