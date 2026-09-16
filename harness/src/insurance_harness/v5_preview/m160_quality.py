from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from .business_field_quality import (
    audit_business_priority_candidate,
    expand_service_table_values,
    normalize_business_field_value,
    supported_special_coverage_tags,
)
from .contracts import CandidateValue, PluginFieldResult, TriState
from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS
from .m156_quality import (
    M156FieldDecision,
    M156ReplacementDecision,
    _evidence_supports,
    _items,
    _normalized,
)
from .m158_quality import (
    audit_m158_candidate,
    choose_m158_replacement,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；;])\s*|\n+")
_DURATION = re.compile(r"(?<!\d)(\d+)\s*(日|天|个月|月|年)")
_LABELS = {
    "duration": ("时长", "等待期时长", "等待期"),
    "start": ("起算点", "起算", "开始"),
    "applicability": ("适用责任", "适用范围", "适用情形"),
    "accident_exception": ("意外例外", "意外伤害例外", "意外"),
    "within_wait_consequence": ("等待期内后果", "等待期内处理", "后果"),
    "special_exceptions": ("特殊例外", "特殊无等待期", "其他例外"),
}


@dataclass(frozen=True, slots=True)
class WaitingPeriodComponents:
    duration: str | None = None
    start: str | None = None
    applicability: str | None = None
    accident_exception: str | None = None
    within_wait_consequence: str | None = None
    special_exceptions: str | None = None

    def as_value(self) -> str:
        labels = (
            ("等待期时长", self.duration),
            ("起算点", self.start),
            ("适用责任", self.applicability),
            ("意外例外", self.accident_exception),
            ("等待期内后果", self.within_wait_consequence),
            ("特殊例外", self.special_exceptions),
        )
        return "\n".join(f"{label}：{value}" for label, value in labels if value)

    def missing(self, *, candidate_text: str = "") -> tuple[str, ...]:
        required = [
            name
            for name in ("duration", "start", "applicability", "within_wait_consequence")
            if not getattr(self, name)
        ]
        # An accident clause is required when the source actually states one;
        # absence of the clause is not a license to invent a negative fact.
        if "意外" in candidate_text and not self.accident_exception:
            required.append("accident_exception")
        return tuple(required)


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(part.strip(" \t\r\n") for part in _SENTENCE_SPLIT.split(text) if part.strip())


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[：:]\s*(.+?)(?=\n|$)", text)
        if match and match.group(1).strip():
            return match.group(1).strip(" ;；。")
    return None


def _first_sentence(sentences: tuple[str, ...], predicates: tuple[str, ...]) -> str | None:
    for sentence in sentences:
        if all(predicate in sentence for predicate in predicates):
            return sentence
    return None


def parse_waiting_period_components(value: CandidateValue | str | None) -> WaitingPeriodComponents:
    """Parse labelled model output or source-like prose into reviewable facts."""

    text = (
        ""
        if value is None
        else "\n".join(_items(value))
        if not isinstance(value, str)
        else value
    )
    sentences = _sentences(text)
    duration = _label_value(text, _LABELS["duration"])
    if duration is None:
        match = _DURATION.search(text)
        duration = f"{match.group(1)}{match.group(2)}" if match else None

    start = _label_value(text, _LABELS["start"])
    if start is None:
        start = _first_sentence(sentences, ("生效", "起"))

    applicability = _label_value(text, _LABELS["applicability"])
    if applicability is None:
        for sentence in sentences:
            if any(
                marker in sentence
                for marker in ("确诊", "疾病", "轻度", "中症", "重大疾病", "保险责任")
            ):
                if "等待期" in sentence or "生效" in sentence or "适用" in sentence:
                    applicability = sentence
                    break

    accident = _label_value(text, _LABELS["accident_exception"])
    if accident is None:
        accident = next(
            (
                sentence
                for sentence in sentences
                if "意外" in sentence
                and any(
                    marker in sentence
                    for marker in ("无等待期", "不受", "不适用", "例外")
                )
            ),
            None,
        )

    consequence = _label_value(text, _LABELS["within_wait_consequence"])
    if consequence is None:
        consequence = next(
            (
                sentence
                for sentence in sentences
                if ("等待期内" in sentence or "等待期" in sentence)
                and any(
                    marker in sentence
                    for marker in (
                        "返还",
                        "退还",
                        "退费",
                        "终止",
                        "不承担",
                        "不予给付",
                        "不负责",
                    )
                )
            ),
            None,
        )

    special = _label_value(text, _LABELS["special_exceptions"])
    if special is None:
        special_sentences = tuple(
            sentence
            for sentence in sentences
            if any(marker in sentence for marker in ("续保", "重新投保", "恢复", "再次投保"))
            and any(marker in sentence for marker in ("无等待期", "免等待期", "重新计算"))
        )
        special = "；".join(special_sentences) if special_sentences else None

    return WaitingPeriodComponents(
        duration=duration,
        start=start,
        applicability=applicability,
        accident_exception=accident,
        within_wait_consequence=consequence,
        special_exceptions=special,
    )


