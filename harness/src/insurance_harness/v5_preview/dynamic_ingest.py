from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from .contracts import (
    CandidateEvidence,
    CandidateValue,
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
    PluginResult,
)
from .field_profiles import (
    FULL_MATERIAL_PROFILE_FIELD_IDS,
    field_extraction_profile,
)
from .value_constraints import normalize_field_value


class CandidateSourcePage(Protocol):
    document_name: str
    page_number: int
    text: str


class SemanticSimilarityPort(Protocol):
    """Optional page-level semantic scorer supplied by an ingest adapter."""

    def score(self, *, query: str, documents: Sequence[str]) -> Sequence[float]: ...


class FieldCandidateRetriever(Protocol):
    """Pluggable all-page candidate retrieval boundary."""

    def retrieve(
        self,
        pages: Sequence[CandidateSourcePage],
        schema: InsuranceSchema,
        field_ids: Sequence[str],
        *,
        max_pages_per_field: int | None = None,
    ) -> dict[str, tuple[FieldCandidate, ...]]: ...


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    field_id: str
    document_name: str
    page_number: int
    score: int
    matched_keywords: tuple[str, ...]
    start_offset: int = 0
    end_offset: int = 0
    reasons: tuple[str, ...] = ()

    @property
    def locator(self) -> str:
        return f"pdf:{self.document_name}#page={self.page_number}"


@dataclass(frozen=True, slots=True)
class CandidateCoverage:
    """Deterministic coverage receipt for one field's source scan."""

    field_id: str
    scanned_page_count: int
    candidate_page_count: int
    selected_page_count: int
    snippet_page_count: int
    candidate_locators: tuple[str, ...]
    selected_locators: tuple[str, ...]
    candidate_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateSourceSelection:
    """Bounded model context plus the full-scan coverage receipt."""

    text: str
    coverage: Mapping[str, CandidateCoverage]


@dataclass(frozen=True, slots=True)
class ExtractionBatch:
    index: int
    category_ids: tuple[str, ...]
    field_ids: tuple[str, ...]
    field_ordinals: tuple[int, ...]


# These fields are easy to miss when the source uses a section heading or a
# product-specific expression instead of the schema label. They get an
# ordered all-page context in addition to the ordinary ranked snippets.
_FULL_MATERIAL_FIELD_IDS = frozenset(
    {
        "premium_grace_period",
        "product_conversion_rules",
        "premium_adjustment_rules",
        "product_summary",
        "product_overview",
        "coverage_responsibilities",
        "exclusions",
        "premium_payment_term",
        "premium_payment_frequency",
        "policyholder_rights",
        "waiting_period",
        "disease_definitions_and_criteria",
        *FULL_MATERIAL_PROFILE_FIELD_IDS,
    }
)


_FIELD_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "product_summary": ("产品特色", "主要保单利益", "保险责任"),
    "official_product_features": ("产品特色", "产品特点"),
    "target_customer_profile": (
        "适用人群",
        "目标人群",
        "投保年龄",
        "投保范围",
        "被保险人范围",
        "家庭成员",
        "成人",
        "少儿",
        "儿童",
        "家人",
        "家庭生活",
    ),
    "marketing_tagline": ("宣传语", "产品特色"),
    "product_overview": ("产品特色", "主要保单利益", "产品介绍"),
    "entry_age_range": ("投保年龄", "年龄范围", "接受的投保年龄"),
    "insured_eligibility": ("投保范围", "被保险人范围"),
    "health_declaration_requirements": ("健康告知", "如实告知"),
    "geographic_eligibility_requirements": ("常住地", "居住区域", "中国内地"),
    "social_insurance_requirements": ("社会医疗保险", "基本医疗保险", "社保"),
    "eligible_occupation_classes": ("职业类别", "职业范围", "职业"),
    "underwriting_method": ("核保", "审核同意", "同意承保", "承保决定"),
    "underwriting_investigation_requirements": (
        "如实告知",
        "提出询问",
        "补充资料",
        "体检",
        "核保调查",
    ),
    "premium_payment_term": ("交费期间", "交费期限", "缴费期间", "缴费期限"),
    "premium_payment_frequency": ("交费方式", "缴费方式", "年交", "月交"),
    "cooling_off_period": ("犹豫期",),
    "waiting_period": ("等待期",),
    "premium_grace_period": ("宽限期",),
    "coverage_period": ("保险期间", "保障期间"),
    "surrender_and_cancellation_terms": ("解除合同", "退保", "现金价值"),
    "coverage_and_renewal_terms": ("续保", "保险期间届满"),
    "guaranteed_renewal_status": ("保证续保",),
    "guaranteed_renewal_period": ("保证续保期间",),
    "product_conversion_rules": (
        "转换",
        "转换为",
        "险种转换",
        "转保",
        "可转换",
        "转换权",
    ),
    "premium_adjustment_rules": (
        "费率调整",
        "调整保险费率",
        "调整费率",
        "费率可调整",
        "费率因子",
        "费率系数",
        "重新定价",
        "提高保险费率",
    ),
    "post_discontinuation_renewal_arrangement": ("停售", "停止销售", "续保安排"),
    "covered_risk_categories": ("保险责任", "主要保单利益"),
    "coverage_responsibilities": ("保险责任", "我们承担"),
    "coverage_summary": (
        "主要保单利益",
        "保险责任",
        "保障责任",
        "保什么",
        "我们承担",
        "给付",
        "赔付",
        "保险金",
        "医疗费用",
        "身故",
        "满期",
        "生存",
        "重大疾病",
        "意外",
    ),
    "sum_assured_range": ("基本保险金额", "保险金额", "给付限额"),
    "total_disability_coverage_flag": ("全残",),
    "accidental_death_coverage_flag": ("意外身故",),
    "disease_death_coverage_flag": ("疾病身故", "身故保险金", "身故保障"),
    "additional_benefit_rules": ("额外保险金", "附加", "额外给付"),
    "special_coverage_and_exclusion_tags": ("责任免除", "除外", "不承担"),
    "exclusions": ("责任免除", "不承担给付保险金的责任"),
    "pre_existing_condition_rules": ("既往症", "既往疾病"),
    "out_of_hospital_special_drug_coverage": ("院外特定药品", "外购药", "特药"),
    "indemnity_principle": ("补偿原则", "费用补偿"),
    "zero_deductible_flag": ("0免赔", "零免赔"),
    "deductible_rules": ("免赔额",),
    "outpatient_inpatient_scope": ("门诊", "住院"),
    "reimbursable_expense_scope": ("医疗费用范围", "合理且必要"),
    "reimbursement_rate_rules": ("给付比例", "赔付比例", "补偿比例"),
    "eligible_hospital_scope": ("医院范围", "二级以上公立医院"),
    "premium_medical_facility_coverage": ("特需医疗", "国际医疗", "高端医疗"),
    "direct_billing_and_advance_payment_rules": ("直付", "垫付"),
    "claim_application_deadline_and_documents": ("保险金申请", "申请材料", "诉讼时效"),
    "policyholder_rights": ("保单权益", "合同权益"),
    "eligible_service_packages": (
        "可享服务",
        "服务权益",
        "在线问诊",
        "门诊预约",
        "陪诊",
        "住院照护",
        "专家会诊",
        "特药",
        "康复护理",
    ),
    "medical_service_benefits": ("健康服务", "增值服务", "就医服务"),
    "tax_qualified_status": ("税优", "个人所得税"),
    "tax_benefit_rules": ("税收优惠", "税前扣除"),
    "product_faq": ("产品Q&A", "常见问题", "Q1", "Q2", "问答"),
    "policy_role": ("主险", "附加险"),
}

