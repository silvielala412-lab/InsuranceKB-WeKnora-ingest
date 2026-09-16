from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .contracts import (
    CandidateEvidence,
    CandidateValue,
    InsuranceSchema,
    PluginFieldResult,
    TriState,
)
from .dynamic_ingest import CandidateSourcePage, locate_field_candidates
from .m156_quality import (
    M156FieldDecision,
    M156ReplacementDecision,
    _items,
    _normalized,
)
from .m157_quality import audit_m157_candidate

M158_MAX_CALLS = 32
M158_LONG_FIELD_IDS = frozenset(
    {
        "coverage_responsibilities",
        "exclusions",
        "disease_definitions_and_criteria",
    }
)
M158_FEEDBACK_FIELD_IDS = frozenset(
    {
        *M158_LONG_FIELD_IDS,
        "premium_payment_term",
        "premium_payment_frequency",
        "policyholder_rights",
        "waiting_period",
    }
)

FeedbackStatus = Literal["RESOLVED", "PARTIAL", "UNRESOLVED", "NOT_SCORABLE"]


@dataclass(frozen=True, slots=True)
class LongFieldShard:
    field_id: str
    shard_index: int
    shard_count: int
    text: str
    scanned_page_count: int
    candidate_locators: tuple[str, ...]
    selected_locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaymentPairAudit:
    term: M156FieldDecision
    frequency: M156FieldDecision


@dataclass(frozen=True, slots=True)
class FeedbackIssue:
    issue_id: int
    product_id: str
    field_id: str
    field_name: str
    problem_label: str
    business_note: str
    workbook_row: int


@dataclass(frozen=True, slots=True)
class FeedbackAssessment:
    issue_id: int
    product_id: str
    field_id: str
    field_name: str
    problem_label: str
    business_note: str
    workbook_row: int
    status: FeedbackStatus
    reason: str
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()


_LIST_NUMBER = re.compile(r"^\s*(?:\d+[.、)]|[（(]?[一二三四五六七八九十]+[）)、.])\s*")
_PAYMENT_TERM = re.compile(
    r"(?:趸[交缴]|一次(?:性)?[交缴](?:清)?|\d+年(?:[交缴]|期)?|\d+个月(?:[交缴]|期)?)"
)
_PAYMENT_FREQUENCY = re.compile(
    r"(?:趸[交缴]|一次(?:性)?[交缴](?:清)?|年[交缴]|半年[交缴]|季[交缴]|月[交缴])"
)
_PAYMENT_FIELD_CUES: Mapping[str, tuple[str, ...]] = {
    "premium_payment_term": ("交费期间", "缴费期间", "交费期限", "缴费期限"),
    "premium_payment_frequency": ("交费方式", "缴费方式"),
}
_PAYMENT_EXAMPLE_CUES = ("示例", "假设", "举例", "为例", "演示")
_VERIFIED_STATUSES = frozenset({"VERIFIED", "NORMALIZED_MATCH"})


def _long_field_semantic_page(field_id: str, text: str) -> bool:
    """Keep continuation pages whose content carries the field, not just its title."""

    compact = _normalized(text)
    if field_id == "coverage_responsibilities":
        return (
            any(marker in compact for marker in ("保险责任", "保障责任", "主要保单利益"))
            or (
                "保险金" in compact
                and any(marker in compact for marker in ("给付", "承担", "赔偿", "按以下"))
            )
        )
    if field_id == "exclusions":
        return any(
            marker in compact
            for marker in ("责任免除", "除外责任", "不承担", "不负给付", "不予给付")
        )
    return any(
        marker in compact
        for marker in (
            "疾病定义",
            "疾病释义",
            "重大疾病释义",
            "轻症疾病释义",
            "中症疾病释义",
            "本合同所定义",
            "指被保险人",
            "是指被保险人",
            "须经医院专科医生明确诊断",
        )
    )


def _page_locator(page: CandidateSourcePage) -> str:
    return f"pdf:{page.document_name}#page={page.page_number}"


def _scope(product_display_name: str) -> str:
    return "附加险" if "附加" in product_display_name else "当前独立产品或主险"


