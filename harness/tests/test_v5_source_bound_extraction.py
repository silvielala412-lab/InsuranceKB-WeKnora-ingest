import json

import pytest

from insurance_harness.v5_preview.source_bound_extraction import (
    SourceBoundExtractionCompletion,
    expand_source_bound_response,
)


def test_long_source_value_and_evidence_resolve_from_same_immutable_bank():
    class Completion:
        model = "test"

        def complete(self, *, system, user):
            prompt = json.loads(user)
            assert prompt["source_bank"]["Q0001"]["quote"] == "每年减少基本保险金额不得超过20%。"
            return json.dumps(
                {
                    "fields": [
                        {
                            "ordinal": 1,
                            "field_id": "sum_assured_reduction_rules",
                            "state": "present",
                            "value": {"source_ids": ["Q0001"]},
                            "evidence": [],
                        }
                    ]
                }
            )

    result = SourceBoundExtractionCompletion(Completion()).complete(
        system="",
        user=json.dumps(
            {
                "source_text": "【文档：条款.pdf｜页码：2】\n每年减少基本保险金额不得超过20%。",
                "output_contract": {},
            }
        ),
    )
    row = json.loads(result)["fields"][0]
    assert row["value"] == ["每年减少基本保险金额不得超过20%。"]
    assert row["evidence"] == [{"locator": "pdf:条款.pdf#page=2", "quote": row["value"][0]}]


def test_unknown_reference_cannot_turn_into_source_evidence():
    class Completion:
        model = "test"

        def complete(self, **kwargs):
            return json.dumps({"fields": [{"value": {"source_ids": ["Q9999"]}, "evidence": []}]})

    with pytest.raises(ValueError, match="SOURCE_BANK_REFERENCE_UNKNOWN"):
        SourceBoundExtractionCompletion(Completion()).complete(
            system="",
            user=json.dumps(
                {
                    "source_text": "【文档：条款.pdf｜页码：2】\n原文",
                    "output_contract": {},
                }
            ),
        )


def test_ordinary_quote_is_not_promoted_to_verified_by_adapter():
    from insurance_harness.v5_preview.source_evidence import SourcePage, classify_evidence

    row = {
        "value": "30万元",
        "evidence": [{"locator": "pdf:条款.pdf#page=1", "quote": "赔付30万元。"}],
    }
    expanded = expand_source_bound_response({"fields": [row]}, {})
    assert expanded["fields"][0] == row
    source = SourcePage(
        document_name="条款.pdf", document_sha256="a" * 64, page_number=1, text="赔付20万元。"
    )
    assert (
        classify_evidence(
            (source,), row["evidence"][0]["quote"], row["evidence"][0]["locator"]
        ).verification_status
        == "UNRESOLVED"
    )
