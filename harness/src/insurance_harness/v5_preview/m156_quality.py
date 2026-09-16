from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .contracts import CandidateValue, InsuranceSchema, TriState
from .dynamic_ingest import (
    CandidateSourcePage,
    build_full_material_field_source_text,
    locate_field_candidates,
    select_candidate_source,
)
from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS

M156_FOCUS_FIELD_IDS: tuple[str, ...] = (
    "coverage_responsibilities",
    "exclusions",
    "premium_payment_term",
    "premium_payment_frequency",
    "policyholder_rights",
    "waiting_period",
    "disease_definitions_and_criteria",
)

M156_LONG_ATOMIC_FIELD_IDS = frozenset(
    {
        "coverage_responsibilities",
        "exclusions",
        "disease_definitions_and_criteria",
    }
)

_M156_CONTEXT_FIELD_IDS = tuple(
    dict.fromkeys((*M156_FOCUS_FIELD_IDS, *BUSINESS_PRIORITY_FIELD_IDS))
)


@dataclass(frozen=True, slots=True)
class M156FieldStrategy:
    field_id: str
    value_shape: str
    require_all_page_scan: bool = True
    require_item_evidence: bool = False


@dataclass(frozen=True, slots=True)
class M156FieldCoverage:
    field_id: str
    scanned_page_count: int
    candidate_page_count: int
    included_page_count: int
    candidate_locators: tuple[str, ...]
    selected_locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class M156FieldContext:
    text: str
    coverage: Mapping[str, M156FieldCoverage]


@dataclass(frozen=True, slots=True)
class M156FieldDecision:
    accepted: bool
    reason: str
    atomic_item_count: int
    supported_item_count: int
    missing_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class M156ReplacementDecision:
    action: str
    reason: str
    proposed_audit: M156FieldDecision
    baseline_audit: M156FieldDecision | None


M156_FIELD_STRATEGIES: Mapping[str, M156FieldStrategy] = {
    field_id: M156FieldStrategy(
        field_id=field_id,
        value_shape=(
            "atomic_legal_list"
            if field_id in M156_LONG_ATOMIC_FIELD_IDS
            else "payment_option_set"
            if field_id in {"premium_payment_term", "premium_payment_frequency"}
            else "waiting_rule"
            if field_id == "waiting_period"
            else "supported_right_set"
            if field_id == "policyholder_rights"
            else "detailed_business_field"
        ),
        require_item_evidence=(
            field_id in M156_LONG_ATOMIC_FIELD_IDS or field_id == "policyholder_rights"
        ),
    )
    for field_id in _M156_CONTEXT_FIELD_IDS
}


def build_m156_field_context(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    product_display_name: str | None = None,
    max_characters: int = 180_000,
) -> M156FieldContext:
    """Build one bounded context after every source page has been considered.

    The ordered scan guarantees coverage. Ranked, wider snippets are appended so
    dense responsibility and exclusion clauses are not represented only by a
    short per-page window.
    """

    requested = tuple(field_ids)
    if (
        not requested
        or len(requested) != len(set(requested))
        or any(field_id not in M156_FIELD_STRATEGIES for field_id in requested)
    ):
        raise ValueError("M156_FOCUS_FIELD_SET_INVALID")
    schema_ids = {field.field_id for field in schema.fields}
    if any(field_id not in schema_ids for field_id in requested):
        raise ValueError("M156_FOCUS_FIELD_SET_INVALID")
    if max_characters < 10_000:
        raise ValueError("M156_CONTEXT_LIMIT_INVALID")

    page_list = tuple(pages)
    located = locate_field_candidates(page_list, schema, requested)
    full_budget = min(max_characters, max(8_000, int(max_characters * 0.62)))
    ordered = build_full_material_field_source_text(
        page_list,
        schema,
        requested,
        max_characters=full_budget,
    )
    remaining = max_characters - len(ordered) - 2
    ranked = ""
    if remaining >= 2_000:
        ranked = select_candidate_source(
            page_list,
            schema,
            requested,
            max_pages=min(48, max(12, len(requested) * 8)),
            max_characters=remaining,
            max_pages_per_field=12,
            snippet_characters=3_200,
        ).text
    text = ordered if not ranked else f"{ordered}\n\n【重点条款完整窗口】\n{ranked}"
    text = text[:max_characters]

    included_locators = {
        f"pdf:{page.document_name}#page={page.page_number}"
        for page in page_list
        if f"【文档：{page.document_name}｜页码：{page.page_number}】" in text
        or f"[pdf:{page.document_name}#page={page.page_number}]" in text
    }
    coverage = {
        field_id: M156FieldCoverage(
            field_id=field_id,
            scanned_page_count=len(page_list),
            candidate_page_count=len(located.get(field_id, ())),
            included_page_count=len(included_locators),
            candidate_locators=tuple(
                item.locator for item in located.get(field_id, ())
            ),
            selected_locators=tuple(
                item.locator
                for item in located.get(field_id, ())[:12]
                if item.locator in included_locators
                or f"[{item.locator}]" in text
            ),
        )
        for field_id in requested
    }
    return M156FieldContext(text=text, coverage=coverage)


