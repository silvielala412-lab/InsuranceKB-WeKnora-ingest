"""Mission 136 RED/GREEN: deterministic candidates must pass LLM resolution."""

import json

import pytest

from insurance_harness.compiler.attempts import InMemoryAttemptLedger
from insurance_harness.compiler.models import FieldCandidate
from insurance_harness.compiler.prompts import SEMANTIC_RESOLUTION_PROMPT_VERSION
from insurance_harness.compiler.semantic_resolution import resolve_candidates
from insurance_harness.goldenset.pdf import PageText
from insurance_harness.schemas import FieldSpec


class QueueClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return self.responses.pop(0)


def _candidate(value: str, quote: str) -> FieldCandidate:
    return FieldCandidate(
        field_id="product_short_name",
        field_name="险种简称",
        group="basic_info",
        doc="保险条款.pdf",
        value=value,
        tri_state="present",
        evidence=[{"page": 1, "quote": quote}],  # type: ignore[list-item]
        origin="fastpath",
        confidence="high",
    )


PAGES = [
    PageText(
        page_no=1,
        text="产品名称：平安e生保（尊享版）医疗保险。险种简称：e生保尊享。以下简称本产品。",
    )
]
PAGES_BY_DOC = {"保险条款.pdf": PAGES}
PAGES_BY_DOC_CROSS = {
    "产品说明书.pdf": [PageText(page_no=1, text="产品名称：平安医疗保险。")],
    "保险条款.pdf": PAGES,
}
FIELD = FieldSpec(
    name="险种简称",
    field_id="product_short_name",
    source_sheet="t",
)


@pytest.mark.asyncio
async def test_rule_candidates_are_sent_together_to_llm() -> None:
    client = QueueClient(
        [
            json.dumps(
                [
                    {
                        "field_id": "product_short_name",
                        "doc": "保险条款.pdf",
                        "value": "e生保尊享",
                        "tri_state": "present",
                        "evidence": [{"page": 1, "quote": "险种简称：e生保尊享"}],
                    }
                ],
                ensure_ascii=False,
            )
        ]
    )
    out = await resolve_candidates(
        client,
        "平安e生保（尊享版）医疗保险",
        FIELD,
        [_candidate("本产品", "以下简称本产品"), _candidate("e生保尊享", "险种简称：e生保尊享")],
        PAGES_BY_DOC,
        ledger=InMemoryAttemptLedger(),
    )
    assert len(client.prompts) == 1
    assert "以下简称本产品" in client.prompts[0][1]
    assert "险种简称：e生保尊享" in client.prompts[0][1]
    assert out.value == "e生保尊享"
    assert out.origin == "semantic_resolve"
    assert out.metadata["candidate_origins"] == ["fastpath", "fastpath"]
    assert out.metadata["candidate_evidence"][1][0]["page"] == 1
    assert out.metadata["candidate_evidence"][1][0]["quote"] == "险种简称：e生保尊享"
    assert out.metadata["candidate_context_pages"] == [[1], [1]]
    assert out.metadata["semantic_prompt_version"] == SEMANTIC_RESOLUTION_PROMPT_VERSION


@pytest.mark.asyncio
async def test_unverified_llm_value_is_unresolved_and_keeps_rejected_candidate() -> None:
    client = QueueClient(
        [
            json.dumps(
                [
                    {
                        "field_id": "product_short_name",
                        "value": "模型自行编造",
                        "tri_state": "present",
                        "evidence": [{"page": 1, "quote": "原文没有这句话"}],
                    }
                ],
                ensure_ascii=False,
            ),
        ]
    )
    out = await resolve_candidates(
        client,
        "平安e生保（尊享版）医疗保险",
        FIELD,
        [_candidate("e生保尊享", "险种简称：e生保尊享")],
        PAGES_BY_DOC,
        ledger=InMemoryAttemptLedger(),
    )
    assert out.tri_state == "unknown"
    assert out.unknown_reason == "candidate_unresolved"
    assert out.value is None and not out.evidence
    assert out.metadata["rejected_value"] == "模型自行编造"
    assert len(client.prompts) == 1


@pytest.mark.asyncio
async def test_cross_document_selection_uses_selected_candidate_document() -> None:
    client = QueueClient(
        [
            json.dumps(
                [
                    {
                        "field_id": "product_short_name",
                        "value": "e生保尊享",
                        "tri_state": "present",
                        "evidence": [{"page": 1, "quote": "险种简称：e生保尊享"}],
                        "selected_candidate": 1,
                    }
                ],
                ensure_ascii=False,
            )
        ]
    )
    first = _candidate("平安医疗", "产品名称：平安医疗保险")
    second = _candidate("e生保尊享", "险种简称：e生保尊享").model_copy(
        update={"doc": "保险条款.pdf"}
    )
    first = first.model_copy(update={"doc": "产品说明书.pdf"})
    out = await resolve_candidates(
        client,
        "平安医疗保险",
        FIELD,
        [first, second],
        PAGES_BY_DOC_CROSS,
        ledger=InMemoryAttemptLedger(),
    )
    assert out.tri_state == "present"
    assert out.doc == "保险条款.pdf"


@pytest.mark.asyncio
async def test_wrong_field_response_is_unresolved() -> None:
    client = QueueClient([json.dumps([{"field_id": "other_field", "value": "误套"}])])
    out = await resolve_candidates(
        client,
        "平安医疗保险",
        FIELD,
        [_candidate("e生保尊享", "险种简称：e生保尊享")],
        PAGES_BY_DOC,
        ledger=InMemoryAttemptLedger(),
    )
    assert out.tri_state == "unknown"
    assert out.unknown_reason == "candidate_unresolved"
    assert out.metadata["semantic_failure"] == "field_id_mismatch"