def audit_waiting_period_components(
    components: WaitingPeriodComponents,
    candidate_text: str = "",
) -> M156FieldDecision:
    missing = components.missing(candidate_text=candidate_text)
    populated = tuple(
        name
        for name in (
            "duration",
            "start",
            "applicability",
            "accident_exception",
            "within_wait_consequence",
            "special_exceptions",
        )
        if getattr(components, name)
    )
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="WAITING_PERIOD_COMPONENTS_INCOMPLETE",
            atomic_item_count=len(populated),
            supported_item_count=0,
            missing_components=missing,
        )
    return M156FieldDecision(
        accepted=bool(populated),
        reason="WAITING_PERIOD_COMPONENTS_COMPLETE" if populated else "EMPTY_VALUE",
        atomic_item_count=len(populated),
        supported_item_count=len(populated),
    )


def audit_m160_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: tuple[str, ...] | list[str],
    candidate_text: str,
    product_display_name: str,
) -> M156FieldDecision:
    if field_id in BUSINESS_PRIORITY_FIELD_IDS and field_id != "waiting_period":
        return audit_business_priority_candidate(
            field_id=field_id,
            proposed_value=proposed_value,
            evidence_quotes=evidence_quotes,
            candidate_text=candidate_text,
        )
    if field_id != "waiting_period":
        return audit_m158_candidate(
            field_id=field_id,
            proposed_value=proposed_value,
            evidence_quotes=evidence_quotes,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
    components = parse_waiting_period_components(proposed_value)
    decision = audit_waiting_period_components(components, candidate_text)
    if not decision.accepted:
        return decision
    # Every populated component must be represented by at least one verified
    # quote. This is intentionally conservative: a compact summary without
    # component-level support remains a review item.
    unsupported = tuple(
        name
        for name in (
            "duration",
            "start",
            "applicability",
            "accident_exception",
            "within_wait_consequence",
            "special_exceptions",
        )
        if getattr(components, name)
        and not any(
            _evidence_supports(str(getattr(components, name)), quote)
            for quote in evidence_quotes
        )
    )
    if unsupported:
        return M156FieldDecision(
            accepted=False,
            reason="WAITING_PERIOD_COMPONENT_EVIDENCE_MISSING",
            atomic_item_count=decision.atomic_item_count,
            supported_item_count=decision.atomic_item_count - len(unsupported),
            missing_components=unsupported,
        )
    return decision


def admit_m160_evidence_subset(
    result: PluginFieldResult,
    *,
    candidate_text: str,
    product_display_name: str,
) -> tuple[PluginFieldResult | None, M156FieldDecision]:
    verified = tuple(
        item
        for item in result.evidence
        if item.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
    )
    if result.state == "present" and verified:
        if result.field_id == "special_coverage_and_exclusion_tags":
            supported_tags = supported_special_coverage_tags(
                result.value,
                tuple(item.quote for item in verified),
            )
            if supported_tags:
                result = result.model_copy(update={"value": supported_tags})
        elif result.field_id == "medical_service_benefits":
            result = result.model_copy(
                update={
                    "value": expand_service_table_values(
                        result.value,
                        tuple(item.quote for item in verified),
                    )
                }
            )
    decision = audit_m160_candidate(
        field_id=result.field_id,
        proposed_value=result.value,
        evidence_quotes=tuple(item.quote for item in verified),
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )
    if result.state != "present" or not verified or not decision.accepted:
        return None, decision
    return result.model_copy(update={"evidence": verified}), decision


def choose_m160_replacement(
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
    """M158 replacement policy with the stricter waiting-period audit."""

    proposed = audit_m160_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=tuple(proposed_evidence_quotes),
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )
    if field_id not in BUSINESS_PRIORITY_FIELD_IDS:
        return choose_m158_replacement(
            field_id=field_id,
            baseline_state=baseline_state,
            baseline_value=baseline_value,
            baseline_evidence_quotes=baseline_evidence_quotes,
            proposed_state=proposed_state,
            proposed_value=proposed_value,
            proposed_evidence_quotes=proposed_evidence_quotes,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
    baseline = None
    if baseline_state == "present":
        baseline = audit_m160_candidate(
            field_id=field_id,
            proposed_value=baseline_value,
            evidence_quotes=tuple(baseline_evidence_quotes),
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )

    if proposed_state != "present" or not proposed.accepted:
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="PROPOSAL_NOT_PRESENT" if proposed_state != "present" else proposed.reason,
            proposed_audit=proposed,
            baseline_audit=baseline,
        )
    if baseline_state == "unknown":
        return M156ReplacementDecision("replace", "SUPPORTED_GAP_FILL", proposed, None)
    if baseline is not None and not baseline.accepted:
        return M156ReplacementDecision(
            "replace", "SUPPORTED_PROPOSAL_REPAIRS_INCOMPLETE_BASELINE", proposed, baseline
        )
    if field_id == "special_coverage_and_exclusion_tags":
        baseline_canonical = normalize_business_field_value(
            field_id,
            cast(CandidateValue, baseline_value),
            tuple(baseline_evidence_quotes),
        )
        proposed_canonical = normalize_business_field_value(
            field_id,
            cast(CandidateValue, proposed_value),
            tuple(proposed_evidence_quotes),
        )
        if (
            _normalized(str(baseline_canonical))
            == _normalized(str(proposed_canonical))
            == _normalized(str(proposed_value))
            and _normalized(str(baseline_value)) != _normalized(str(proposed_value))
        ):
            return M156ReplacementDecision(
                "replace",
                "SUPPORTED_EQUIVALENT_TAG_CANONICALIZATION",
                proposed,
                baseline,
            )
    if _normalized(str(baseline_value)) == _normalized(str(proposed_value)):
        return M156ReplacementDecision(
            "keep_baseline", "SAME_NORMALIZED_VALUE", proposed, baseline
        )
    if (
        baseline is not None
        and proposed.supported_item_count >= baseline.supported_item_count
        and proposed.atomic_item_count > baseline.atomic_item_count
    ):
        return M156ReplacementDecision(
            "replace",
            (
                "SUPPORTED_PROPOSAL_ADDS_WAITING_COMPONENTS"
                if field_id == "waiting_period"
                else "SUPPORTED_PROPOSAL_ADDS_BUSINESS_COMPONENTS"
            ),
            proposed,
            baseline,
        )
    return M156ReplacementDecision(
        "keep_baseline", "COMPLETE_BASELINE_CONFLICT_REQUIRES_REVIEW", proposed, baseline
    )


def m160_repair_hint(kind: str) -> str:
    if kind == "long_field_shard":
        return (
            "Mission 160 long-field shard. Exhaustively extract every material-supported "
            "atomic item for this product and field. Preserve conditions, limits, exceptions "
            "and applicability; number every item and attach a short same-page verbatim "
            "Evidence. Never use 等、详见、"
            "包括但不限于 or a directory reference, and never merge another contract."
        )
    return (
        "Priority-field pass. Return complete material-supported facts, not a short summary. "
        "Merge facts across product terms, brochures, service manuals and other supplied files; "
        "a brochure summary never replaces more detailed policy wording. For special coverage "
        "tags preserve the exact positive/negative direction and name the subject. For external "
        "drug, reimbursable scope, claim documents and value-added services keep every stated "
        "component, item, condition, limit and applicable responsibility. "
        "For waiting_period value use exactly these labelled lines when supported: "
        "等待期时长、起算点、适用责任、意外例外、等待期内后果、特殊例外. The duration alone "
        "is incomplete. Keep every formal payment term/frequency option and separate the two "
        "fields; exclude illustration examples. For rights, responsibilities and exclusions "
        "keep current-product scope and atomic conditions. Every populated waiting component "
        "and every atomic item needs direct same-page Evidence; never infer."
    )


__all__ = [
    "WaitingPeriodComponents",
    "admit_m160_evidence_subset",
    "audit_m160_candidate",
    "audit_waiting_period_components",
    "choose_m160_replacement",
    "m160_repair_hint",
    "parse_waiting_period_components",
]
