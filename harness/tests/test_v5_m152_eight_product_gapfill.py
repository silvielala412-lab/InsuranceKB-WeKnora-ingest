from __future__ import annotations

from insurance_harness.v5_preview.catalog import catalog_sha256, load_v5_catalog
from insurance_harness.v5_preview.contracts import (
    CandidateEvidence,
    CandidateField,
    PluginFieldResult,
    V5CandidatePreview,
)
from insurance_harness.v5_preview.ingest import preview_digest
from insurance_harness.v5_preview.m152_gapfill import (
    M152FieldIssue,
    merge_m152_batch,
    split_target_batches,
)


def _candidate_field(field_id: str, *, value: str | None = None) -> CandidateField:
    schema = load_v5_catalog().schema_for("医疗险")
    definition = next(field for field in schema.fields if field.field_id == field_id)
    evidence = (
        CandidateEvidence(
            source_revision_id="source-1",
            locator="pdf:条款.pdf#page=2",
            quote="本合同等待期为30日。",
        ),
    ) if value is not None else ()
    return CandidateField(
        ordinal=definition.ordinal,
        category_id=definition.category_id,
        category_display_name=definition.category_display_name,
        field_id=definition.field_id,
        display_name=definition.display_name,
        knowledge_role=definition.knowledge_role,
        formation_modes=definition.formation_modes,
        output_kind=definition.output_kind,
        state="present" if value is not None else "unknown",
        value=value,
        evidence=evidence,
    )


def _preview() -> V5CandidatePreview:
    catalog = load_v5_catalog()
    schema = catalog.schema_for("医疗险")
    fields = (
        _candidate_field("target_customer_profile"),
        _candidate_field("waiting_period", value="30日"),
    )
    payload = {
        "contract": "insurance-v5-candidate-preview.v2",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog_sha256(catalog),
        "schema_id": schema.schema_id,
        "source_revision_id": "source-1",
        "insurance_class": schema.insurance_class,
        "product_id": "596",
        "product_version_id": "596-1",
        "product_display_name": "测试医疗险",
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "categories": [],
        "fields": [field.model_dump(mode="json") for field in fields],
    }
    identity = {
        key: value for key, value in payload.items() if key not in {"categories", "fields"}
    }
    return V5CandidatePreview(
        **identity,
        categories=(),
        fields=fields,
        preview_sha256=preview_digest(payload),
    )


def _result(field_id: str, value: str, quote: str) -> PluginFieldResult:
    definition = next(
        field
        for field in load_v5_catalog().schema_for("医疗险").fields
        if field.field_id == field_id
    )
    return PluginFieldResult(
        ordinal=definition.ordinal,
        field_id=field_id,
        state="present",
        value=value,
        evidence=(
            CandidateEvidence(
                source_revision_id="source-1",
                locator="pdf:条款.pdf#page=2",
                quote=quote,
            ),
        ),
    )


def test_split_target_batches_is_stable_and_bounded() -> None:
    fields = tuple(f"field_{index}" for index in range(17))

    batches = split_target_batches(fields)

    assert tuple(len(batch) for batch in batches) == (8, 8, 1)
    assert tuple(field for batch in batches for field in batch) == fields


def test_merge_fills_unknown_but_preserves_conflicting_existing_value() -> None:
    preview = _preview()
    issues = {
        "target_customer_profile": M152FieldIssue(
            display_name="适用人群",
            issue_labels=("未抽取",),
        ),
        "waiting_period": M152FieldIssue(
            display_name="等待期",
            issue_labels=("抽取不全",),
        ),
    }
    results = (
        _result(
            "target_customer_profile",
            "成人和少儿",
            "投保年龄为出生满28日到60周岁。",
        ),
        _result("waiting_period", "60日", "本合同等待期为60日。"),
    )

    merged, receipts = merge_m152_batch(
        preview=preview,
        results=results,
        issues=issues,
        candidate_locators={
            "target_customer_profile": ("pdf:条款.pdf#page=2",),
            "waiting_period": ("pdf:条款.pdf#page=2",),
        },
        batch_index=1,
        provider_call=1,
    )

    by_id = {field.field_id: field for field in merged.fields}
    receipt_by_id = {receipt.field_id: receipt for receipt in receipts}
    assert by_id["target_customer_profile"].value == "成人和少儿"
    assert receipt_by_id["target_customer_profile"].status == "FILLED"
    assert receipt_by_id["target_customer_profile"].changed is True
    assert by_id["waiting_period"].value == "30日"
    assert receipt_by_id["waiting_period"].status == "CONFLICT"
    assert receipt_by_id["waiting_period"].proposed is not None
    assert receipt_by_id["waiting_period"].proposed.value == "60日"
    assert receipt_by_id["waiting_period"].changed is False


def test_gapfill_does_not_auto_admit_explicit_absence() -> None:
    preview = _preview()
    definition = next(
        field
        for field in load_v5_catalog().schema_for("医疗险").fields
        if field.field_id == "target_customer_profile"
    )
    absence = PluginFieldResult(
        ordinal=definition.ordinal,
        field_id=definition.field_id,
        state="absent_explicitly",
        evidence=(
            CandidateEvidence(
                source_revision_id="source-1",
                locator="pdf:条款.pdf#page=2",
                quote="本合同等待期为30日。",
            ),
        ),
    )

    merged, receipts = merge_m152_batch(
        preview=preview,
        results=(absence,),
        issues={
            definition.field_id: M152FieldIssue(
                display_name=definition.display_name,
                issue_labels=("未抽取",),
            )
        },
        candidate_locators={definition.field_id: ("pdf:条款.pdf#page=2",)},
        batch_index=1,
        provider_call=1,
    )

    result = next(field for field in merged.fields if field.field_id == definition.field_id)
    assert result.state == "unknown"
    assert receipts[0].status == "ABSENCE_NEEDS_REVIEW"
    assert receipts[0].proposed is not None
    assert receipts[0].proposed.state == "absent_explicitly"
