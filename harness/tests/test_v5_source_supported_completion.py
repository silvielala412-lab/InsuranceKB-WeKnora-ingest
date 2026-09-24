from __future__ import annotations

import json
from pathlib import Path

import pytest

from insurance_harness.v5_preview.provider_trial import load_provider_trial_run
from insurance_harness.v5_preview.source_evidence import SourcePage
from insurance_harness.v5_preview.source_supported_completion import (
    complete_source_supported_fields,
    registered_completion_field_count,
)


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "outputs/rules-20260922/all-five/preview.json"
EXPECTED = ROOT / "outputs/rules-20260922/all-five-supplemented/preview.json"
INVENTORY = ROOT / "outputs/schema-audit-20260923/inventory.json"


def _current_material():
    if not all(path.exists() for path in (ORIGINAL, EXPECTED, INVENTORY)):
        pytest.skip("current five-product local evaluation artifacts are not available")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    pages = {
        product["id"]: tuple(SourcePage.model_validate(page) for page in product["pages"])
        for product in inventory["products"]
    }
    return load_provider_trial_run(ORIGINAL), load_provider_trial_run(EXPECTED), pages


def test_current_material_reproduces_all_22_reviewed_completions():
    original, expected, pages = _current_material()
    expected_by_id = {product.product_id: product for product in expected.products}
    changed = []
    for product in original.products:
        preview, receipts = complete_source_supported_fields(
            preview=product.preview,
            source_manifest_sha256=product.source_manifest_sha256,
            pages=pages[product.product_id],
        )
        expected_preview = expected_by_id[product.product_id].preview
        assert expected_preview is not None
        original_by_id = {field.field_id: field for field in product.preview.fields}
        expected_by_field = {field.field_id: field for field in expected_preview.fields}
        changed_ids = {receipt.field_id for receipt in receipts}
        for field in preview.fields:
            expected_field = expected_by_field[field.field_id]
            if field.field_id in changed_ids:
                assert field.state == expected_field.state == "present"
                assert field.value == expected_field.value
                assert field.evidence
                assert all(
                    item.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
                    and item.source_revision_id == preview.source_revision_id
                    for item in field.evidence
                )
            else:
                assert field == original_by_id[field.field_id]
        changed.extend(receipts)

    assert registered_completion_field_count() == 22
    assert len(changed) == 22
    assert sum(item.kind == "literal_missing" for item in changed) == 4
    assert sum(item.kind == "derived_or_synthesized" for item in changed) == 18


def test_unknown_manifest_is_never_completed():
    original, _, pages = _current_material()
    product = original.products[0]
    preview, receipts = complete_source_supported_fields(
        preview=product.preview,
        source_manifest_sha256="0" * 64,
        pages=pages[product.product_id],
    )
    assert preview == product.preview
    assert receipts == ()


def test_existing_provider_value_is_preserved():
    original, expected, pages = _current_material()
    product = original.products[0]
    filled = expected.products[0].preview
    assert filled is not None
    preview, receipts = complete_source_supported_fields(
        preview=filled,
        source_manifest_sha256=product.source_manifest_sha256,
        pages=pages[product.product_id],
    )
    assert preview == filled
    assert receipts == ()
