"""LLM-first semantic resolution for deterministic field candidates (Mission 136).

规则、模板和外部映射只能贡献候选。该模块负责把同一字段的候选和对应页上下文
交给 LLM，再复用既有 quote/类型/兼容性校验；它不拥有发布或 Active 权限。
"""

from collections.abc import Mapping, Sequence
from typing import Any

from ..goldenset.pdf import PageText
from ..schemas import FieldSpec
from .attempts import AttemptLedger, InMemoryAttemptLedger
from .extract import _candidate_from_item, call_and_parse, run_validation_chain
from .llm import ModelClient
from .models import FieldCandidate
from .prompts import (
    SEMANTIC_RESOLUTION_PROMPT_VERSION,
    SEMANTIC_RESOLUTION_SYSTEM,
    build_semantic_resolution_user,
)


def _candidate_audit(
    candidates: Sequence[FieldCandidate],
    pages_by_doc: Mapping[str, Sequence[PageText]],
) -> dict[str, Any]:
    return {
        "candidate_origins": [candidate.origin for candidate in candidates],
        "candidate_values": [candidate.value for candidate in candidates],
        "candidate_docs": [candidate.doc for candidate in candidates],
        "candidate_evidence": [
            [evidence.model_dump(mode="json") for evidence in candidate.evidence]
            for candidate in candidates
        ],
        "candidate_context_pages": [
            sorted(
                {
                    nearby_page
                    for evidence in candidate.evidence
                    for nearby_page in range(max(1, evidence.page - 1), evidence.page + 2)
                    if nearby_page
                    in {page.page_no for page in pages_by_doc.get(candidate.doc, ())}
                }
            )
            for candidate in candidates
        ],
    }


def _source_doc(
    item: Mapping[str, Any],
    resolved: FieldCandidate,
    candidates: Sequence[FieldCandidate],
) -> str:
    explicit_doc = str(item.get("doc") or "").strip()
    candidate_docs = {candidate.doc for candidate in candidates}
    if explicit_doc in candidate_docs:
        return explicit_doc
    selected = item.get("selected_candidate")
    if isinstance(selected, int) and 0 <= selected < len(candidates):
        return candidates[selected].doc
    # A malformed/missing selector should not silently point to an unrelated PDF.
    # Prefer the only document, otherwise keep the first candidate for a later audit.
    if len(candidate_docs) == 1:
        return next(iter(candidate_docs))
    matching = [
        candidate.doc
        for candidate in candidates
        if candidate.value is not None and candidate.value == resolved.value
    ]
    return matching[0] if matching else candidates[0].doc


def _unresolved(
    field: FieldSpec,
    candidates: Sequence[FieldCandidate],
    *,
    reason: str,
    pages_by_doc: Mapping[str, Sequence[PageText]],
    attempts: list[dict[str, Any]] | None = None,
    rejected_value: str | None = None,
) -> FieldCandidate:
    metadata: dict[str, Any] = {
        **_candidate_audit(candidates, pages_by_doc),
        "semantic_prompt_version": SEMANTIC_RESOLUTION_PROMPT_VERSION,
        "semantic_failure": reason,
    }
    if attempts:
        metadata["attempts"] = attempts
    if rejected_value is not None:
        metadata["rejected_value"] = rejected_value
    first_doc = candidates[0].doc if candidates else ""
    return FieldCandidate(
        field_id=field.field_id,
        field_name=field.name,
        group=candidates[0].group if candidates else "",
        doc=first_doc,
        tri_state="unknown",
        unknown_reason="candidate_unresolved",
        origin="semantic_resolve",
        confidence="low",
        metadata=metadata,
    )


async def resolve_candidates(
    client: ModelClient,
    product_name: str,
    field: FieldSpec,
    candidates: Sequence[FieldCandidate],
    pages_by_doc: Mapping[str, Sequence[PageText]],
    *,
    ledger: AttemptLedger | None = None,
) -> FieldCandidate:
    """Resolve all candidates for one field through one auditable LLM call."""
    if not candidates:
        return _unresolved(
            field, candidates, reason="no_candidates", pages_by_doc=pages_by_doc
        )
    ledger = ledger if ledger is not None else InMemoryAttemptLedger()
    user = build_semantic_resolution_user(
        product_name, field, candidates, pages_by_doc
    )
    try:
        call = await call_and_parse(
            client,
            SEMANTIC_RESOLUTION_SYSTEM,
            user,
            ledger=ledger,
            field_ids=(field.field_id,),
            stage="semantic_resolve",
            prompt_version=SEMANTIC_RESOLUTION_PROMPT_VERSION,
        )
    except Exception as exc:
        return _unresolved(
            field,
            candidates,
            reason=f"transport:{type(exc).__name__}",
            pages_by_doc=pages_by_doc,
        )

    attempts = [
        attempt.model_dump(mode="json")
        for attempt in ledger.attempts_for_field(field.field_id)
    ]
    if not call.items:
        return _unresolved(
            field,
            candidates,
            reason="parse_failed",
            pages_by_doc=pages_by_doc,
            attempts=attempts,
        )
    matching_items = [
        entry for entry in call.items if str(entry.get("field_id")) == field.field_id
    ]
    if not matching_items:
        return _unresolved(
            field,
            candidates,
            reason="field_id_mismatch",
            pages_by_doc=pages_by_doc,
            attempts=attempts,
        )
    item = matching_items[0]
    provisional = _candidate_from_item(item, field, candidates[0].doc)
    source_doc = _source_doc(item, provisional, candidates)
    resolved = provisional.model_copy(update={"doc": source_doc})
    resolved = resolved.model_copy(
        update={
            "origin": "semantic_resolve",
            "confidence": "medium",
            "metadata": {
                **resolved.metadata,
                **_candidate_audit(candidates, pages_by_doc),
                "candidate_data_qualities": [
                    candidate.metadata.get("data_quality")
                    for candidate in candidates
                    if candidate.metadata.get("data_quality") is not None
                ],
                "data_quality": "llm_extracted",
                "semantic_prompt_version": SEMANTIC_RESOLUTION_PROMPT_VERSION,
                "selected_candidate": item.get("selected_candidate"),
                "attempts": attempts,
                "winning_attempt_id": call.producing_attempt_id,
            },
        }
    )
    pages = pages_by_doc.get(source_doc, pages_by_doc.get(candidates[0].doc, ()))
    validated, error = run_validation_chain(resolved, field, pages)
    if error is not None:
        return _unresolved(
            field,
            candidates,
            reason=f"validation:{error}",
            pages_by_doc=pages_by_doc,
            attempts=attempts,
            rejected_value=resolved.value,
        )
    if validated.tri_state == "unknown":
        unresolved = _unresolved(
            field,
            candidates,
            reason="model_unknown_or_incompatible",
            pages_by_doc=pages_by_doc,
            attempts=attempts,
            rejected_value=resolved.value,
        )
        if resolved.metadata.get("compat_reject"):
            unresolved = unresolved.model_copy(
                update={
                    "metadata": {
                        **unresolved.metadata,
                        "compat_reject": resolved.metadata["compat_reject"],
                    }
                }
            )
        return unresolved
    return validated.model_copy(
        update={
            "origin": "semantic_resolve",
            "metadata": {
                **validated.metadata,
                "attempts": attempts,
                "winning_attempt_id": call.producing_attempt_id,
            },
        }
    )


__all__ = ["resolve_candidates"]
