"""Deterministic completion for facts already reviewed in exact source material.

The profiles in this module are bound to source-manifest hashes.  They may fill
an unknown candidate field, but they never replace a provider value and never
grant serving or publication authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from .catalog import load_v5_catalog
from .contracts import (
    CandidateEvidence,
    CandidateValue,
    PluginFieldResult,
    V5CandidatePreview,
)
from .ingest import preview_digest
from .source_evidence import SourcePage, classify_evidence
from .value_constraints import normalize_field_value


CompletionKind = Literal["literal_missing", "derived_or_synthesized"]


@dataclass(frozen=True, slots=True)
class LiteralEvidenceSelector:
    document_name: str
    page_number: int
    quote: str


@dataclass(frozen=True, slots=True)
class SourceSupportedFieldRule:
    field_id: str
    value: CandidateValue
    kind: CompletionKind
    supporting_field_ids: tuple[str, ...] = ()
    literal_evidence: tuple[LiteralEvidenceSelector, ...] = ()
    max_supporting_evidence: int = 8


@dataclass(frozen=True, slots=True)
class SourceSupportedProfile:
    product_id: str
    source_manifest_sha256: str
    fields: tuple[SourceSupportedFieldRule, ...]


@dataclass(frozen=True, slots=True)
class SourceSupportedCompletionReceipt:
    product_id: str
    source_manifest_sha256: str
    field_id: str
    kind: CompletionKind
    before_state: Literal["unknown"]
    after_state: Literal["present"]
    supporting_field_ids: tuple[str, ...]
    evidence_locators: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _rule(
    field_id: str,
    value: CandidateValue,
    *,
    supporting: tuple[str, ...] = (),
    literal: tuple[LiteralEvidenceSelector, ...] = (),
    kind: CompletionKind = "derived_or_synthesized",
) -> SourceSupportedFieldRule:
    return SourceSupportedFieldRule(
        field_id=field_id,
        value=value,
        kind=kind,
        supporting_field_ids=supporting,
        literal_evidence=literal,
    )


SOURCE_SUPPORTED_PROFILES: tuple[SourceSupportedProfile, ...] = (
    SourceSupportedProfile(
        product_id="596",
        source_manifest_sha256=(
            "fbd785f1ce35ec8015ddbfc93cbdee20ffde362e480d25a5ccee3d7da1e26824"
        ),
        fields=(
            _rule(
                "direct_billing_and_advance_payment_rules",
                (
                    "一码垫付：入住二级及以上基本医疗保险定点医院普通部，经专业服务人员判断符合保险责任后，可在给付限额内对合理且必要的医疗费用申请垫付。",
                    "一码直付：服务有效期和保额范围内，等待期后因疾病在二级及以上基本医疗保险定点医院国际部或特需部就医，可在一般医疗保险金给付限额内申请直付。",
                    "结算限制：若最终理赔款小于垫付或直付金额，客户须归还差额；如不予理赔，客户须全额归还垫付或直付金额。",
                ),
                kind="literal_missing",
                literal=(
                    LiteralEvidenceSelector(
                        "安有医健康服务手册（尊享版）.pdf",
                        19,
                        "客户入住二级及以上基本医疗保险定点医院普通部，经专业服务人员判断符合保险责任后，可申请一码\n垫付，对于所实际支出的合理且必要的医疗费用，我们将在给付限额内给予垫付",
                    ),
                    LiteralEvidenceSelector(
                        "安有医健康服务手册（尊享版）.pdf",
                        20,
                        "服务使用有效期限内和保额范围内，客户经过等待期后因疾病在二级及以上基本医疗保险定点医院国际\n/特需部就医时，发生保险责任范围内的住院医疗费用，可提供一码直付服务，我们在一般医疗保险金\n的给付限额内进行直付服务",
                    ),
                    LiteralEvidenceSelector(
                        "安有医健康服务手册（尊享版）.pdf",
                        44,
                        "如理赔款金额小于医疗直付金额，服务商将获\n得保司全部理赔款，且客户应向服务商归还差\n额部分；如保司不予理赔，客户应向服务商全\n额归还医疗直付金额",
                    ),
                ),
            ),
        ),
    ),
    SourceSupportedProfile(
        product_id="5003",
        source_manifest_sha256=(
            "7fc84c9a9312e85940209ccd1fa4474fd98c15c49035d7c0fa5a1af4a42113b5"
        ),
        fields=(
            _rule(
                "total_disability_coverage_flag",
                "否",
                supporting=("coverage_responsibilities",),
            ),
            _rule(
                "accidental_death_coverage_flag",
                "可保意外身故",
                supporting=("coverage_responsibilities", "exclusions"),
            ),
            _rule(
                "disease_death_coverage_flag",
                "可保疾病身故",
                supporting=("coverage_responsibilities", "exclusions"),
            ),
        ),
    ),
    SourceSupportedProfile(
        product_id="1813",
        source_manifest_sha256=(
            "90de63cab338361897a6208cad856c9fffe704375c44ee14e33a973ec12eff81"
        ),
        fields=(
            _rule("policy_role", "主险", supporting=("product_bundle_rules",)),
            _rule("coverage_term_category", "长期", supporting=("coverage_period",)),
            _rule(
                "covered_risk_categories",
                ("身故风险", "重疾风险"),
                supporting=("coverage_responsibilities",),
            ),
            _rule(
                "age_segment_tags",
                ("儿童（0-17岁）", "成人（18-59岁）", "老年人（60岁及以上）"),
                supporting=("entry_age_range",),
            ),
            _rule(
                "maturity_benefit_flag",
                "否",
                supporting=("coverage_responsibilities",),
            ),
            _rule(
                "disease_count_by_severity",
                (
                    "重大疾病120种",
                    "轻度疾病40种（仅保险计划二）",
                    "中症疾病20种（仅保险计划二）",
                ),
                supporting=(
                    "coverage_responsibilities",
                    "covered_mild_specified_diseases",
                    "covered_moderate_specified_diseases",
                ),
            ),
            _rule(
                "special_coverage_and_exclusion_tags",
                ("既往症除外", "加费承保（五类职业EM50、六类职业EM100）"),
                supporting=("exclusions", "product_bundle_rules"),
            ),
        ),
    ),
    SourceSupportedProfile(
        product_id="1837",
        source_manifest_sha256=(
            "216b968732ad66b903e943bb12867c270614a61bf84dc7e534c6d8a3d8ef1ca0"
        ),
        fields=(
            _rule("policy_role", "主险", supporting=("product_bundle_rules",)),
            _rule(
                "marketing_tagline",
                "身故保障会长大 守护挚爱家人",
                kind="literal_missing",
                literal=(
                    LiteralEvidenceSelector(
                        "产品说明书.pdf",
                        1,
                        "身故保障会长大 守护挚爱家人\n身故保障持续增长至终身，保障长久相伴，延续对家人的关爱。",
                    ),
                ),
            ),
            _rule(
                "covered_risk_categories",
                ("身故风险",),
                supporting=("coverage_responsibilities",),
            ),
            _rule(
                "age_segment_tags",
                ("儿童（0-17岁）", "成人（18-59岁）", "老年人（60岁及以上）"),
                supporting=("entry_age_range",),
            ),
            _rule(
                "sum_assured_pattern",
                "增额",
                supporting=("sum_assured_growth_rules",),
            ),
            _rule(
                "total_disability_coverage_flag",
                "否",
                supporting=("coverage_responsibilities",),
            ),
            _rule(
                "accidental_death_coverage_flag",
                "可保意外身故",
                supporting=("coverage_responsibilities", "exclusions"),
            ),
            _rule(
                "disease_death_coverage_flag",
                "可保疾病身故",
                supporting=("coverage_responsibilities", "exclusions"),
            ),
            _rule(
                "coverage_increase_rules",
                "我们不接受增加基本保险金额的申请。",
                kind="literal_missing",
                literal=(
                    LiteralEvidenceSelector(
                        "保险条款.pdf",
                        2,
                        "我们不接受增加基本保险金额的申请。",
                    ),
                ),
            ),
        ),
    ),
    SourceSupportedProfile(
        product_id="1824",
        source_manifest_sha256=(
            "017ab28cead808c5046f8b61da3b864b4fd81997aa970281f03e2887b15133ba"
        ),
        fields=(
            _rule(
                "target_customer_profile",
                "适合有终身身故保障及长期现金价值需求，并符合0周岁（须出生满28日）至75周岁投保年龄及保险公司承保条件的人群。",
                supporting=(
                    "entry_age_range",
                    "coverage_period",
                    "coverage_responsibilities",
                    "cash_value_rules",
                ),
            ),
            _rule(
                "marketing_tagline",
                "现价确定增长 无惧市场波动",
                kind="literal_missing",
                literal=(
                    LiteralEvidenceSelector(
                        "产品说明书.pdf",
                        1,
                        "现价确定增长 无惧市场波动\n交费期满一定年度后，现价以约 2%增长至终身。",
                    ),
                ),
            ),
        ),
    ),
)

_PROFILES_BY_MANIFEST: Mapping[str, SourceSupportedProfile] = {
    profile.source_manifest_sha256: profile for profile in SOURCE_SUPPORTED_PROFILES
}


def _replace_preview_fields(
    preview: V5CandidatePreview,
    updates: Mapping[str, PluginFieldResult],
) -> V5CandidatePreview:
    fields = tuple(
        field.model_copy(
            update={
                "state": update.state,
                "value": update.value,
                "evidence": update.evidence,
            }
        )
        if (update := updates.get(field.field_id)) is not None
        else field
        for field in preview.fields
    )
    payload = preview.model_dump(mode="json")
    payload.pop("preview_sha256")
    payload["fields"] = [field.model_dump(mode="json") for field in fields]
    return preview.model_copy(
        update={"fields": fields, "preview_sha256": preview_digest(payload)}
    )


def _supporting_evidence(
    *,
    preview: V5CandidatePreview,
    rule: SourceSupportedFieldRule,
) -> tuple[CandidateEvidence, ...]:
    current = {field.field_id: field for field in preview.fields}
    evidence: list[CandidateEvidence] = []
    for field_id in rule.supporting_field_ids:
        field = current.get(field_id)
        if field is None or field.state != "present" or not field.evidence:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_DEPENDENCY_MISSING:{rule.field_id}:{field_id}"
            )
        verified = tuple(
            item
            for item in field.evidence
            if item.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}
            and item.source_revision_id == preview.source_revision_id
        )
        if not verified:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_DEPENDENCY_UNVERIFIED:{rule.field_id}:{field_id}"
            )
        evidence.extend(verified)
    return tuple(dict.fromkeys(evidence))[: rule.max_supporting_evidence]


def _literal_evidence(
    *,
    preview: V5CandidatePreview,
    pages: Sequence[SourcePage],
    rule: SourceSupportedFieldRule,
) -> tuple[CandidateEvidence, ...]:
    evidence: list[CandidateEvidence] = []
    for selector in rule.literal_evidence:
        locator = f"pdf:{selector.document_name}#page={selector.page_number}"
        resolution = classify_evidence(pages, selector.quote, locator)
        if resolution.verification_status not in {"VERIFIED", "NORMALIZED_MATCH"}:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_EVIDENCE_UNVERIFIED:{rule.field_id}:{locator}"
            )
        evidence.append(
            CandidateEvidence(
                source_revision_id=preview.source_revision_id,
                locator=resolution.locator,
                quote=selector.quote,
                verification_status=resolution.verification_status,
            )
        )
    return tuple(evidence)


def _complete_profile(
    *,
    preview: V5CandidatePreview,
    source_manifest_sha256: str,
    pages: Sequence[SourcePage],
    profile: SourceSupportedProfile,
) -> tuple[V5CandidatePreview, tuple[SourceSupportedCompletionReceipt, ...]]:
    if source_manifest_sha256 != profile.source_manifest_sha256:
        raise ValueError("SOURCE_SUPPORTED_COMPLETION_MANIFEST_MISMATCH")
    if preview.product_id != profile.product_id:
        raise ValueError("SOURCE_SUPPORTED_COMPLETION_PRODUCT_MISMATCH")
    if preview.source_revision_id != f"v5-source-{source_manifest_sha256}":
        raise ValueError("SOURCE_SUPPORTED_COMPLETION_REVISION_MISMATCH")
    if len({rule.field_id for rule in profile.fields}) != len(profile.fields):
        raise ValueError("SOURCE_SUPPORTED_COMPLETION_DUPLICATE_FIELD")

    schema = load_v5_catalog().schema_for(preview.insurance_class)
    if schema.schema_id != preview.schema_id:
        raise ValueError("SOURCE_SUPPORTED_COMPLETION_SCHEMA_MISMATCH")
    definitions = {field.field_id: field for field in schema.fields}
    current = {field.field_id: field for field in preview.fields}
    updates: dict[str, PluginFieldResult] = {}
    receipts: list[SourceSupportedCompletionReceipt] = []
    for rule in profile.fields:
        before = current.get(rule.field_id)
        definition = definitions.get(rule.field_id)
        if before is None or definition is None or before.ordinal != definition.ordinal:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_FIELD_IDENTITY_MISMATCH:{rule.field_id}"
            )
        if before.state != "unknown":
            continue
        evidence = (
            *_supporting_evidence(preview=preview, rule=rule),
            *_literal_evidence(preview=preview, pages=pages, rule=rule),
        )
        evidence = tuple(dict.fromkeys(evidence))
        if not evidence:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_EVIDENCE_MISSING:{rule.field_id}"
            )
        value = normalize_field_value(definition, rule.value)
        if value is None:
            raise ValueError(
                f"SOURCE_SUPPORTED_COMPLETION_VALUE_INVALID:{rule.field_id}"
            )
        updates[rule.field_id] = PluginFieldResult(
            ordinal=before.ordinal,
            field_id=rule.field_id,
            state="present",
            value=value,
            evidence=evidence,
        )
        receipts.append(
            SourceSupportedCompletionReceipt(
                product_id=preview.product_id,
                source_manifest_sha256=source_manifest_sha256,
                field_id=rule.field_id,
                kind=rule.kind,
                before_state="unknown",
                after_state="present",
                supporting_field_ids=rule.supporting_field_ids,
                evidence_locators=tuple(item.locator for item in evidence),
            )
        )
    return _replace_preview_fields(preview, updates), tuple(receipts)


def complete_source_supported_fields(
    *,
    preview: V5CandidatePreview,
    source_manifest_sha256: str,
    pages: Sequence[SourcePage],
) -> tuple[V5CandidatePreview, tuple[SourceSupportedCompletionReceipt, ...]]:
    """Fill reviewed source-supported gaps for one exact material manifest."""
    profile = _PROFILES_BY_MANIFEST.get(source_manifest_sha256)
    if profile is None:
        return preview, ()
    return _complete_profile(
        preview=preview,
        source_manifest_sha256=source_manifest_sha256,
        pages=pages,
        profile=profile,
    )


def registered_completion_field_count() -> int:
    return sum(len(profile.fields) for profile in SOURCE_SUPPORTED_PROFILES)


__all__ = [
    "LiteralEvidenceSelector",
    "SOURCE_SUPPORTED_PROFILES",
    "SourceSupportedCompletionReceipt",
    "SourceSupportedFieldRule",
    "SourceSupportedProfile",
    "complete_source_supported_fields",
    "registered_completion_field_count",
]
