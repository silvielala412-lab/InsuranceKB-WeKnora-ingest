from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from .catalog import load_v5_catalog
from .contracts import CandidateValue, EvidenceResolution, InsuranceSchema, TriState
from .dynamic_ingest import CandidateSourcePage
from .m156_quality import (
    M156_FOCUS_FIELD_IDS,
    M156_LONG_ATOMIC_FIELD_IDS,
    M156FieldContext,
    M156FieldDecision,
    M156ReplacementDecision,
    _evidence_supports,
    _items,
    _normalized,
    audit_m156_candidate,
    build_m156_field_context,
)
from .provider_trial import ProviderTrialError
from .source_evidence import SourcePage, classify_evidence

M157_MAX_CALLS = 24
M157_EXPECTED_PRIMARY_CALLS = 20

_SHORTCUT_MARKERS = ("等责任", "等情形", "详见", "包括但不限于")
_MAIN_CONTRACT_ONLY_MARKERS = (
    "适用主险合同",
    "适用于主险合同",
    "按主险合同",
    "主险合同适用",
)
_PUNCTUATION = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def plan_m157_batches(insurance_class: str) -> tuple[tuple[str, ...], ...]:
    """Give each long legal field its own output budget."""

    schema = load_v5_catalog().schema_for(insurance_class)
    applicable = tuple(
        field.field_id for field in schema.fields if field.field_id in M156_FOCUS_FIELD_IDS
    )
    long_batches = tuple(
        (field_id,)
        for field_id in applicable
        if field_id in M156_LONG_ATOMIC_FIELD_IDS
    )
    compact = tuple(
        field_id for field_id in applicable if field_id not in M156_LONG_ATOMIC_FIELD_IDS
    )
    batches = (*long_batches, *((compact,) if compact else ()))
    if set(field_id for batch in batches for field_id in batch) != set(applicable):
        raise ProviderTrialError("M157_BATCH_TOPOLOGY_INVALID")
    return batches


def _product_scope(product_display_name: str) -> str:
    return "附加险" if "附加" in product_display_name else "当前独立产品或主险"


def build_m157_field_context(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    product_display_name: str,
    max_characters: int = 180_000,
) -> M156FieldContext:
    """Build an all-page receipt plus field-specific clause windows."""

    if not product_display_name.strip():
        raise ValueError("M157_PRODUCT_NAME_REQUIRED")
    header = (
        f"【当前产品：{product_display_name}】\n"
        f"【当前产品作用域：{_product_scope(product_display_name)}】\n"
        "【适用范围要求】只归并明确适用于当前产品的责任、免责和权益；材料引用主险、"
        "附加险或其他合同时必须保留适用对象，不得跨合同归并。\n"
    )
    base = build_m156_field_context(
        pages,
        schema,
        field_ids,
        max_characters=max(10_000, max_characters - len(header)),
    )
    return M156FieldContext(
        text=(header + base.text)[:max_characters],
        coverage=base.coverage,
    )


def _audit_atomic_m157(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> M156FieldDecision:
    items = _items(value)
    supported = sum(
        any(_evidence_supports(item, quote) for quote in evidence_quotes) for item in items
    )
    if any(marker in str(value) for marker in _SHORTCUT_MARKERS):
        return M156FieldDecision(
            accepted=False,
            reason="ATOMIC_VALUE_CONTAINS_SHORTCUT",
            atomic_item_count=len(items),
            supported_item_count=supported,
        )
    missing = tuple(
        item
        for item in items
        if not any(_evidence_supports(item, quote) for quote in evidence_quotes)
    )
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="ATOMIC_EVIDENCE_ITEM_UNSUPPORTED",
            atomic_item_count=len(items),
            supported_item_count=supported,
            missing_components=missing,
        )
    return M156FieldDecision(
        accepted=bool(items),
        reason="ATOMIC_ITEMS_SUPPORTED" if items else "EMPTY_VALUE",
        atomic_item_count=len(items),
        supported_item_count=supported,
    )


def _is_wrong_scope_quote(product_display_name: str, quote: str) -> bool:
    return "附加" in product_display_name and any(
        marker in _normalized(quote) for marker in _MAIN_CONTRACT_ONLY_MARKERS
    )


def audit_m157_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
    product_display_name: str,
) -> M156FieldDecision:
    if field_id in M156_LONG_ATOMIC_FIELD_IDS:
        return _audit_atomic_m157(proposed_value, evidence_quotes)
    if field_id == "policyholder_rights":
        applicable_quotes = tuple(
            quote
            for quote in evidence_quotes
            if not _is_wrong_scope_quote(product_display_name, quote)
        )
        decision = audit_m156_candidate(
            field_id=field_id,
            proposed_value=proposed_value,
            evidence_quotes=applicable_quotes,
            candidate_text=candidate_text,
        )
        if not decision.accepted and len(applicable_quotes) != len(evidence_quotes):
            return M156FieldDecision(
                accepted=False,
                reason="POLICY_RIGHT_WRONG_PRODUCT_SCOPE",
                atomic_item_count=decision.atomic_item_count,
                supported_item_count=decision.supported_item_count,
                missing_components=decision.missing_components,
            )
        return decision
    return audit_m156_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=evidence_quotes,
        candidate_text=candidate_text,
    )


