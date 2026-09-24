from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .contracts import CandidateValue
from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS, field_extraction_profile
from .m156_quality import (
    M156FieldDecision,
    _evidence_supports,
    _has_unsupported_shortcut,
    _items,
    _normalized,
    audit_m156_candidate,
)
from .source_evidence import strip_defined_footnote_references

_SHORTCUT_MARKERS = ("等责任", "等情形", "等费用", "等服务", "详见", "包括但不限于")
_POSITIVE_TAG_MARKERS = ("可赔", "承保", "可保", "保障")
_NEGATIVE_TAG_MARKERS = ("不可赔", "不赔", "不保", "除外", "不承担", "不予给付")
_TAG_DIRECTION_MARKERS = (*_POSITIVE_TAG_MARKERS, *_NEGATIVE_TAG_MARKERS)

_COMPONENTS: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "out_of_hospital_special_drug_coverage": (
        ("药品或疾病范围", ("药品清单", "特定药品", "院外药品", "适用药品")),
        ("处方要求", ("处方", "处方医师")),
        ("购药渠道", ("指定药店", "指定机构", "购药渠道", "药店购买")),
        ("事前申请或审核", ("事前申请", "购药申请", "审核", "用药合理性")),
        ("责任额度", ("限额", "保险金额", "最高给付")),
        ("赔付比例", ("给付比例", "赔付比例", "按百分之", "%")),
    ),
    "reimbursable_expense_scope": (
        ("床位费", ("床位费",)),
        ("药品费", ("药品费", "药费")),
        ("材料费", ("材料费", "医用材料")),
        ("检查检验费", ("检查费", "检验费", "化验费")),
        ("治疗费", ("治疗费",)),
        ("手术费", ("手术费",)),
        ("护理费", ("护理费",)),
        ("目录范围", ("社会医疗保险目录", "基本医疗保险目录", "目录外")),
        ("合理必要及实际发生", ("合理且必要", "实际支出", "实际发生")),
    ),
    "reimbursement_rate_rules": (
        ("给付比例", ("给付比例", "赔付比例", "报销比例", "%")),
        (
            "社会医疗保险结算条件",
            ("社会医疗保险结算", "基本医疗保险结算", "医保结算"),
        ),
        (
            "未使用社会医疗保险结算",
            ("未使用社会医疗保险", "未使用基本医疗保险", "未经医保结算"),
        ),
        ("预审核条件", ("预审核", "事前审核")),
        ("医保目录条件", ("医保目录内", "医保目录外")),
    ),
    "claim_application_deadline_and_documents": (
        ("保险事故通知", ("事故通知", "通知本公司", "通知保险人", "通知我们")),
        ("申请或诉讼时效", ("诉讼时效", "申请时限")),
        (
            "保险公司核定时效",
            ("保险公司核定时效", "作出核定", "核定；", "核定。"),
        ),
        (
            "保险金给付时效",
            ("保险金给付时效", "履行给付保险金义务", "达成给付协议"),
        ),
        ("保险金申请书", ("保险金申请书", "理赔申请书")),
        ("身份或关系证明", ("身份证明", "有效身份证件", "关系证明", "受益人证明")),
        ("诊断病历或鉴定", ("诊断证明", "病历", "病理", "鉴定书", "伤残鉴定")),
        ("费用票据及清单", ("费用收据", "费用票据", "原始凭证", "费用清单", "结算清单")),
    ),
    "medical_service_benefits": (
        ("就医绿通", ("就医绿通", "绿色通道")),
        ("在线问诊", ("在线问诊", "线上问诊")),
        ("专家会诊", ("专家会诊", "专家门诊")),
        ("门诊预约", ("门诊预约", "预约挂号")),
        ("住院安排", ("住院安排", "住院协调")),
        ("陪诊服务", ("陪诊",)),
        ("费用垫付", ("费用垫付", "住院垫付", "一码垫付")),
        ("预赔闪赔", ("预赔", "闪赔")),
        ("线上理赔", ("线上理赔",)),
        ("康复护理", ("康复护理", "康复指导")),
    ),
}