def _split_text(value: str, limit: int, *, overlap: int = 180) -> tuple[str, ...]:
    if len(value) <= limit:
        return (value,)
    parts: list[str] = []
    start = 0
    while start < len(value):
        end = min(len(value), start + limit)
        if end < len(value):
            boundary = max(
                value.rfind("\n", start + limit // 2, end),
                value.rfind("。", start + limit // 2, end),
                value.rfind("；", start + limit // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        parts.append(value[start:end])
        if end >= len(value):
            break
        start = max(start + 1, end - overlap)
    return tuple(parts)


def build_long_field_shards(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_id: str,
    *,
    product_display_name: str,
    max_characters: int = 58_000,
    neighbor_pages: int = 2,
) -> tuple[LongFieldShard, ...]:
    """Scan all pages, then create bounded high-recall field windows."""

    if field_id not in M158_LONG_FIELD_IDS:
        raise ValueError("M158_LONG_FIELD_INVALID")
    if not product_display_name.strip():
        raise ValueError("M158_PRODUCT_NAME_REQUIRED")
    if max_characters < 900:
        raise ValueError("M158_SHARD_LIMIT_INVALID")
    page_list = tuple(pages)
    located = locate_field_candidates(page_list, schema, (field_id,)).get(field_id, ())
    semantic_keys = {
        (page.document_name, page.page_number)
        for page in page_list
        if _long_field_semantic_page(field_id, page.text)
    }
    candidate_keys = {
        *((item.document_name, item.page_number) for item in located),
        *semantic_keys,
    }
    selected_keys = set(candidate_keys)
    source_index = {
        (page.document_name, page.page_number): index for index, page in enumerate(page_list)
    }
    for key in tuple(candidate_keys):
        index = source_index.get(key)
        if index is None:
            continue
        for offset in range(-neighbor_pages, neighbor_pages + 1):
            neighbor_index = index + offset
            if not 0 <= neighbor_index < len(page_list):
                continue
            neighbor = page_list[neighbor_index]
            if neighbor.document_name == key[0]:
                selected_keys.add((neighbor.document_name, neighbor.page_number))
    selected_pages = tuple(
        page for page in page_list if (page.document_name, page.page_number) in selected_keys
    )
    if not selected_pages:
        selected_pages = page_list

    base_header = (
        f"【当前产品：{product_display_name}】\n"
        f"【当前产品作用域：{_scope(product_display_name)}】\n"
        f"【目标字段：{field_id}】\n"
        "只抽取本分片原文明确支持的原子事实；不得用‘等’或‘详见条款’代替清单。"
        "Evidence 必须引用同一页内可以回验的短原文，不得跨页拼成一条引文。\n"
    )
    payload_limit = max(400, max_characters - len(base_header) - 90)
    blocks: list[tuple[str, str]] = []
    for page in selected_pages:
        locator = _page_locator(page)
        prefix = f"【文档：{page.document_name}｜页码：{page.page_number}】\n"
        part_limit = max(200, payload_limit - len(prefix))
        for part in _split_text(page.text, part_limit):
            blocks.append((locator, prefix + part.strip()))

    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_length = 0
    for block in blocks:
        block_length = len(block[1]) + (2 if current else 0)
        if current and current_length + block_length > payload_limit:
            groups.append(current)
            current = []
            current_length = 0
        current.append(block)
        current_length += block_length
    if current:
        groups.append(current)
    if not groups:
        groups = [[]]

    candidate_locators = tuple(
        _page_locator(page)
        for page in page_list
        if (page.document_name, page.page_number) in candidate_keys
    )
    shard_count = len(groups)
    shards: list[LongFieldShard] = []
    for index, group in enumerate(groups, 1):
        shard_header = base_header + f"【分片：{index}/{shard_count}】\n"
        body = "\n\n".join(block for _, block in group)
        text = (shard_header + body)[:max_characters]
        shards.append(
            LongFieldShard(
                field_id=field_id,
                shard_index=index,
                shard_count=shard_count,
                text=text,
                scanned_page_count=len(page_list),
                candidate_locators=candidate_locators,
                selected_locators=tuple(dict.fromkeys(locator for locator, _ in group)),
            )
        )
    return tuple(shards)


def _atomic_identity(item: str) -> str:
    item = _LIST_NUMBER.sub("", item).strip()
    heading = re.split(r"[：:]", item, maxsplit=1)[0].strip()
    basis = heading if 1 < len(heading) <= 40 else item
    return _normalized(basis)


def _dedupe_evidence(
    evidence: Sequence[CandidateEvidence],
) -> tuple[CandidateEvidence, ...]:
    unique: dict[tuple[str, str], CandidateEvidence] = {}
    for item in evidence:
        unique.setdefault((item.locator, _normalized(item.quote)), item)
    return tuple(unique.values())


def merge_atomic_shard_results(
    field_id: str,
    results: Sequence[PluginFieldResult],
) -> PluginFieldResult:
    """Merge overlapping shard answers by stable atomic heading and source order."""

    if field_id not in M158_LONG_FIELD_IDS:
        raise ValueError("M158_LONG_FIELD_INVALID")
    if not results or any(result.field_id != field_id for result in results):
        raise ValueError("M158_SHARD_RESULT_SET_INVALID")
    present = tuple(result for result in results if result.state == "present")
    if not present:
        return PluginFieldResult(
            ordinal=results[0].ordinal,
            field_id=field_id,
            state="unknown",
            value=None,
            evidence=(),
        )

    by_identity: dict[str, str] = {}
    order: list[str] = []
    for result in present:
        for raw_item in _items(result.value):
            item = _LIST_NUMBER.sub("", raw_item).strip()
            if not item:
                continue
            identity = _atomic_identity(item)
            if identity not in by_identity:
                order.append(identity)
                by_identity[identity] = item
            elif len(_normalized(item)) > len(_normalized(by_identity[identity])):
                by_identity[identity] = item
    if not order:
        return PluginFieldResult(
            ordinal=results[0].ordinal,
            field_id=field_id,
            state="unknown",
            value=None,
            evidence=(),
        )
    value = "\n".join(
        f"{index}. {by_identity[identity]}" for index, identity in enumerate(order, 1)
    )
    return PluginFieldResult(
        ordinal=results[0].ordinal,
        field_id=field_id,
        state="present",
        value=value,
        evidence=_dedupe_evidence(
            tuple(item for result in present for item in result.evidence)
        ),
    )


def admit_verified_evidence_subset(
    result: PluginFieldResult,
    *,
    candidate_text: str,
    product_display_name: str,
) -> tuple[PluginFieldResult | None, M156FieldDecision]:
    """Drop redundant unresolved citations, then re-audit all atomic claims."""

    verified = tuple(
        item for item in result.evidence if item.verification_status in _VERIFIED_STATUSES
    )
    decision = audit_m158_candidate(
        field_id=result.field_id,
        proposed_value=result.value,
        evidence_quotes=tuple(item.quote for item in verified),
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )
    if result.state != "present" or not verified or not decision.accepted:
        return None, decision
    return result.model_copy(update={"evidence": verified}), decision


def _canonical_payment(raw: str, field_id: str) -> str:
    value = raw.replace("缴", "交")
    if value.startswith("一次") or value == "趸交":
        return "趸交"
    if field_id == "premium_payment_term":
        value = re.sub(r"(年|个月)(?:交|期)$", r"\1", value)
    return value


def _payment_values(value: CandidateValue | str | None, field_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    text = "，".join(_items(value)) if not isinstance(value, str) else value
    pattern = _PAYMENT_TERM if field_id == "premium_payment_term" else _PAYMENT_FREQUENCY
    return tuple(
        dict.fromkeys(_canonical_payment(item, field_id) for item in pattern.findall(text))
    )


def _formal_payment_values(text: str, field_id: str) -> tuple[str, ...]:
    values: list[str] = []
    for segment in re.split(r"[。；;\n]+", text):
        if not any(cue in segment for cue in _PAYMENT_FIELD_CUES[field_id]):
            continue
        if any(cue in segment for cue in _PAYMENT_EXAMPLE_CUES):
            continue
        for value in _payment_values(segment, field_id):
            if value not in values:
                values.append(value)
    return tuple(values)


def _audit_one_payment(
    *,
    field_id: str,
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
) -> M156FieldDecision:
    proposed = _payment_values(value, field_id)
    formal = _formal_payment_values(candidate_text, field_id)
    missing = tuple(item for item in formal if item not in proposed)
    supported = tuple(
        item
        for item in proposed
        if any(item in _payment_values(quote, field_id) for quote in evidence_quotes)
    )
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="PAYMENT_OPTION_SET_INCOMPLETE",
            atomic_item_count=len(proposed),
            supported_item_count=len(supported),
            missing_components=missing,
        )
    if not proposed or len(supported) != len(proposed):
        unsupported = tuple(item for item in proposed if item not in supported)
        return M156FieldDecision(
            accepted=False,
            reason="PAYMENT_OPTION_EVIDENCE_MISSING" if proposed else "EMPTY_VALUE",
            atomic_item_count=len(proposed),
            supported_item_count=len(supported),
            missing_components=unsupported,
        )
    return M156FieldDecision(
        accepted=True,
        reason="PAYMENT_OPTION_SET_SUPPORTED",
        atomic_item_count=len(proposed),
        supported_item_count=len(supported),
    )


def audit_payment_pair(
    *,
    term_value: CandidateValue | None,
    term_evidence: Sequence[str],
    frequency_value: CandidateValue | None,
    frequency_evidence: Sequence[str],
    candidate_text: str,
) -> PaymentPairAudit:
    return PaymentPairAudit(
        term=_audit_one_payment(
            field_id="premium_payment_term",
            value=term_value,
            evidence_quotes=term_evidence,
            candidate_text=candidate_text,
        ),
        frequency=_audit_one_payment(
            field_id="premium_payment_frequency",
            value=frequency_value,
            evidence_quotes=frequency_evidence,
            candidate_text=candidate_text,
        ),
    )


def audit_m158_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
    product_display_name: str,
) -> M156FieldDecision:
    if field_id in {"premium_payment_term", "premium_payment_frequency"}:
        return _audit_one_payment(
            field_id=field_id,
            value=proposed_value,
            evidence_quotes=evidence_quotes,
            candidate_text=candidate_text,
        )
    return audit_m157_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=evidence_quotes,
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )


def choose_m158_replacement(
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
    proposed = audit_m158_candidate(
        field_id=field_id,
        proposed_value=proposed_value,
        evidence_quotes=proposed_evidence_quotes,
        candidate_text=candidate_text,
        product_display_name=product_display_name,
    )
    baseline = (
        audit_m158_candidate(
            field_id=field_id,
            proposed_value=baseline_value,
            evidence_quotes=baseline_evidence_quotes,
            candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
        if baseline_state == "present"
        else None
    )
    if proposed_state != "present" or not proposed.accepted:
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="PROPOSAL_NOT_PRESENT" if proposed_state != "present" else proposed.reason,
            proposed_audit=proposed,
            baseline_audit=baseline,
        )
    if baseline_state == "unknown":
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_GAP_FILL",
            proposed_audit=proposed,
            baseline_audit=None,
        )
    if baseline_state == "absent_explicitly":
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="EXPLICIT_ABSENCE_CONFLICT_REQUIRES_REVIEW",
            proposed_audit=proposed,
            baseline_audit=None,
        )
    if baseline is not None and not baseline.accepted:
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_PROPOSAL_REPAIRS_INCOMPLETE_BASELINE",
            proposed_audit=proposed,
            baseline_audit=baseline,
        )
    if _normalized(str(baseline_value)) == _normalized(str(proposed_value)):
        return M156ReplacementDecision(
            action="keep_baseline",
            reason="SAME_NORMALIZED_VALUE",
            proposed_audit=proposed,
            baseline_audit=baseline,
        )
    if (
        baseline is not None
        and proposed.atomic_item_count > baseline.atomic_item_count
        and proposed.supported_item_count >= baseline.supported_item_count
    ):
        return M156ReplacementDecision(
            action="replace",
            reason="SUPPORTED_PROPOSAL_ADDS_ATOMIC_ITEMS",
            proposed_audit=proposed,
            baseline_audit=baseline,
        )
    return M156ReplacementDecision(
        action="keep_baseline",
        reason="COMPLETE_BASELINE_CONFLICT_REQUIRES_REVIEW",
        proposed_audit=proposed,
        baseline_audit=baseline,
    )


