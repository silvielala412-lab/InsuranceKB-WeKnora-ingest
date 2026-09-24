"""Execution completeness checks, separate from semantic accuracy and publication."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import PluginFieldResult, V5CandidatePreview
from .trial_artifacts import write_provider_trial_run
from .trial_contracts import V5ProviderTrialRun


def confirmed_material_fields(source_manifest_sha256: str) -> tuple[str, ...]:
    """Use a frozen minimum regression set only for the exact reviewed material."""
    path = Path(__file__).parent / "data" / "v5_material_regression.json"
    profiles = json.loads(path.read_text(encoding="utf-8"))["products"]
    for profile in profiles:
        if profile["source_manifest_sha256"] == source_manifest_sha256:
            return tuple(item["field_id"] for item in profile["required_fields"])
    return ()


@dataclass(frozen=True, slots=True)
class ExtractionCompletion:
    status: str
    unplanned_field_ids: tuple[str, ...]
    retry_batch_ids: tuple[int, ...]
    regressed_field_ids: tuple[str, ...]
    confirmed_missing_field_ids: tuple[str, ...]
    pending_source_field_ids: tuple[str, ...]
    confirmed_field_count: int
    confirmed_present_count: int
    confirmed_field_coverage: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_extraction_completion(
    *,
    preview: V5CandidatePreview,
    baseline: V5CandidatePreview,
    expected_field_ids: Sequence[str],
    planned_batches: Mapping[int, Sequence[str]],
    batch_results: Mapping[int, Sequence[PluginFieldResult] | None],
    confirmed_field_ids: Sequence[str] = (),
) -> ExtractionCompletion:
    """A failed/missing shard is incomplete even when another shard filled its field.

    Confirmed fields must come from independently checked material for this exact
    source revision. Unknown answers never prove absence of supporting material.
    """
    if (preview.product_version_id, preview.source_revision_id) != (
        baseline.product_version_id, baseline.source_revision_id
    ):
        raise ValueError("EXTRACTION_COMPLETION_IDENTITY_DRIFT")
    current = {f.field_id: f for f in preview.fields}
    previous = {f.field_id: f for f in baseline.fields}
    if set(current) != set(previous):
        raise ValueError("EXTRACTION_COMPLETION_SCHEMA_DRIFT")
    expected = set(expected_field_ids)
    confirmed = set(confirmed_field_ids)
    planned = {fid for fields in planned_batches.values() for fid in fields}
    if not (expected | confirmed | planned) <= current.keys():
        raise ValueError("EXTRACTION_COMPLETION_UNKNOWN_FIELD")
    if set(batch_results) - planned_batches.keys():
        raise ValueError("EXTRACTION_COMPLETION_UNPLANNED_BATCH")
    retry = []
    for batch, fields in planned_batches.items():
        results = batch_results.get(batch)
        ids = [result.field_id for result in results] if results is not None else []
        if results is None or len(ids) != len(set(ids)) or set(ids) != set(fields):
            retry.append(batch)
    regressed = tuple(sorted(
        fid for fid, field in current.items()
        if previous[fid].state != "unknown" and field.state == "unknown"
    ))
    missing = tuple(sorted(fid for fid in confirmed if current[fid].state != "present"))
    pending = tuple(sorted(
        fid for fid, field in current.items()
        if field.state == "unknown" and "原文抽取" in field.formation_modes
    ))
    unplanned = tuple(sorted(expected - planned))
    return ExtractionCompletion(
        status=(
            "REPAIR_REQUIRED" if unplanned or retry or regressed or missing
            else "REVIEW_REQUIRED" if pending else "EXECUTION_CHECKS_PASSED"
        ),
        unplanned_field_ids=unplanned,
        retry_batch_ids=tuple(sorted(retry)),
        regressed_field_ids=regressed,
        confirmed_missing_field_ids=missing,
        pending_source_field_ids=pending,
        confirmed_field_count=len(confirmed),
        confirmed_present_count=len(confirmed) - len(missing),
        confirmed_field_coverage=(len(confirmed) - len(missing)) / len(confirmed)
        if confirmed else None,
    )


def require_complete_execution(reports: Sequence[ExtractionCompletion]) -> None:
    if not reports or any(report.status == "REPAIR_REQUIRED" for report in reports):
        raise ValueError("EXTRACTION_INCOMPLETE_REPAIR_REQUIRED")


def write_checked_trial(
    path: Path, run: V5ProviderTrialRun, reports: Sequence[ExtractionCompletion]
) -> Path:
    """Persist diagnostics on failure without replacing the normal preview artifact."""
    blocked = not reports or any(report.status == "REPAIR_REQUIRED" for report in reports)
    destination = path.with_name(path.stem + ".incomplete" + path.suffix) if blocked else path
    if destination.exists():
        raise ValueError("EXTRACTION_RESULT_ALREADY_EXISTS")
    write_provider_trial_run(destination, run)
    return destination