_DOCUMENT_NAME_PATTERNS = (
    re.compile(r"pdf:(?P<name>[^#\]\r\n]+)#page=\d+"),
    re.compile(r"文档：(?P<name>[^｜】\r\n]+)"),
)
_CLAIM_APPLICATION_LABELS = ("申请时效", "理赔时效")
_INSURER_PROCESSING_MARKERS = ("作出核定", "核定", "履行给付", "达成给付协议")
_POLICY_RIGHT_DOCUMENT_MARKERS = ("解除合同通知书", "保险合同", "有效身份证件")
_POLICY_RIGHT_DEADLINE = re.compile(
    r"(?:收到|自).{0,40}?(?P<days>\d+)\s*日内.{0,40}?(?:退还|返还|给付)"
)


def _tag_subject(item: str) -> str:
    subject = item
    for marker in sorted(_TAG_DIRECTION_MARKERS, key=len, reverse=True):
        subject = subject.replace(marker, "")
    return subject.strip(" ：:、，,；;。()（）")


def _subject_polarity(subject: str, quotes: Sequence[str]) -> str | None:
    if not subject:
        return None
    relevant = tuple(_normalized(quote) for quote in quotes if subject in _normalized(quote))
    if not relevant:
        return None
    negative = any(any(marker in quote for marker in _NEGATIVE_TAG_MARKERS) for quote in relevant)
    positive = any(
        any(marker in quote for marker in _POSITIVE_TAG_MARKERS)
        and not any(marker in quote for marker in _NEGATIVE_TAG_MARKERS)
        for quote in relevant
    )
    if negative == positive:
        return None
    return "negative" if negative else "positive"


def normalize_business_field_value(
    field_id: str,
    value: CandidateValue,
    evidence_quotes: Sequence[str],
) -> CandidateValue:
    """Correct evidence-explicit tag polarity without inventing missing facts."""

    if field_id != "special_coverage_and_exclusion_tags":
        return value
    values = _items(value)
    normalized: list[str] = []
    for item in values:
        subject = _tag_subject(item)
        polarity = _subject_polarity(subject, evidence_quotes)
        item_negative = any(marker in item for marker in _NEGATIVE_TAG_MARKERS)
        if polarity == "negative" or (polarity is None and item_negative):
            normalized.append(f"{subject}不可赔")
        elif polarity == "positive" and any(marker in item for marker in _NEGATIVE_TAG_MARKERS):
            normalized.append(f"{subject}可赔")
        else:
            normalized.append(item)
    normalized_value: CandidateValue = tuple(dict.fromkeys(normalized))
    if isinstance(value, str) and len(normalized) == 1:
        normalized_value = normalized[0]
    return normalized_value


def _component_missing(
    field_id: str,
    value: CandidateValue | None,
    material: str,
) -> tuple[str, ...]:
    proposed = _normalized("，".join(_items(value)))
    if field_id == "claim_application_deadline_and_documents":
        # Health questions in underwriting documents are not claim documents.
        # Keep all contract pages, including continuation pages and footnotes.
        blocks = re.split(r"(?=【文档：|\[pdf:)", material)
        material = "\n".join(
            block for block in blocks
            if not any(
                term in name for name in _document_names(block)
                for term in ("投保规则", "保全规则", "健康告知")
            )
        )
    source = _normalized(material)
    return tuple(
        label
        for label, aliases in _COMPONENTS.get(field_id, ())
        if any(_normalized(alias) in source for alias in aliases)
        and not any(_normalized(alias) in proposed for alias in aliases)
    )