# These are semantic expressions found in the Schema descriptions/value guidance
# and in the business badcases. They are product-agnostic: no file name, product ID
# or expected answer is encoded here.
_FIELD_SEMANTIC_TERMS: Mapping[str, tuple[str, ...]] = {
    "premium_payment_term": (
        "趸交",
        "一次性交清",
        "分期交纳",
        "分期支付",
        "交费年期",
        "缴费年期",
        "交清保险费",
    ),
    "premium_payment_frequency": (
        "趸交",
        "分期交纳",
        "分期支付",
        "半年交",
        "季交",
        "按年交纳",
        "按月交纳",
    ),
    "annuity_benefit_types": (
        "生存保险金",
        "年金",
        "满期保险金",
        "养老保险金",
        "领取型保险金",
    ),
    "annuity_start_time": (
        "开始领取",
        "首次领取",
        "首次给付",
        "首个保单周年日",
        "领取日",
    ),
    "annuity_start_age": (
        "领取年龄",
        "年满",
        "周岁后的首个保单周年日",
        "开始领取年龄",
    ),
    "annuity_payment_frequency": (
        "按年领取",
        "按月领取",
        "年领",
        "月领",
        "一次性领取",
        "领取日",
        "领取方式",
    ),
    "sum_assured_reduction_rules": (
        "减少基本保险金额",
        "申请减少",
        "基本保险金额减少",
        "减保",
        "部分领取现金价值",
    ),
    "policyholder_rights": (
        "保单贷款",
        "自动垫交",
        "减额交清",
        "现金价值",
        "解除合同",
    ),
    "claim_application_deadline_and_documents": (
        "保险金申请人",
        "申请保险金",
        "应当提供下列证明和资料",
        "证明和资料",
        "请求给付保险金的诉讼时效",
    ),
}

_SCHEMA_CONCEPT_VOCABULARY = (
    "趸交",
    "期交",
    "分期交纳",
    "分期支付",
    "年交",
    "半年交",
    "季交",
    "月交",
    "生存保险金",
    "满期保险金",
    "养老保险金",
    "开始领取",
    "首次领取",
    "首次给付",
    "保单周年日",
    "领取年龄",
    "领取频率",
    "领取方式",
    "减少基本保险金额",
    "部分领取",
    "现金价值",
    "保单贷款",
    "自动垫交",
    "减额交清",
    "申请材料",
    "证明和资料",
    "诉讼时效",
)

_WEAK_QUERY_TERMS = frozenset(
    {
        "年交",
        "月交",
        "趸交",
        "保险费",
        "保费",
        "年金",
        "领取",
        "周岁",
        "给付",
        "保险金",
    }
)


@dataclass(frozen=True, slots=True)
class _QueryTerm:
    value: str
    weight: int
    reason: str
    weak: bool = False


@dataclass(frozen=True, slots=True)
class _TermHit:
    start: int
    end: int
    term: _QueryTerm

_GENERIC_SUFFIXES = (
    "要求",
    "规则",
    "标记",
    "标签",
    "摘要",
    "范围",
    "方式",
    "条款",
    "分类",
    "状态",
)