def choose_m157_replacement(
    *,
    field_id: str,
    baseline_state: TriState,
    baseline_value: CandidateValue | None,
    baseline_evidence_quotes: Sequence[str],
    proposed_state: TriState,
    proposed_value: CandidateValue | None,
    proposed_evidence_quotes: Sequence[str],
    candidate_text: str,
    product_display_name: str,
) -> M156ReplacementDecision:
    proposed_audit = audit_m157_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=proposed_evidence_quotes,
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )
    baseline_audit = (
        audit_m157_candidate(
            field_id=field_id,
            proposed_value=baseline_value,
            evidence_quotes=baseline_evidence_quotes,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
        if baseline_state == "present"
        else None
    )
    if proposed_state != "present" or not proposed_audit.accepted:
        return M156ReplacementDecision(
            action="keep_baseline",
            reason=(
                "PROPOSAL_NOT_PRESENT"
                if proposed_state != "present"
                else proposed_audit.reason
            ),
            proposed_audit=proposed_audit,
            baseline_audit=baseline_audit,
        )
    if baseline_state == "unknown":
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_GAP_FILL",
            proposed_audit=proposed_audit,
            baseline_audit=None,
        )
    if baseline_state == "absent_explicitly":
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="EXPLICIT_ABSENCE_CONFLICT_REQUIRES_REVIEW",
            proposed_audit=proposed_audit,
            baseline_audit=None,
        )
    if baseline_audit is not None and not baseline_audit.accepted:
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_PROPOSAL_REPAIRS_INCOMPLETE_BASELINE",
            proposed_audit=proposed_audit,
            baseline_audit=baseline_audit,
        )
    if _normalized(str(baseline_value)) == _normalized(str(proposed_value)):
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="SAME_NORMALIZED_VALUE",
            proposed_audit=proposed_audit,
            baseline_audit=baseline_audit,
        )
    if (
        baseline_audit is not None
        and proposed_audit.atomic_item_count > baseline_audit.atomic_item_count
        and proposed_audit.supported_item_count >= baseline_audit.supported_item_count
    ):
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_PROPOSAL_ADDS_ATOMIC_ITEMS",
            proposed_audit=proposed_audit,
            baseline_audit=baseline_audit,
        )
    return M156ReplacementDecision(
        action="keep_baseline",
        reason="COMPLETE_BASELINE_CONFLICT_REQUIRES_REVIEW",
        proposed_audit=proposed_audit,
        baseline_audit=baseline_audit,
    )


def _compact_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _PUNCTUATION.sub("", normalized).lower()


def _fuzzy_coverage(quote: str, page_text: str) -> float:
    compact_quote = _compact_evidence(quote)
    compact_page = _compact_evidence(page_text)
    if not compact_quote or len(compact_quote) < 12:
        return 0.0
    if compact_quote in compact_page:
        return 1.0
    width = 12
    starts = range(0, max(1, len(compact_quote) - width + 1), 6)
    anchors = tuple(compact_quote[start : start + width] for start in starts)
    anchors = tuple(anchor for anchor in anchors if len(anchor) == width)
    if not anchors:
        return 0.0
    return sum(anchor in compact_page for anchor in anchors) / len(anchors)


def classify_m157_evidence(
    pages: Sequence[SourcePage],
    quote: str,
    advisory_locator: str,
) -> EvidenceResolution:
    direct = classify_evidence(pages, quote, advisory_locator)
    if direct.verification_status != "UNRESOLVED":
        return direct

    scored = tuple(
        (page, _fuzzy_coverage(quote, page.text))
        for page in pages
    )
    candidates = tuple(
        (page, score) for page, score in scored if score >= 0.82
    )
    if not candidates:
        return direct
    best_score = max(score for _, score in candidates)
    best = tuple(page for page, score in candidates if best_score - score <= 0.03)
    if len(best) != 1:
        return EvidenceResolution(
            locator=advisory_locator,
            verification_status="AMBIGUOUS",
            verification_error="V5_EVIDENCE_PAGE_AMBIGUOUS",
        )
    page = best[0]
    return EvidenceResolution(
        locator=f"pdf:{page.document_name}#page={page.page_number}",
        verification_status="NORMALIZED_MATCH",
    )


__all__ = [
    "M157_EXPECTED_PRIMARY_CALLS",
    "M157_MAX_CALLS",
    "audit_m157_candidate",
    "build_m157_field_context",
    "choose_m157_replacement",
    "classify_m157_evidence",
    "plan_m157_batches",
]