def _component_evidence_missing(
    field_id: str,
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> tuple[str, ...]:
    proposed = _normalized("，".join(_items(value)))
    evidence = _normalized("\n".join(evidence_quotes))
    return tuple(
        label
        for label, aliases in _COMPONENTS.get(field_id, ())
        if any(_normalized(alias) in proposed for alias in aliases)
        and not any(_normalized(alias) in evidence for alias in aliases)
    )


def _document_names(text: str) -> tuple[str, ...]:
    names: list[str] = []
    for pattern in _DOCUMENT_NAME_PATTERNS:
        names.extend(match.group("name").strip() for match in pattern.finditer(text))
    return tuple(dict.fromkeys(name for name in names if name))


def _contains_document_term(document_names: Sequence[str], terms: Sequence[str]) -> bool:
    return any(
        _normalized(term) in _normalized(document_name)
        for document_name in document_names
        for term in terms
    )


def _missing_authoritative_source(
    field_id: str,
    *,
    candidate_text: str,
    evidence_locators: Sequence[str],
) -> tuple[str, ...]:
    profile = field_extraction_profile(field_id)
    if profile is None or not profile.required_evidence_document_terms:
        return ()
    required = profile.required_evidence_document_terms
    available = _contains_document_term(_document_names(candidate_text), required)
    if not available or not evidence_locators:
        return ()
    if _contains_document_term(_document_names("\n".join(evidence_locators)), required):
        return ()
    return required


def _authoritative_item_evidence_missing(
    field_id: str,
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    evidence_locators: Sequence[str],
    candidate_text: str = "",
) -> tuple[str, ...]:
    profile = field_extraction_profile(field_id)
    if (
        profile is None
        or not profile.required_evidence_document_terms
        or not evidence_locators
    ):
        return ()
    authoritative_quotes = tuple(
        strip_defined_footnote_references(_normalized(quote), candidate_text)
        for quote, locator in zip(evidence_quotes, evidence_locators, strict=False)
        if _contains_document_term(
            _document_names(locator),
            profile.required_evidence_document_terms,
        )
    )
    return tuple(
        item
        for item in _items(value)
        if not any(
            _evidence_supports(
                strip_defined_footnote_references(_normalized(item), candidate_text), quote
            )
            for quote in authoritative_quotes
        )
    )


def _claim_deadline_semantically_conflated(value: CandidateValue | None) -> bool:
    text = "\n".join(_items(value))
    return any(
        any(label in segment for label in _CLAIM_APPLICATION_LABELS)
        and any(marker in segment for marker in _INSURER_PROCESSING_MARKERS)
        for segment in re.split(r"[。；;\n]+", text)
    )


def _policy_right_details_missing(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> tuple[str, ...]:
    proposed = _normalized("，".join(_items(value)))
    evidence = _normalized("\n".join(evidence_quotes))
    missing = [
        marker
        for marker in _POLICY_RIGHT_DOCUMENT_MARKERS
        if _normalized(marker) in evidence and _normalized(marker) not in proposed
    ]
    for match in _POLICY_RIGHT_DEADLINE.finditer(evidence):
        duration = f"{match.group('days')}日"
        if duration not in proposed:
            missing.append(duration)
    return tuple(dict.fromkeys(missing))


def _tag_supported(item: str, quotes: Sequence[str]) -> bool:
    subject = _tag_subject(item)
    polarity = _subject_polarity(subject, quotes)
    if not subject or polarity is None:
        return False
    item_negative = any(marker in item for marker in _NEGATIVE_TAG_MARKERS)
    item_positive = any(marker in item for marker in _POSITIVE_TAG_MARKERS) and not item_negative
    return (polarity == "negative" and item_negative) or (polarity == "positive" and item_positive)


def supported_special_coverage_tags(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> tuple[str, ...]:
    return tuple(item for item in _items(value) if _tag_supported(item, evidence_quotes))


_SERVICE_FREQUENCY = re.compile(
    r"^(?P<name>.+?)\s+(?P<frequency>不限次|\d+\s*次\s*/\s*(?:年|住院))$"
)
_SERVICE_SCENES = ("院前就医", "院中治疗", "院后康复")


def expand_service_table_values(
    value: CandidateValue | None,
    evidence_quotes: Sequence[str],
) -> CandidateValue | None:
    expanded: list[str] = []
    for quote in evidence_quotes:
        for raw_line in quote.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            match = _SERVICE_FREQUENCY.match(line)
            if match is None:
                continue
            name = match.group("name").strip()
            for scene in _SERVICE_SCENES:
                if name.startswith(f"{scene} "):
                    name = name[len(scene) :].strip()
                    break
            frequency = re.sub(r"\s+", "", match.group("frequency"))
            if name and name not in {"服务权益", "服务场景"}:
                expanded.append(f"{name}：{frequency}")
    return tuple(dict.fromkeys(expanded)) if expanded else value


def audit_business_priority_candidate(
    *,
    field_id: str,
    proposed_value: CandidateValue | None,
    evidence_quotes: Sequence[str],
    candidate_text: str,
    evidence_locators: Sequence[str] = (),
) -> M156FieldDecision:
    if field_id not in BUSINESS_PRIORITY_FIELD_IDS or field_id == "waiting_period":
        raise ValueError("BUSINESS_PRIORITY_FIELD_INVALID")
    missing_source = _missing_authoritative_source(
        field_id,
        candidate_text=candidate_text,
        evidence_locators=evidence_locators,
    )
    if missing_source:
        return M156FieldDecision(
            accepted=False,
            reason="BUSINESS_FIELD_AUTHORITATIVE_SOURCE_MISSING",
            atomic_item_count=len(_items(proposed_value)),
            supported_item_count=0,
            missing_components=missing_source,
        )
    if field_id in {"exclusions", "policyholder_rights"}:
        decision = audit_m156_candidate(
            field_id=field_id,
            proposed_value=proposed_value,
            evidence_quotes=evidence_quotes,
            candidate_text=candidate_text,
        )
        if not decision.accepted:
            return decision
        authoritative_missing = (
            _authoritative_item_evidence_missing(
                field_id,
                proposed_value,
                evidence_quotes,
                evidence_locators,
                candidate_text,
            )
            if field_id == "exclusions"
            else ()
        )
        if authoritative_missing:
            return M156FieldDecision(
                accepted=False,
                reason="BUSINESS_FIELD_AUTHORITATIVE_ITEM_EVIDENCE_MISSING",
                atomic_item_count=decision.atomic_item_count,
                supported_item_count=decision.atomic_item_count
                - len(authoritative_missing),
                missing_components=authoritative_missing,
            )
        if field_id == "policyholder_rights":
            missing_details = _policy_right_details_missing(
                proposed_value,
                evidence_quotes,
            )
            if missing_details:
                return M156FieldDecision(
                    accepted=False,
                    reason="POLICY_RIGHT_DETAILS_INCOMPLETE",
                    atomic_item_count=decision.atomic_item_count,
                    supported_item_count=decision.supported_item_count,
                    missing_components=missing_details,
                )
        return decision

    items = _items(proposed_value)
    if _has_unsupported_shortcut(proposed_value, evidence_quotes, _SHORTCUT_MARKERS):
        return M156FieldDecision(
            accepted=False,
            reason="BUSINESS_FIELD_CONTAINS_SHORTCUT",
            atomic_item_count=len(items),
            supported_item_count=0,
        )
    if field_id == "special_coverage_and_exclusion_tags":
        unsupported = tuple(item for item in items if not _tag_supported(item, evidence_quotes))
        reason = "SPECIAL_TAG_POLARITY_UNSUPPORTED"
        if unsupported:
            return M156FieldDecision(
                accepted=False,
                reason=reason,
                atomic_item_count=len(items),
                supported_item_count=len(items) - len(unsupported),
                missing_components=unsupported,
            )
    if (
        field_id == "claim_application_deadline_and_documents"
        and _claim_deadline_semantically_conflated(proposed_value)
    ):
        return M156FieldDecision(
            accepted=False,
            reason="CLAIM_DEADLINE_SEMANTIC_CONFLATION",
            atomic_item_count=len(items),
            supported_item_count=0,
            missing_components=("客户申请时效", "保险公司核定/给付时效"),
        )
    missing = _component_missing(field_id, proposed_value, candidate_text)
    if missing:
        return M156FieldDecision(
            accepted=False,
            reason="BUSINESS_FIELD_COMPONENTS_INCOMPLETE",
            atomic_item_count=len(items),
            supported_item_count=len(items),
            missing_components=missing,
        )
    evidence_missing = _component_evidence_missing(
        field_id,
        proposed_value,
        evidence_quotes,
    )
    if evidence_missing:
        return M156FieldDecision(
            accepted=False,
            reason="BUSINESS_FIELD_COMPONENT_EVIDENCE_MISSING",
            atomic_item_count=max(len(items), len(_COMPONENTS.get(field_id, ()))),
            supported_item_count=max(
                0,
                max(len(items), len(_COMPONENTS.get(field_id, ())))
                - len(evidence_missing),
            ),
            missing_components=evidence_missing,
        )
    component_count = len(_COMPONENTS.get(field_id, ()))
    atomic_count = max(len(items), component_count)
    return M156FieldDecision(
        accepted=bool(items and evidence_quotes),
        reason="BUSINESS_FIELD_COMPLETE" if items and evidence_quotes else "EMPTY_VALUE",
        atomic_item_count=atomic_count,
        supported_item_count=atomic_count,
    )


__all__ = [
    "audit_business_priority_candidate",
    "expand_service_table_values",
    "normalize_business_field_value",
    "supported_special_coverage_tags",
]