def _normalized(value: str) -> str:
    return "".join(
        character.lower()
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _field_keywords(field: FieldDefinition) -> tuple[str, ...]:
    values: list[str] = [field.display_name, *_FIELD_KEYWORDS.get(field.field_id, ())]
    for separator in ("/", "、", "及", "与"):
        values.extend(part for value in tuple(values) for part in value.split(separator))
    values.extend(
        value[: -len(suffix)]
        for value in tuple(values)
        for suffix in _GENERIC_SUFFIXES
        if value.endswith(suffix)
    )
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = value.strip(" ：:（）()")
        normalized = _normalized(keyword)
        if len(normalized) >= 2 and normalized not in seen:
            seen.add(normalized)
            unique.append(keyword)
    return tuple(unique)


def _schema_value_terms(field: FieldDefinition) -> tuple[str, ...]:
    values = re.split(r"[\s,，、。；;：:/（）()]+", field.value_guidance)
    return tuple(
        value
        for value in values
        if 2 <= len(_normalized(value)) <= 16
        and _normalized(value) not in {"是否", "其他", "不适用"}
    )


def _field_query_terms(field: FieldDefinition) -> tuple[_QueryTerm, ...]:
    terms: dict[str, _QueryTerm] = {}

    def add(value: str, *, weight: int, reason: str) -> None:
        normalized = _normalized(value)
        if len(normalized) < 2:
            return
        term = _QueryTerm(
            value=value,
            weight=weight,
            reason=reason,
            weak=value in _WEAK_QUERY_TERMS or bool(re.fullmatch(r"\d+年", value)),
        )
        current = terms.get(normalized)
        if current is None or term.weight > current.weight:
            terms[normalized] = term

    for keyword in _field_keywords(field):
        add(
            keyword,
            weight=12 if _normalized(keyword) == _normalized(field.display_name) else 8,
            reason=(
                "schema_label"
                if _normalized(keyword) == _normalized(field.display_name)
                else "schema_keyword"
            ),
        )
    profile = field_extraction_profile(field.field_id)
    semantic_terms = (
        *_FIELD_SEMANTIC_TERMS.get(field.field_id, ()),
        *(profile.semantic_terms if profile is not None else ()),
    )
    for value in semantic_terms:
        add(value, weight=9, reason="schema_alias")
    for value in _schema_value_terms(field):
        add(value, weight=6, reason="schema_value_guidance")

    schema_sections = {
        "description": field.description,
        "source_guidance": field.source_guidance,
    }
    for section, source in schema_sections.items():
        normalized_source = _normalized(source)
        for concept in _SCHEMA_CONCEPT_VOCABULARY:
            if _normalized(concept) in normalized_source:
                add(concept, weight=5, reason=f"schema_{section}")
    return tuple(terms.values())


def _field_semantic_query(field: FieldDefinition) -> str:
    profile = field_extraction_profile(field.field_id)
    return "｜".join(
        part
        for part in (
            field.display_name,
            field.description,
            field.value_guidance,
            field.source_guidance,
            "、".join(_FIELD_SEMANTIC_TERMS.get(field.field_id, ())),
            "、".join(profile.semantic_terms) if profile is not None else "",
        )
        if part
    )


def _normalized_with_offsets(value: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(value):
        for normalized in unicodedata.normalize("NFKC", character).lower():
            if normalized.isspace():
                continue
            characters.append(normalized)
            offsets.append(index)
    return "".join(characters), tuple(offsets)


def _term_hits(text: str, terms: Sequence[_QueryTerm]) -> tuple[_TermHit, ...]:
    normalized_text, offsets = _normalized_with_offsets(text)
    hits: list[_TermHit] = []
    for term in terms:
        needle = _normalized(term.value)
        start = 0
        while (position := normalized_text.find(needle, start)) >= 0:
            original_start = offsets[position]
            original_end = offsets[position + len(needle) - 1] + 1
            hits.append(_TermHit(original_start, original_end, term))
            start = position + max(1, len(needle))
    return tuple(sorted(hits, key=lambda hit: (hit.start, hit.end)))


def _best_candidate_span(
    text: str,
    hits: Sequence[_TermHit],
    *,
    window_characters: int = 1_200,
) -> tuple[int, int, int, tuple[_TermHit, ...]]:
    best: tuple[int, int, tuple[_TermHit, ...]] | None = None
    radius = window_characters // 2
    for anchor in hits:
        nearby = tuple(
            hit
            for hit in hits
            if anchor.start - radius <= hit.start <= anchor.start + radius
        )
        unique_weights: dict[str, int] = {}
        for hit in nearby:
            key = _normalized(hit.term.value)
            unique_weights[key] = max(unique_weights.get(key, 0), hit.term.weight)
        score = sum(unique_weights.values()) + min(6, len(nearby))
        candidate = (score, -anchor.start, nearby)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return 0, min(len(text), window_characters), 0, ()

    selected = best[2]
    hit_start = min(hit.start for hit in selected)
    hit_end = max(hit.end for hit in selected)
    start = max(0, hit_start - 320)
    end = min(len(text), max(hit_end + 560, start + window_characters))

    left_boundaries = (
        text.rfind("\n\n", start, hit_start),
        text.rfind("\n", start, hit_start),
        text.rfind("。", start, hit_start),
    )
    boundary = max(left_boundaries)
    if boundary >= start:
        start = boundary + 1
    right_boundaries = tuple(
        position
        for position in (
            text.find("\n\n", hit_end, end),
            text.find("\n", hit_end, end),
            text.find("。", hit_end, end),
        )
        if position >= 0
    )
    if right_boundaries:
        end = min(right_boundaries) + 1
    return start, end, best[0], selected


def _source_guidance_bonus(page: CandidateSourcePage, field: FieldDefinition) -> int:
    guidance = _normalized(field.source_guidance)
    document_name = _normalized(page.document_name.rsplit(".", 1)[0])
    roles = ("产品说明书", "保险条款", "费率表", "服务手册", "投保规则")
    matched = any(
        _normalized(role) in guidance and _normalized(role) in document_name
        for role in roles
    )
    return 4 if matched else 0


def _looks_like_weak_rate_table(
    page: CandidateSourcePage,
    selected_hits: Sequence[_TermHit],
) -> bool:
    if not selected_hits or any(not hit.term.weak for hit in selected_hits):
        return False
    text = page.text
    rate_table_role = "费率表" in page.document_name or (
        ("费率" in text or "保险费" in text)
        and sum(character.isdigit() for character in text) >= max(8, len(text) // 12)
    )
    return rate_table_role


def _field_value_signal_bonus(
    page: CandidateSourcePage,
    field: FieldDefinition,
    *,
    start: int,
    end: int,
) -> int:
    """Prefer answer-shaped passages without converting retrieval into extraction."""

    region = _normalized(page.text[start:end])
    patterns: Mapping[str, tuple[str, ...]] = {
        "premium_payment_term": (
            r"(?:交|缴)费(?:期|期间|期限|年期)(?:为|有|可选|选择|包括|分为|:|：)*"
            r"(?:趸交|一次性交清|\d{1,2}年)",
            r"(?:趸交|一次性交清|\d{1,2}年)(?:、|,|，|及|或)*"
            r"(?:交|缴)费",
        ),
        "premium_payment_frequency": (
            r"(?:趸交|年交|半年交|季交|月交)(?:保费|保险费)",
            r"(?:交|缴)费方式.{0,40}(?:趸交|年交|半年交|季交|月交)",
        ),
        "annuity_start_time": (
            r"开始领取时间.{0,80}(?:第\d+个保单周年日|\d{1,3}周岁)",
        ),
        "annuity_start_age": (
            r"开始领取年龄.{0,80}\d{1,3}周岁",
        ),
        "annuity_payment_frequency": (
            r"领取方式.{0,80}(?:年领|月领|季领|半年领|一次性领取)",
        ),
        "sum_assured_reduction_rules": (
            r"(?:申请减少|减少基本保险金额).{0,120}(?:不得超过|现金价值|审核同意)",
        ),
        "claim_application_deadline_and_documents": (
            r"(?:申请保险金|保险金申请).{0,160}(?:证明和资料|申请书)",
        ),
        "policyholder_rights": (
            r"(?:其他权益|保单权益).{0,160}(?:现金价值|保单贷款|自动垫交|减额交清)",
        ),
    }
    matches_value_shape = any(
        re.search(pattern, region) for pattern in patterns.get(field.field_id, ())
    )
    return 18 if matches_value_shape else 0


def _candidate_for_page(
    page: CandidateSourcePage,
    field: FieldDefinition,
    terms: Sequence[_QueryTerm],
    *,
    semantic_score: float | None = None,
) -> FieldCandidate | None:
    hits = _term_hits(page.text, terms)
    start, end, score, selected_hits = _best_candidate_span(page.text, hits)
    reasons = list(dict.fromkeys(hit.term.reason for hit in selected_hits))
    matched = tuple(dict.fromkeys(hit.term.value for hit in selected_hits))
    if semantic_score is not None and semantic_score >= 0.55:
        score += round(semantic_score * 100)
        reasons.append("semantic_similarity")
        if not hits:
            start, end = 0, min(len(page.text), 1_200)
    value_signal_bonus = _field_value_signal_bonus(
        page,
        field,
        start=start,
        end=end,
    )
    if value_signal_bonus:
        score += value_signal_bonus
        reasons.append("field_value_signal")
    if score <= 0:
        return None
    score += _source_guidance_bonus(page, field)
    if _looks_like_weak_rate_table(page, selected_hits):
        score = max(1, score // 4)
        reasons.append("weak_repetitive_rate_table")
    return FieldCandidate(
        field_id=field.field_id,
        document_name=page.document_name,
        page_number=page.page_number,
        score=score,
        matched_keywords=matched,
        start_offset=start,
        end_offset=end,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _candidate_score(
    page: CandidateSourcePage,
    field: FieldDefinition,
) -> tuple[int, tuple[str, ...]]:
    candidate = _candidate_for_page(page, field, _field_query_terms(field))
    return (
        (candidate.score, candidate.matched_keywords)
        if candidate is not None
        else (0, ())
    )


class AllPageFieldCandidateRetriever:
    """Deterministic full-page scanner with an optional semantic scoring port."""

    def __init__(
        self,
        *,
        semantic_similarity: SemanticSimilarityPort | None = None,
        max_weak_pages_per_document: int = 2,
    ) -> None:
        if max_weak_pages_per_document < 0:
            raise ValueError("M151_WEAK_PAGE_LIMIT_INVALID")
        self._semantic_similarity = semantic_similarity
        self._max_weak_pages_per_document = max_weak_pages_per_document

    def retrieve(
        self,
        pages: Sequence[CandidateSourcePage],
        schema: InsuranceSchema,
        field_ids: Sequence[str],
        *,
        max_pages_per_field: int | None = None,
    ) -> dict[str, tuple[FieldCandidate, ...]]:
        if max_pages_per_field is not None and max_pages_per_field < 1:
            raise ValueError("M127_CANDIDATE_PAGE_LIMIT_INVALID")
        definitions = {field.field_id: field for field in schema.fields}
        invalid_field_set = len(set(field_ids)) != len(field_ids) or any(
            field_id not in definitions for field_id in field_ids
        )
        if invalid_field_set:
            raise ValueError("M127_CANDIDATE_FIELD_SET_INVALID")
        source_order = {
            (page.document_name, page.page_number): index for index, page in enumerate(pages)
        }
        located: dict[str, tuple[FieldCandidate, ...]] = {}
        for field_id in field_ids:
            field = definitions[field_id]
            terms = _field_query_terms(field)
            semantic_scores: Sequence[float | None]
            if self._semantic_similarity is None:
                semantic_scores = (None,) * len(pages)
            else:
                raw_scores = tuple(
                    self._semantic_similarity.score(
                        query=_field_semantic_query(field),
                        documents=tuple(page.text for page in pages),
                    )
                )
                if len(raw_scores) != len(pages):
                    raise ValueError("M151_SEMANTIC_SCORE_SHAPE_INVALID")
                semantic_scores = raw_scores
            candidates = [
                candidate
                for page, semantic_score in zip(pages, semantic_scores, strict=True)
                if (
                    candidate := _candidate_for_page(
                        page,
                        field,
                        terms,
                        semantic_score=semantic_score,
                    )
                )
                is not None
            ]
            candidates.sort(
                key=lambda item: (
                    -item.score,
                    source_order[(item.document_name, item.page_number)],
                )
            )
            filtered: list[FieldCandidate] = []
            weak_counts: dict[str, int] = {}
            for candidate in candidates:
                if "weak_repetitive_rate_table" in candidate.reasons:
                    count = weak_counts.get(candidate.document_name, 0)
                    if count >= self._max_weak_pages_per_document:
                        continue
                    weak_counts[candidate.document_name] = count + 1
                filtered.append(candidate)
            profile = field_extraction_profile(field_id)
            if (
                max_pages_per_field is not None
                and profile is not None
                and profile.preserve_document_diversity
            ):
                diverse: list[FieldCandidate] = []
                seen_documents: set[str] = set()
                for candidate in filtered:
                    if candidate.document_name in seen_documents:
                        continue
                    diverse.append(candidate)
                    seen_documents.add(candidate.document_name)
                    if len(diverse) >= max_pages_per_field:
                        break
                for candidate in filtered:
                    if len(diverse) >= max_pages_per_field:
                        break
                    if candidate not in diverse:
                        diverse.append(candidate)
                filtered = diverse
            elif max_pages_per_field is not None:
                filtered = filtered[:max_pages_per_field]
            located[field_id] = tuple(filtered)
        return located


_DEFAULT_FIELD_CANDIDATE_RETRIEVER = AllPageFieldCandidateRetriever()


def locate_field_candidates(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    max_pages_per_field: int | None = None,
    retriever: FieldCandidateRetriever | None = None,
) -> dict[str, tuple[FieldCandidate, ...]]:
    return (retriever or _DEFAULT_FIELD_CANDIDATE_RETRIEVER).retrieve(
        pages,
        schema,
        field_ids,
        max_pages_per_field=max_pages_per_field,
    )


def build_candidate_source_text(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    max_pages: int = 18,
    max_characters: int = 75_000,
    max_pages_per_field: int | None = None,
    snippet_characters: int = 1_200,
    retriever: FieldCandidateRetriever | None = None,
) -> str:
    full_material_fields = tuple(
        field_id for field_id in field_ids if field_id in _FULL_MATERIAL_FIELD_IDS
    )
    if full_material_fields:
        # Reserve most of the request for the complete ordered scan. The
        # ranked snippets remain useful for neighbouring fields in the same
        # micro-batch, but must not crowd out a page entirely.
        full_budget = max(20_000, int(max_characters * 0.70))
        full_text = build_full_material_field_source_text(
            pages,
            schema,
            full_material_fields,
            max_characters=min(full_budget, max_characters),
        )
        remaining = max_characters - len(full_text) - 2
        if remaining <= 1_000:
            return full_text[:max_characters]
        ranked = select_candidate_source(
            pages,
            schema,
            field_ids,
            max_pages=max_pages,
            max_characters=remaining,
            max_pages_per_field=max_pages_per_field,
            snippet_characters=snippet_characters,
            retriever=retriever,
        ).text
        text = f"{full_text}\n\n{ranked}" if ranked else full_text
        return text[:max_characters]

    selection = select_candidate_source(
        pages,
        schema,
        field_ids,
        max_pages=max_pages,
        max_characters=max_characters,
        max_pages_per_field=max_pages_per_field,
        snippet_characters=snippet_characters,
        retriever=retriever,
    )
    if "coverage_summary" not in field_ids:
        return selection.text

    # ``保什么`` is a cross-section synthesis field. The ordinary field ranking
    # remains useful for the other fields, while this second context collects
    # responsibility language that may not contain the field label at all.
    # Keep the combined request within the caller's budget. The dedicated
    # coverage context is a supplement, not an extra unbounded payload.
    coverage_budget = max(12_000, min(60_000, max_characters // 3))
    coverage_text = build_coverage_summary_source_text(
        pages,
        max_pages=max(24, min(48, max_pages * 2)),
        max_characters=coverage_budget,
    )
    prefix = "【保什么专项候选上下文】\n"
    remaining = max(1_000, max_characters - len(selection.text) - len(prefix) - 2)
    return f"{selection.text}\n\n{prefix}{coverage_text[:remaining]}"


def build_full_material_field_source_text(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    max_characters: int = 100_000,
) -> str:
    """Build an ordered all-page context for semantic target fields.

    Every page is scanned before the context is bounded. If the complete text
    does not fit, each page still contributes bounded head/middle/tail windows and
    keeps its document/page marker so coverage cannot silently disappear.
    """
    if max_characters < 1_000:
        raise ValueError("M143_FULL_MATERIAL_CONTEXT_LIMIT_INVALID")
    definitions = {field.field_id: field for field in schema.fields}
    requested = tuple(field_ids)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("M143_FULL_MATERIAL_FIELD_SET_INVALID")
    if any(field_id not in definitions for field_id in requested):
        raise ValueError("M143_FULL_MATERIAL_FIELD_SET_INVALID")
    page_list = tuple(pages)
    if not page_list:
        return "【字段全材料扫描：" + ",".join(requested) + "】\n（没有可用页面）"

    prefix = "【字段全材料扫描：" + ",".join(requested) + "】\n"
    marker_overhead = sum(
        len(f"【文档：{page.document_name}｜页码：{page.page_number}】\n")
        for page in page_list
    )
    body_budget = max(1, max_characters - len(prefix) - marker_overhead)
    per_page_budget = max(1, body_budget // len(page_list))
    parts = [prefix.rstrip("\n")]
    for page in page_list:
        marker = f"【文档：{page.document_name}｜页码：{page.page_number}】\n"
        text = page.text.strip()
        excerpt = distributed_page_excerpt(text, max_characters=per_page_budget)
        parts.append(marker + excerpt)
    return "\n\n".join(parts)[:max_characters]


def distributed_page_excerpt(text: str, *, max_characters: int) -> str:
    """Keep ordered head, middle and tail windows instead of silently losing the middle."""

    if max_characters < 1:
        return ""
    if len(text) <= max_characters:
        return text
    separator = "……（本页连续分窗省略）……"
    usable = max_characters - (2 * len(separator))
    if usable < 60:
        return text[:max_characters]
    head_size = usable // 3
    middle_size = usable // 3
    tail_size = usable - head_size - middle_size
    middle_start = max(head_size, (len(text) - middle_size) // 2)
    tail_start = len(text) - tail_size
    return (
        text[:head_size]
        + separator
        + text[middle_start : middle_start + middle_size]
        + separator
        + text[tail_start:]
    )[:max_characters]


_COVERAGE_SEMANTIC_ANCHORS: tuple[str, ...] = (
    "保险责任",
    "保障责任",
    "主要保单利益",
    "我们承担",
    "承担下列责任",
    "给付",
    "赔付",
    "保险金",
    "医疗费用",
    "身故",
    "满期",
    "生存",
    "重大疾病",
    "意外",
    "住院",
    "门诊",
    "伤残",
)


def _coverage_semantic_score(page: CandidateSourcePage) -> int:
    text = _normalized(page.text)
    score = 0
    for anchor in _COVERAGE_SEMANTIC_ANCHORS:
        normalized = _normalized(anchor)
        count = min(text.count(normalized), 4)
        if count:
            # Responsibility headings get more weight than incidental mentions.
            score += count * min(len(normalized), 10)
    for heading in ("保险责任", "保障责任", "主要保单利益", "我们承担"):
        if _normalized(heading) in text:
            score += 12
    if "责任免除" in text or "免责条款" in text:
        # Exclusions are useful surrounding context, but should not outrank
        # positive responsibility sections when the field is summarized.
        score = max(1, score - 8)
    return score


def _coverage_document_role(text: str) -> str:
    normalized = _normalized(text)
    if any(token in normalized for token in ("产品说明", "产品介绍", "产品特色")):
        return "产品说明内容"
    if any(token in normalized for token in ("本合同", "保险合同", "责任免除")):
        return "合同责任内容"
    if any(token in normalized for token in ("费率", "基本保险金额", "保险金额")):
        return "费率或额度内容"
    return "保障相关内容"


def build_coverage_summary_source_text(
    pages: Sequence[CandidateSourcePage],
    *,
    max_pages: int = 36,
    max_characters: int = 60_000,
    neighbor_pages: int = 1,
    snippet_characters: int = 1_800,
) -> str:
    """Build a filename-independent, cross-document context for ``保什么``.

    Every page is scored before the context budget is applied. Positive
    responsibility sections are admitted in source order, with adjacent pages
    kept for continuation clauses. Omitted hits remain represented as compact
    snippets, so a late page cannot silently become an extraction miss.
    """
    if max_pages < 1 or max_characters < 1_000:
        raise ValueError("M140_COVERAGE_CONTEXT_LIMIT_INVALID")
    if neighbor_pages < 0 or snippet_characters < 100:
        raise ValueError("M140_COVERAGE_CONTEXT_OPTION_INVALID")
    page_list = tuple(pages)
    if not page_list:
        return "（没有可用的保障责任候选页面）"

    indexed = list(enumerate(page_list))
    scored = [
        (index, page, _coverage_semantic_score(page))
        for index, page in indexed
        if _coverage_semantic_score(page) > 0
    ]
    if not scored:
        return "（未扫描到明确的保障责任语义候选）"

    selected_indices: set[int] = set()
    # Keep at least the best hit from each source document. This is based on
    # page content and source order, never on a particular filename.
    best_by_document: dict[str, tuple[int, int]] = {}
    for index, page, score in scored:
        current = best_by_document.get(page.document_name)
        if current is None or score > current[1]:
            best_by_document[page.document_name] = (index, score)
    for index, _score in best_by_document.values():
        selected_indices.add(index)

    ranked = sorted(scored, key=lambda row: (-row[2], row[0]))
    for index, _page, _score in ranked:
        if len(selected_indices) >= max_pages:
            break
        selected_indices.add(index)
    for index in tuple(selected_indices):
        page = page_list[index]
        same_document = [
            candidate_index
            for candidate_index, candidate_page in indexed
            if candidate_page.document_name == page.document_name
        ]
        position = same_document.index(index)
        selected_indices.update(
            same_document[max(0, position - neighbor_pages) : position + neighbor_pages + 1]
        )
    if len(selected_indices) > max_pages:
        selected_indices = set(
            sorted(
                selected_indices,
                key=lambda index: (
                    -next(score for hit, _page, score in scored if hit == index)
                    if any(hit == index for hit, _page, _score in scored)
                    else 0,
                    index,
                ),
            )[:max_pages]
        )

    parts: list[str] = []
    used = 0
    for index in sorted(selected_indices):
        page = page_list[index]
        part = (
            f"【材料线索：{_coverage_document_role(page.text)}｜文档：{page.document_name}｜"
            f"页码：{page.page_number}】\n{page.text}"
        )
        remaining = max_characters - used
        if remaining <= 0:
            break
        part = part[:remaining]
        parts.append(part)
        used += len(part) + 2

    # Add one centered snippet for every omitted semantic hit. This is the
    # recall bridge: all pages were scanned, but the provider gets bounded text.
    for index, page, _score in sorted(scored, key=lambda row: (-row[2], row[0])):
        if index in selected_indices or used >= max_characters:
            continue
        text = page.text
        if len(text) > snippet_characters:
            positions = [
                text.find(anchor)
                for anchor in _COVERAGE_SEMANTIC_ANCHORS
                if text.find(anchor) >= 0
            ]
            start = max(0, (min(positions) if positions else 0) - snippet_characters // 3)
            text = text[start : start + snippet_characters]
        part = (
            f"【保障责任候选片段｜文档：{page.document_name}｜页码：{page.page_number}】\n"
            f"{text}"
        )
        remaining = max_characters - used
        if remaining <= 0:
            break
        part = part[:remaining]
        parts.append(part)
        used += len(part) + 2
    return "\n\n".join(parts)


def _candidate_snippet(
    page: CandidateSourcePage,
    candidate: FieldCandidate,
    *,
    max_characters: int,
) -> str:
    """Keep a small field-centered window for pages omitted from full context."""
    text = page.text
    if len(text) <= max_characters:
        return text
    if 0 <= candidate.start_offset < candidate.end_offset <= len(text):
        center = (candidate.start_offset + candidate.end_offset) // 2
    else:
        offsets = [
            text.find(keyword)
            for keyword in candidate.matched_keywords
            if text.find(keyword) >= 0
        ]
        if not offsets:
            return distributed_page_excerpt(text, max_characters=max_characters)
        center = min(offsets)
    start = max(0, center - max_characters // 2)
    end = min(len(text), start + max_characters)
    if end - start < max_characters:
        start = max(0, end - max_characters)
    return text[start:end]


def select_candidate_source(
    pages: Sequence[CandidateSourcePage],
    schema: InsuranceSchema,
    field_ids: Sequence[str],
    *,
    max_pages: int = 18,
    max_characters: int = 75_000,
    max_pages_per_field: int | None = None,
    snippet_characters: int = 1_200,
    retriever: FieldCandidateRetriever | None = None,
) -> CandidateSourceSelection:
    """Scan all pages, then build bounded full-page and snippet context.

    The full scan happens before any page budget is applied. Pages outside the
    full-page budget remain represented by field-centered snippets, so a late
    source hit cannot silently become an extraction miss.
    """
    if max_pages < 1 or max_characters < 1_000:
        raise ValueError("M127_CANDIDATE_EXCERPT_LIMIT_INVALID")
    if snippet_characters < 100:
        raise ValueError("M131_CANDIDATE_SNIPPET_LIMIT_INVALID")
    located = locate_field_candidates(
        pages,
        schema,
        field_ids,
        max_pages_per_field=max_pages_per_field,
        retriever=retriever,
    )
    page_by_key = {(page.document_name, page.page_number): page for page in pages}
    source_order = {key: index for index, key in enumerate(page_by_key)}
    page_coverage: dict[tuple[str, int], set[str]] = {}
    scores: dict[tuple[str, int], int] = {}
    for field_id, candidates in located.items():
        for candidate in candidates:
            key = (candidate.document_name, candidate.page_number)
            page_coverage.setdefault(key, set()).add(field_id)
            scores[key] = max(scores.get(key, 0), candidate.score)
    uncovered = set(field_ids)
    ranked_keys: list[tuple[str, int]] = []
    remaining_keys = set(page_coverage)
    while uncovered and remaining_keys and len(ranked_keys) < max_pages:
        key = min(
            remaining_keys,
            key=lambda item: (
                -len(page_coverage[item] & uncovered),
                -scores[item],
                source_order[item],
            ),
        )
        if not page_coverage[key] & uncovered:
            break
        ranked_keys.append(key)
        uncovered -= page_coverage[key]
        remaining_keys.remove(key)

    for field_id in field_ids:
        profile = field_extraction_profile(field_id)
        if profile is None or not profile.preserve_document_diversity:
            continue
        seen_documents = {
            key[0] for key in ranked_keys if field_id in page_coverage.get(key, set())
        }
        for candidate in located.get(field_id, ()):
            if len(ranked_keys) >= max_pages:
                break
            key = (candidate.document_name, candidate.page_number)
            if candidate.document_name in seen_documents:
                continue
            if key not in ranked_keys:
                ranked_keys.append(key)
                remaining_keys.discard(key)
            seen_documents.add(candidate.document_name)

    anchor_keys = tuple(ranked_keys)
    for key in anchor_keys:
        if len(ranked_keys) >= max_pages:
            break
        relevant_profiles = tuple(
            profile
            for field_id in page_coverage.get(key, set())
            if (profile := field_extraction_profile(field_id)) is not None
        )
        radius = max((profile.neighbor_pages for profile in relevant_profiles), default=0)
        for distance in range(1, radius + 1):
            for page_number in (key[1] - distance, key[1] + distance):
                neighbor = (key[0], page_number)
                if neighbor not in page_by_key or neighbor in ranked_keys:
                    continue
                ranked_keys.append(neighbor)
                remaining_keys.discard(neighbor)
                if len(ranked_keys) >= max_pages:
                    break
            if len(ranked_keys) >= max_pages:
                break
    ranked_keys.extend(
        sorted(
            remaining_keys,
            key=lambda key: (-len(page_coverage[key]), -scores[key], source_order[key]),
        )[: max_pages - len(ranked_keys)]
    )
    if not ranked_keys:
        ranked_keys = list(page_by_key)[:max_pages]

    selected_keys = set(ranked_keys)
    omitted_candidates = [
        (candidate, (candidate.document_name, candidate.page_number))
        for candidates in located.values()
        for candidate in candidates
        if (candidate.document_name, candidate.page_number) not in selected_keys
    ]
    snippet_budget = min(
        max_characters // 3,
        snippet_characters * max(1, len(field_ids)),
    ) if omitted_candidates else 0
    full_page_budget = max_characters - snippet_budget
    index_rows = [
        {
            "field_id": field_id,
            "candidate_pages": [candidate.locator for candidate in candidates],
            "selected_full_pages": [
                candidate.locator
                for candidate in candidates
                if (candidate.document_name, candidate.page_number) in selected_keys
            ],
        }
        for field_id, candidates in located.items()
    ]
    parts = [
        "候选页索引（仅用于定位，不得作为 Evidence quote）："
        + json.dumps(index_rows, ensure_ascii=False, separators=(",", ":"))
    ]
    for key in ranked_keys:
        page = page_by_key[key]
        part = f"【文档：{page.document_name}｜页码：{page.page_number}】\n{page.text}"
        remaining = full_page_budget - len("\n\n".join(parts)) - 2
        if remaining <= 0:
            break
        parts.append(part[:remaining])

    # Add one compact snippet for every candidate page that was not admitted as
    # a full page. This is the LLM Wiki-style recall bridge: all source pages are
    # scanned, while the provider still receives a bounded request.
    snippet_keys: set[tuple[str, tuple[str, int]]] = set()
    snippet_characters_used = 0
    snippet_rows = sorted(
        omitted_candidates,
        key=lambda item: (
            -item[0].score,
            source_order[item[1]],
            item[0].field_id,
        ),
    )
    for candidate, key in snippet_rows:
        snippet_key = (candidate.field_id, key)
        if snippet_key in snippet_keys:
            continue
        remaining = min(
            max_characters - len("\n\n".join(parts)) - 2,
            snippet_budget - snippet_characters_used,
        )
        if remaining <= 0:
            break
        page = page_by_key[key]
        snippet = _candidate_snippet(
            page,
            candidate,
            max_characters=min(snippet_characters, remaining),
        )
        parts.append(
            f"【字段候选片段：{candidate.field_id}｜文档：{page.document_name}｜页码：{page.page_number}】\n"
            + snippet
        )
        snippet_characters_used += len(snippet) + len(
            f"【字段候选片段：{candidate.field_id}｜文档：{page.document_name}｜页码：{page.page_number}】\n"
        )
        snippet_keys.add(snippet_key)

    text = "\n\n".join(parts)
    coverage = {
        field_id: CandidateCoverage(
            field_id=field_id,
            scanned_page_count=len(pages),
            candidate_page_count=len(candidates),
            selected_page_count=sum(
                (candidate.document_name, candidate.page_number) in selected_keys
            for candidate in candidates
            ),
            snippet_page_count=sum(
                (candidate.field_id, (candidate.document_name, candidate.page_number))
                in snippet_keys
                for candidate in candidates
            ),
            candidate_locators=tuple(candidate.locator for candidate in candidates),
            selected_locators=tuple(
                candidate.locator
                for candidate in candidates
                if (candidate.document_name, candidate.page_number) in selected_keys
            ),
            candidate_reasons=tuple(
                f"{candidate.locator}:{','.join(candidate.reasons)}"
                for candidate in candidates
            ),
        )
        for field_id, candidates in located.items()
    }
    return CandidateSourceSelection(text=text, coverage=coverage)


def build_field_micro_batches(
    schema: InsuranceSchema,
    *,
    min_fields: int = 5,
    max_fields: int = 8,
) -> tuple[ExtractionBatch, ...]:
    """Build ordered field micro-batches for a capacity-aware provider plan."""
    if min_fields < 1 or max_fields < min_fields:
        raise ValueError("M131_MICROBATCH_LIMIT_INVALID")
    fields = tuple(
        field for field in schema.fields if field.formation_modes != ("外部映射",)
    )
    chunks: list[list[FieldDefinition]] = [
        list(fields[index : index + max_fields])
        for index in range(0, len(fields), max_fields)
    ]
    if len(chunks) > 1:
        while len(chunks[-1]) < min_fields and len(chunks[-2]) > min_fields:
            chunks[-1].insert(0, chunks[-2].pop())
    batches: list[ExtractionBatch] = []
    for index, chunk in enumerate(chunks, 1):
        batches.append(
            ExtractionBatch(
                index=index,
                category_ids=tuple(dict.fromkeys(field.category_id for field in chunk)),
                field_ids=tuple(field.field_id for field in chunk),
                field_ordinals=tuple(field.ordinal for field in chunk),
            )
        )
    return tuple(batches)


def build_category_batches(
    schema: InsuranceSchema,
    *,
    batch_count: int = 3,
) -> tuple[ExtractionBatch, ...]:
    target_fields = tuple(
        field for field in schema.fields if field.formation_modes != ("外部映射",)
    )
    category_ids = tuple(dict.fromkeys(field.category_id for field in target_fields))
    if batch_count < 1 or batch_count > len(category_ids):
        raise ValueError("M127_CATEGORY_BATCH_COUNT_INVALID")
    fields_by_category = {
        category_id: tuple(
            field for field in target_fields if field.category_id == category_id
        )
        for category_id in category_ids
    }
    best: tuple[tuple[int, int, tuple[int, ...]], tuple[tuple[str, ...], ...]] | None = None
    for split_points in combinations(range(1, len(category_ids)), batch_count - 1):
        boundaries = (0, *split_points, len(category_ids))
        groups = tuple(
            category_ids[boundaries[index] : boundaries[index + 1]]
            for index in range(batch_count)
        )
        sizes = tuple(
            sum(len(fields_by_category[category_id]) for category_id in group)
            for group in groups
        )
        objective = (max(sizes), max(sizes) - min(sizes), split_points)
        if best is None or objective < best[0]:
            best = (objective, groups)
    assert best is not None
    batches: list[ExtractionBatch] = []
    for index, group in enumerate(best[1], 1):
        fields = tuple(
            field
            for category_id in group
            for field in fields_by_category[category_id]
        )
        batches.append(
            ExtractionBatch(
                index=index,
                category_ids=group,
                field_ids=tuple(field.field_id for field in fields),
                field_ordinals=tuple(field.ordinal for field in fields),
            )
        )
    return tuple(batches)


_METADATA_FIELD_MAP: Mapping[str, str] = {
    "product_code": "planCode",
    "product_short_name": "productShortName",
    "product_name": "clauseName",
    "sales_start_date": "startDate",
    "product_type": "planPlanType",
    "sales_channels": "planSalesChannel",
    "sales_status": "planSalesStatus",
}

_METADATA_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "product_short_name": ("productShortName", "shortName", "险种简称", "产品简称"),
}
_SHORT_NAME_PATTERN = re.compile(
    r"(?:险种简称|产品简称)\s*(?:为|是)?\s*[:：]?\s*"
    r"(?P<value>[^\s,，。；;|｜]{1,80})"
)


def _metadata_value(field_id: str, raw: object) -> CandidateValue | None:
    if field_id == "sales_channels" and isinstance(raw, str):
        values = tuple(value.strip() for value in re.split(r"[、,，;；/]+", raw) if value.strip())
        return values or None
    if isinstance(raw, (str, int, float, bool)) and not isinstance(raw, str) or (
        isinstance(raw, str) and raw.strip()
    ):
        return raw
    return None


def _metadata_key(field_id: str, metadata: Mapping[str, object]) -> str | None:
    keys = _METADATA_FIELD_ALIASES.get(field_id)
    if keys is None:
        mapped = _METADATA_FIELD_MAP.get(field_id)
        keys = (mapped,) if mapped is not None else ()
    return next((key for key in keys if key in metadata), None)


def _source_short_name(
    pages: Sequence[CandidateSourcePage],
) -> tuple[str, str, str] | None:
    for page in pages:
        match = _SHORT_NAME_PATTERN.search(page.text)
        if match is None:
            continue
        value = match.group("value").strip()
        if not value:
            continue
        return (
            value,
            f"pdf:{page.document_name}#page={page.page_number}",
            match.group(0).strip(),
        )
    return None


class MetadataMappingPlugin:
    plugin_id = "v5-authoritative-product-metadata-v1"

    def __init__(
        self,
        *,
        metadata: Mapping[str, object],
        source_pages: Sequence[CandidateSourcePage] = (),
    ) -> None:
        self._metadata = dict(metadata)
        self._source_pages = tuple(source_pages)

    def extract(self, request: IngestRequest, schema: InsuranceSchema) -> PluginResult:
        rows: list[PluginFieldResult] = []
        for field in schema.fields:
            metadata_key = _metadata_key(field.field_id, self._metadata)
            value = (
                _metadata_value(field.field_id, self._metadata.get(metadata_key))
                if metadata_key is not None and metadata_key in self._metadata
                else None
            )
            source_short_name = (
                _source_short_name(self._source_pages)
                if field.field_id == "product_short_name" and value is None
                else None
            )
            if source_short_name is not None:
                value, locator, quote = source_short_name
                rows.append(
                    PluginFieldResult(
                        ordinal=field.ordinal,
                        field_id=field.field_id,
                        state="present",
                        value=value,
                        evidence=(
                            CandidateEvidence(
                                source_revision_id=request.source_revision_id,
                                locator=locator,
                                quote=quote,
                                verification_status="VERIFIED",
                            ),
                        ),
                    )
                )
                continue
            if value is None:
                rows.append(
                    PluginFieldResult(
                        ordinal=field.ordinal,
                        field_id=field.field_id,
                        state="unknown",
                    )
                )
                continue
            assert metadata_key is not None
            value = normalize_field_value(field, value)
            raw = self._metadata[metadata_key]
            quote = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            rows.append(
                PluginFieldResult(
                    ordinal=field.ordinal,
                    field_id=field.field_id,
                    state="present",
                    value=value,
                    evidence=(
                        CandidateEvidence(
                            source_revision_id=request.source_revision_id,
                            locator=f"json:product_meta.json#/{metadata_key}",
                            quote=quote,
                            verification_status="VERIFIED",
                        ),
                    ),
                )
            )
        return PluginResult(
            plugin_id=self.plugin_id,
            source_revision_id=request.source_revision_id,
            insurance_class=schema.insurance_class,
            product_id=request.product_id,
            product_version_id=request.product_version_id,
            schema_id=schema.schema_id,
            fields=tuple(rows),
        )


__all__ = [
    "AllPageFieldCandidateRetriever",
    "CandidateCoverage",
    "CandidateSourceSelection",
    "CandidateSourcePage",
    "ExtractionBatch",
    "FieldCandidate",
    "FieldCandidateRetriever",
    "MetadataMappingPlugin",
    "SemanticSimilarityPort",
    "build_candidate_source_text",
    "build_full_material_field_source_text",
    "build_coverage_summary_source_text",
    "build_category_batches",
    "build_field_micro_batches",
    "distributed_page_excerpt",
    "locate_field_candidates",
    "select_candidate_source",
]