_LIST_PREFIX = re.compile(
    r"(?:^|\n)\s*(?:[-*•]|\d+[.、)]|[（(]?[一二三四五六七八九十]+[）)、.])\s*"
)
_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")
_SPACE = re.compile(r"\s+")


def _normalized(value: str) -> str:
    return _SPACE.sub("", value).replace("天", "日").strip("，,。；;：:")


def _items(value: CandidateValue | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ()
    matches = tuple(part.strip() for part in _LIST_PREFIX.split(text) if part.strip())
    if len(matches) > 1:
        return matches
    semicolon_items = tuple(part.strip() for part in re.split(r"[；;]", text) if part.strip())
    return semicolon_items if len(semicolon_items) > 1 else (text,)


def _evidence_supports(item: str, quote: str) -> bool:
    left = _normalized(item)
    right = _normalized(quote)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    tokens = tuple(
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", left)
        if token not in {"本公司", "被保险人", "保险合同", "保险期间"}
    )
    return bool(tokens) and sum(token in right for token in tokens) >= min(2, len(tokens))


def _audit_atomic(
    field_id: str,
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> M156FieldDecision:
    items = _items(value)
    supported = sum(
        any(_evidence_supports(item, quote) for quote in evidence_quotes) for item in items
    )
    if any(marker in str(value) for marker in ("等责任", "等情形", "详见", "包括但不限于")):
        return M156FieldDecision(
            accepted=False,
            reason="ATOMIC_VALUE_CONTAINS_SHORTCUT",
            atomic_item_count=len(items),
            supported_item_count=supported,
        )
    if len(evidence_quotes) < len(items) or supported < len(items):
        return M156FieldDecision(
            accepted=False,
            reason="ATOMIC_EVIDENCE_COUNT_MISMATCH",
            atomic_item_count=len(items),
            supported_item_count=supported,
            missing_components=tuple(
                item
                for item in items
                if not any(_evidence_supports(item, quote) for quote in evidence_quotes)
            ),
        )
    return M156FieldDecision(
        accepted=bool(items),
        reason="ATOMIC_ITEMS_SUPPORTED" if items else "EMPTY_VALUE",
        atomic_item_count=len(items),
        supported_item_count=supported,
    )


_TERM_VALUE = re.compile(r"(?:趸交|一次(?:性)?交清|\d+年(?:交|缴|期)?|\d+个月(?:交|缴|期)?)")
_FREQUENCY_VALUE = re.compile(r"(?:趸交|一次(?:性)?交清|年交|半年交|季交|月交)")
_FORMAL_PAYMENT_CUES = ("可选择", "可选", "交费期间为", "缴费期间为", "交费方式为", "缴费方式为")
_EXAMPLE_CUES = ("示例", "假设", "举例", "为例", "演示")


def _payment_values(text: str, field_id: str) -> tuple[str, ...]:
    pattern = _TERM_VALUE if field_id == "premium_payment_term" else _FREQUENCY_VALUE
    values: list[str] = []
    for raw in pattern.findall(text):
        value = raw.replace("缴", "交")
        if value == "一次性交清":
            value = "趸交"
        if field_id == "premium_payment_term":
            value = re.sub(r"(年|个月)(?:交|期)$", r"\1", value)
        if value not in values:
            values.append(value)
    return tuple(values)


def _formal_payment_values(text: str, field_id: str) -> tuple[str, ...]:
    values: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if not any(cue in sentence for cue in _FORMAL_PAYMENT_CUES):
            continue
        if any(cue in sentence for cue in _EXAMPLE_CUES):
            continue
        for value in _payment_values(sentence, field_id):
            if value not in values:
                values.append(value)
    return tuple(values)


def _audit_payment(
    field_id: str,
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
) -> M156FieldDecision:
    proposed = _payment_values("，".join(_items(value)), field_id)
    formal = _formal_payment_values(candidate_text, field_id)
    missing = tuple(item for item in formal if item not in proposed)
    example_only = bool(evidence_quotes) and all(
        any(cue in quote for cue in _EXAMPLE_CUES) for quote in evidence_quotes
    )
    if missing or example_only:
        return M156FieldDecision(
            accepted=False,
            reason="PAYMENT_EXAMPLE_OR_INCOMPLETE_SET",
            atomic_item_count=len(proposed),
            supported_item_count=len(tuple(item for item in proposed if item in formal)),
            missing_components=missing,
        )
    return M156FieldDecision(
        accepted=bool(proposed and evidence_quotes),
        reason="PAYMENT_OPTION_SET_SUPPORTED" if proposed and evidence_quotes else "EMPTY_VALUE",
        atomic_item_count=len(proposed),
        supported_item_count=len(proposed),
    )


def _audit_waiting(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
) -> M156FieldDecision:
    proposed = _normalized("，".join(_items(value)))
    material = _normalized(candidate_text)
    missing: list[str] = []
    exception_in_material = "意外" in material and any(
        marker in material for marker in ("无等待期", "不受等待期", "不适用等待期", "不受此限")
    )
    exception_in_value = "意外" in proposed and any(
        marker in proposed for marker in ("无等待期", "不受等待期", "不适用等待期", "不受此限")
    )
    if exception_in_material and not exception_in_value:
        missing.append("意外例外")
    consequence_markers = ("不承担保险责任", "退还保险费", "合同终止", "解除合同")
    if any(marker in material for marker in consequence_markers) and not any(
        marker in proposed for marker in consequence_markers
    ):
        missing.append("等待期内后果")
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="WAITING_PERIOD_COMPONENT_MISSING",
            atomic_item_count=1 if proposed else 0,
            supported_item_count=0,
            missing_components=tuple(missing),
        )
    supported = int(
        bool(
            proposed
            and any(_evidence_supports(proposed, quote) for quote in evidence_quotes)
        )
    )
    return M156FieldDecision(
        accepted=bool(supported),
        reason="WAITING_PERIOD_SUPPORTED" if supported else "WAITING_PERIOD_EVIDENCE_MISSING",
        atomic_item_count=1 if proposed else 0,
        supported_item_count=supported,
    )


_RIGHT_ALIASES: Mapping[str, tuple[str, ...]] = {
    "保单贷款": ("保单贷款", "申请贷款"),
    "自动垫交": ("自动垫交", "自动垫缴"),
    "减额交清": ("减额交清",),
    "减保": ("减保", "减少基本保险金额"),
    "退保": ("退保", "解除合同"),
    "现金价值": ("现金价值",),
    "红利": ("红利", "分红"),
}


def _positive_right_support(item: str, quote: str) -> bool:
    aliases = next(
        (aliases for key, aliases in _RIGHT_ALIASES.items() if key in item),
        (item,),
    )
    if not any(alias in quote for alias in aliases):
        return False
    for negative in ("不支持", "不提供", "不得", "不能", "无", "未约定", "不享有"):
        if any(negative + alias in _normalized(quote) for alias in aliases):
            return False
    return True


def _audit_policy_rights(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> M156FieldDecision:
    items = _items(value)
    missing = tuple(
        item
        for item in items
        if not any(_positive_right_support(item, quote) for quote in evidence_quotes)
    )
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="POLICY_RIGHT_UNSUPPORTED",
            atomic_item_count=len(items),
            supported_item_count=len(items) - len(missing),
            missing_components=missing,
        )
    return M156FieldDecision(
        accepted=bool(items),
        reason="POLICY_RIGHTS_SUPPORTED" if items else "EMPTY_VALUE",
        atomic_item_count=len(items),
        supported_item_count=len(items),
    )


def audit_m156_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
) -> M156FieldDecision:
    if field_id not in M156_FIELD_STRATEGIES:
        raise ValueError("M156_FOCUS_FIELD_INVALID")
    if field_id in M156_LONG_ATOMIC_FIELD_IDS:
        return _audit_atomic(field_id, proposed_value, evidence_quotes)
    if field_id in {"premium_payment_term", "premium_payment_frequency"}:
        return _audit_payment(field_id, proposed_value, evidence_quotes, candidate_text)
    if field_id == "waiting_period":
        return _audit_waiting(proposed_value, evidence_quotes, candidate_text)
    return _audit_policy_rights(proposed_value, evidence_quotes)


def choose_m156_replacement(
    *,
    field_id: str,
    baseline_state: TriState,
    baseline_value: CandidateValue | None,
    baseline_evidence_quotes: Sequence[str],
    proposed_state: TriState,
    proposed_value: CandidateValue | None,
    proposed_evidence_quotes: Sequence[str],
    candidate_text: str,
    product_display_name: str | None = None,
) -> M156ReplacementDecision:
    proposed_audit = audit_m156_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=proposed_evidence_quotes,
        candidate_text=candidate_text,
    )
    baseline_audit = (
        audit_m156_candidate(
            field_id=field_id,
            proposed_value=baseline_value,
            evidence_quotes=baseline_evidence_quotes,
            candidate_text=candidate_text,
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


__all__ = [
    "M156_FIELD_STRATEGIES",
    "M156_FOCUS_FIELD_IDS",
    "M156_LONG_ATOMIC_FIELD_IDS",
    "M156FieldContext",
    "M156FieldCoverage",
    "M156FieldDecision",
    "M156ReplacementDecision",
    "M156FieldStrategy",
    "audit_m156_candidate",
    "build_m156_field_context",
    "choose_m156_replacement",
]
