"""Evidence-gated quality policy for material-backed Schema extraction.

This policy is intentionally generic. The catalog owns field meaning; this
module only decides whether a returned value is supported by verified source
quotes and whether it may repair a stale/unknown baseline.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from .contracts import CandidateValue, InsuranceSchema, PluginFieldResult, TriState
from .dynamic_ingest import (
    CandidateSourcePage,
    build_full_material_field_source_text,
    locate_field_candidates,
    select_candidate_source,
)
from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS
from .m156_quality import (
    M156_FOCUS_FIELD_IDS,
    M156FieldContext,
    M156FieldCoverage,
    M156FieldDecision,
    M156ReplacementDecision,
    _has_unsupported_shortcut,
    _items,
    _normalized,
)
from .m160_quality import admit_m160_evidence_subset, choose_m160_replacement
from .source_evidence import strip_defined_footnote_references

_SHORTCUTS = ("等情形", "等责任", "详见", "包括但不限于")
_SPECIALIZED_FIELDS = frozenset((*M156_FOCUS_FIELD_IDS, *BUSINESS_PRIORITY_FIELD_IDS))


def _source_text(value: str, candidate_text: str = "") -> str:
    value = re.sub(r"(?m)^[ \t]*[\uf06c•●▪][ \t]*", "", value)
    normalized = re.sub(r"[\s，,。；;：:（）()、]", "", unicodedata.normalize("NFKC", value))
    # Remove only reference numbers backed by an explicit footnote definition.
    # Do not strip arbitrary digits: age, percentages and monetary limits matter.
    return strip_defined_footnote_references(normalized, candidate_text)


def _source_supports(item: str, quotes: Sequence[str], candidate_text: str = "") -> bool:
    # Separate facts may cite different pages. Every sentence must still occur
    # in a verified quote; matching a few common words or numbers is not proof.
    parts = tuple(part.strip() for part in re.split(r"[。；;\n]+", item) if part.strip())
    normalized_quotes = tuple(_source_text(quote, candidate_text) for quote in quotes)
    if _source_text(item) in {"是", "否", "有", "无"}:
        return False
    # A whole quoted span is already supported. Splitting it at PDF line breaks
    # first can strand a superscript number after its definition was normalized.
    whole = _source_text(item, candidate_text)
    if whole and any(whole in quote for quote in normalized_quotes):
        return True
    return bool(parts) and all(
        any(_source_text(part, candidate_text) in quote for quote in normalized_quotes)
        for part in parts
    )


def build_full_schema_field_context(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    product_display_name: str,
    max_characters: int = 150_000,
) -> M156FieldContext:
    """Build a complete, bounded material window for arbitrary catalog fields."""

    requested = tuple(field_ids)
    schema_ids = {field.field_id for field in schema.fields}
    if not requested or any(field_id not in schema_ids for field_id in requested):
        raise ValueError("FULL_SCHEMA_FIELD_SET_INVALID")
    header = (
        f"【当前产品：{product_display_name}】\n"
        "【材料驱动抽取】只抽取当前产品材料中明确出现的事实；不得从字段名称、"
        "示例值或常识补全。每个返回值必须附带同页逐字 Evidence。\n"
    )
    ordered = build_full_material_field_source_text(
        pages,
        schema,
        requested,
        max_characters=min(max_characters - len(header), 95_000),
    )
    remaining = max_characters - len(header) - len(ordered) - 2
    ranked = ""
    if remaining >= 2_000 and not all(page.text.strip() in ordered for page in pages):
        ranked = select_candidate_source(
            pages,
            schema,
            requested,
            max_pages=min(48, max(12, len(requested) * 4)),
            max_characters=remaining,
            max_pages_per_field=12,
            snippet_characters=2_400,
        ).text
    text = (header + ordered + ("\n\n【字段候选窗口】\n" + ranked if ranked else ""))[
        :max_characters
    ]
    locations = {
        f"pdf:{page.document_name}#page={page.page_number}"
        for page in pages
        if f"【文档：{page.document_name}｜页码：{page.page_number}】" in text
        or f"[pdf:{page.document_name}#page={page.page_number}]" in text
    }
    located = locate_field_candidates(pages, schema, requested)
    coverage = {
        field_id: M156FieldCoverage(
            field_id=field_id,
            scanned_page_count=len(pages),
            candidate_page_count=len(located.get(field_id, ())),
            included_page_count=sum(
                candidate.locator in locations for candidate in located.get(field_id, ())
            ),
            candidate_locators=tuple(
                candidate.locator for candidate in located.get(field_id, ())
            ),
            selected_locators=tuple(
                candidate.locator
                for candidate in located.get(field_id, ())
                if candidate.locator in locations
            ),
        )
        for field_id in requested
    }
    return M156FieldContext(text=text, coverage=coverage)


def audit_full_schema_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str = "",
) -> M156FieldDecision:
    """Require every atomic returned item to be supported by verified evidence."""

    items = _items(proposed_value)
    if field_id == "health_declaration_requirements" and proposed_value in (
        "需要健康告知", "健康告知宽松", "无需健康告知",
    ):
        text = _source_text("\n".join(evidence_quotes))
        negative = any(term in text for term in ("无需健康告知", "免健康告知"))
        positive = any(
            term in text
            for term in ("须健康告知", "需要健康告知", "健康告知事项如下", "健康告知问卷")
        )
        polarity_supported = (
            (proposed_value == "需要健康告知" and positive and not negative)
            or (proposed_value == "无需健康告知" and negative and not positive)
            or (proposed_value == "健康告知宽松" and "健康告知宽松" in text and not negative)
        )
        return M156FieldDecision(
            polarity_supported,
            "SOURCE_POLARITY_SUPPORTED" if polarity_supported else "SOURCE_POLARITY_UNSUPPORTED",
            1, int(polarity_supported),
        )
    if field_id == "multiple_insured_rules" and proposed_value in ("支持双被保人/联合被保人", "否"):
        quotes = "\n".join(evidence_quotes)
        positive = any(term in _source_text(quotes) for term in (
            "可同时设置两名被保险人", "也可以同时为两名被保险人投保", "支持双被保人",
        ))
        negative = any(term in _source_text(quotes) for term in (
            "不支持双被保人", "不支持联合被保人", "只能设置一名被保险人",
        ))
        polarity_supported = (
            positive and not negative if proposed_value != "否" else negative and not positive
        )
        return M156FieldDecision(
            polarity_supported,
            "SOURCE_POLARITY_SUPPORTED" if polarity_supported else "SOURCE_POLARITY_UNSUPPORTED",
            1, int(polarity_supported),
        )
    supported = tuple(
        item
        for item in items
        if _source_supports(item, evidence_quotes, candidate_text)
    )
    if not items:
        return M156FieldDecision(False, "EMPTY_VALUE", 0, 0)
    if _has_unsupported_shortcut(proposed_value, evidence_quotes, _SHORTCUTS):
        return M156FieldDecision(
            False,
            "SOURCE_VALUE_CONTAINS_SHORTCUT",
            len(items),
            len(supported),
        )
    if len(supported) != len(items):
        return M156FieldDecision(
            False,
            "SOURCE_EVIDENCE_ITEM_MISSING",
            len(items),
            len(supported),
            tuple(item for item in items if item not in supported),
        )
    return M156FieldDecision(True, "SOURCE_VALUE_SUPPORTED", len(items), len(supported))


def admit_full_schema_evidence_subset(
    result: PluginFieldResult,
    *,
    candidate_text: str,
    product_display_name: str,
) -> tuple[PluginFieldResult | None, M156FieldDecision]:
    if result.field_id in _SPECIALIZED_FIELDS:
        return admit_m160_evidence_subset(
            result,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
    verified = tuple(
        item
        for item in result.evidence
        if item.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
    )
    decision = audit_full_schema_candidate(
        field_id=result.field_id,
        proposed_value=result.value,
        evidence_quotes=tuple(item.quote for item in verified),
        candidate_text=candidate_text,
    )
    if result.state == "present" and not verified:
        return None, M156FieldDecision(False, "SOURCE_EVIDENCE_UNVERIFIED", 0, 0)
    if (
        result.state == "present"
        and verified
        and decision.reason == "SOURCE_EVIDENCE_ITEM_MISSING"
        and isinstance(result.value, tuple)
        and decision.supported_item_count > 0
    ):
        # A bad independent array item must not erase other verified facts.
        # Preserve the rejected items in admission diagnostics for further
        # repair; this is partial extraction, never a completeness assertion.
        supported = tuple(
            item for item in result.value
            if _source_supports(item, tuple(e.quote for e in verified), candidate_text)
        )
        return (
            result.model_copy(update={"value": supported, "evidence": verified}),
            M156FieldDecision(
                True, "SOURCE_PARTIAL_EVIDENCE_ADMITTED", decision.atomic_item_count,
                len(supported), decision.missing_components,
            ),
        )
    if result.state != "present" or not verified or not decision.accepted:
        return None, decision
    return result.model_copy(update={"evidence": verified}), decision


def choose_full_schema_replacement(
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
    baseline_evidence_locators: Sequence[str] = (),
    proposed_evidence_locators: Sequence[str] = (),
) -> M156ReplacementDecision:
    if field_id in _SPECIALIZED_FIELDS:
        return choose_m160_replacement(
            field_id=field_id,
            baseline_state=baseline_state,
            baseline_value=baseline_value,
            baseline_evidence_quotes=baseline_evidence_quotes,
            proposed_state=proposed_state,
            proposed_value=proposed_value,
            proposed_evidence_quotes=proposed_evidence_quotes,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
            baseline_evidence_locators=baseline_evidence_locators,
            proposed_evidence_locators=proposed_evidence_locators,
        )
    proposed = audit_full_schema_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=proposed_evidence_quotes,
        candidate_text=candidate_text,
    )
    baseline = (
        audit_full_schema_candidate(
            field_id=field_id,
            proposed_value=baseline_value,
            evidence_quotes=baseline_evidence_quotes,
            candidate_text=candidate_text,
        )
        if baseline_state == "present"
        else None
    )
    if proposed_state != "present" or not proposed.accepted:
        return M156ReplacementDecision(
            "keep_baseline",
            "PROPOSAL_NOT_PRESENT" if proposed_state != "present" else proposed.reason,
            proposed,
            baseline,
        )
    if baseline_state == "unknown":
        return M156ReplacementDecision("replace", "SUPPORTED_SOURCE_GAP_FILL", proposed, None)
    if baseline_state == "absent_explicitly":
        return M156ReplacementDecision(
            "keep_baseline", "SOURCE_CONFLICT_REQUIRES_REVIEW", proposed, None
        )
    if baseline is not None and not baseline.accepted:
        return M156ReplacementDecision(
            "replace", "SUPPORTED_SOURCE_REPAIRS_BASELINE", proposed, baseline
        )
    if _normalized(str(baseline_value)) == _normalized(str(proposed_value)):
        return M156ReplacementDecision("keep_baseline", "SAME_NORMALIZED_VALUE", proposed, baseline)
    if baseline is not None and all(
        _source_supports(item, _items(proposed_value)) for item in _items(baseline_value)
    ):
        return M156ReplacementDecision(
            "replace", "SUPPORTED_SOURCE_ADDS_OR_REFINES_FACTS", proposed, baseline
        )
    return M156ReplacementDecision(
        "keep_baseline", "SOURCE_CONFLICT_REQUIRES_REVIEW", proposed, baseline
    )


__all__ = [
    "admit_full_schema_evidence_subset",
    "audit_full_schema_candidate",
    "build_full_schema_field_context",
    "choose_full_schema_replacement",
]