_TERM_ALIASES: Mapping[str, tuple[str, ...]] = {
    "趸缴": ("趸缴", "趸交", "一次性交清", "一次缴清"),
    "趸交": ("趸缴", "趸交", "一次性交清", "一次缴清"),
    "年缴": ("年缴", "年交"),
    "意外情形": ("意外",),
    "保单红利责任": ("保单红利", "红利"),
}


def _contains_term(value: str, term: str) -> bool:
    aliases = _TERM_ALIASES.get(term, (term,))
    return any(alias in value for alias in aliases)


def _feedback_expectations(note: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not note.strip() or "截图" in note or "回看源文件" in note:
        return (), ()
    required: list[str] = []
    forbidden: list[str] = []
    for pattern in (r"无([\u4e00-\u9fffA-Za-z0-9]+)", r"不应包含([\u4e00-\u9fffA-Za-z0-9]+)"):
        forbidden.extend(re.findall(pattern, note))
    for pattern in (r"缺少([^；，。]+)", r"缺失([^；，。]+)"):
        required.extend(re.findall(pattern, note))
    match = re.search(r"至少(?:应有|缺少)([^；。]+)", note)
    if match:
        required.extend(re.split(r"[、，,及和]", match.group(1)))
    answer = re.search(r"应为([^；。]+)", note)
    if answer:
        raw = answer.group(1)
        years = re.findall(r"\d+", raw)
        required.extend(f"{year}年" for year in years)
    if (
        not required
        and not forbidden
        and len(note.strip()) <= 16
        and not any(marker in note for marker in ("应", "不", "最好", "概括"))
    ):
        required.append(note.strip())
    cleaned_required = tuple(
        dict.fromkeys(item.strip(" \"'“”") for item in required if item.strip())
    )
    cleaned_forbidden = tuple(
        dict.fromkeys(item.strip(" \"'“”") for item in forbidden if item.strip())
    )
    return cleaned_required, cleaned_forbidden


def assess_feedback_issues(
    issues: Sequence[FeedbackIssue],
    fields: Mapping[tuple[str, str], PluginFieldResult],
) -> tuple[FeedbackAssessment, ...]:
    assessments: list[FeedbackAssessment] = []
    for issue in issues:
        required, forbidden = _feedback_expectations(issue.business_note)
        field = fields.get((issue.product_id, issue.field_id))
        value = "" if field is None or field.value is None else str(field.value)
        if not required and not forbidden:
            status: FeedbackStatus = "NOT_SCORABLE"
            reason = "BUSINESS_ANSWER_NOT_MACHINE_READABLE"
        elif field is None or field.state != "present":
            status = "UNRESOLVED"
            reason = "FIELD_NOT_PRESENT"
        else:
            required_hits = sum(_contains_term(value, term) for term in required)
            forbidden_hits = sum(_contains_term(value, term) for term in forbidden)
            checks = len(required) + len(forbidden)
            passes = required_hits + len(forbidden) - forbidden_hits
            if passes == checks:
                status = "RESOLVED"
                reason = "ALL_MACHINE_READABLE_EXPECTATIONS_MET"
            elif passes:
                status = "PARTIAL"
                reason = "SOME_MACHINE_READABLE_EXPECTATIONS_MET"
            else:
                status = "UNRESOLVED"
                reason = "MACHINE_READABLE_EXPECTATIONS_NOT_MET"
        assessments.append(
            FeedbackAssessment(
                issue_id=issue.issue_id,
                product_id=issue.product_id,
                field_id=issue.field_id,
                field_name=issue.field_name,
                problem_label=issue.problem_label,
                business_note=issue.business_note,
                workbook_row=issue.workbook_row,
                status=status,
                reason=reason,
                required_terms=required,
                forbidden_terms=forbidden,
            )
        )
    return tuple(assessments)


__all__ = [
    "FeedbackAssessment",
    "FeedbackIssue",
    "FeedbackStatus",
    "LongFieldShard",
    "M158_FEEDBACK_FIELD_IDS",
    "M158_LONG_FIELD_IDS",
    "M158_MAX_CALLS",
    "PaymentPairAudit",
    "admit_verified_evidence_subset",
    "assess_feedback_issues",
    "audit_m158_candidate",
    "audit_payment_pair",
    "build_long_field_shards",
    "merge_atomic_shard_results",
    "choose_m158_replacement",
]
