from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import CandidateValue, FieldDefinition


class ValueConstraintKind(StrEnum):
    FREE_TEXT = "free_text"
    SINGLE = "single_choice"
    MULTI = "multi_choice"


@dataclass(frozen=True, slots=True)
class ValueConstraint:
    kind: ValueConstraintKind
    allowed_values: tuple[str, ...] = ()
    multi_select: bool = False
    nullable: bool = False
    allow_other: bool = False

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "allowed_values": list(self.allowed_values),
            "multi_select": self.multi_select,
            "nullable": self.nullable,
            "allow_other": self.allow_other,
        }


_PARENTHETICAL = re.compile(r"[（(]([^（）()]*)[）)]")
_QUOTED_OPTIONS = re.compile(r"[“\"]([^”\"]+)[”\"]")
_SPLIT_OPTIONS = re.compile(r"[、,，;；]+")
_YES_NO_NEGATIVE = ("不可", "不能", "不可以", "不支持", "不保证", "不允许", "不得", "无")
_YES_NO_POSITIVE = ("可以", "可", "支持", "保证", "允许", "能够")


def _clean_guidance(guidance: str) -> tuple[str, bool, bool, bool]:
    text = guidance.strip()
    nullable = "可为空" in text or "可以为空" in text
    multi = "多选" in text
    open_ended = (
        bool(re.search(r"等\s*(?:[（(]|$)", text))
        or "按实际产品" in text
        or "包括但不限于" in text
    )
    quoted = _QUOTED_OPTIONS.search(text)
    if quoted is not None:
        text = quoted.group(1)
    text = text.replace("可选值", "").replace("取值为", "")
    def remove_qualifier(match: re.Match[str]) -> str:
        inner = match.group(1)
        return "" if any(
            marker in inner for marker in ("多选", "可为空", "标签化", "按实际产品")
        ) else match.group(0)

    text = _PARENTHETICAL.sub(remove_qualifier, text)
    text = re.sub(r"\s*等\s*$", "", text).strip()
    return text, multi, nullable, open_ended


def parse_value_guidance(guidance: str | None) -> ValueConstraint:
    """Compile the workbook's human guidance without guessing missing options."""
    if guidance is None or not guidance.strip():
        return ValueConstraint(kind=ValueConstraintKind.FREE_TEXT)
    text, multi, nullable, open_ended = _clean_guidance(guidance)
    options = tuple(
        option.strip()
        for option in _SPLIT_OPTIONS.split(text)
        if option.strip()
    )
    # Descriptive text with no stable option separator remains free text.
    if len(options) < 2:
        return ValueConstraint(
            kind=ValueConstraintKind.FREE_TEXT,
            nullable=nullable,
        )
    unique_options = tuple(dict.fromkeys(options))
    allow_other = "其他" in unique_options or open_ended
    return ValueConstraint(
        kind=ValueConstraintKind.MULTI if multi else ValueConstraintKind.SINGLE,
        allowed_values=unique_options,
        multi_select=multi,
        nullable=nullable,
        allow_other=allow_other,
    )


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).strip("。；;，,、")


def _option_key(value: str) -> str:
    # Insurance source text commonly uses 交/缴 interchangeably for payment
    # frequency; compare that harmless orthographic variant only.
    return _compact(value).replace("交", "缴")


def _allowed_hit(value: str, allowed_values: tuple[str, ...]) -> str | None:
    key = _option_key(value)
    return next(
        (option for option in allowed_values if _option_key(option) == key),
        None,
    )


def _single_normalize(value: str, constraint: ValueConstraint) -> str:
    raw = _compact(value)
    exact = _allowed_hit(raw, constraint.allowed_values)
    if exact is not None:
        return exact
    exact_hits = tuple(option for option in constraint.allowed_values if option in raw)
    if len(exact_hits) == 1 and len(raw) <= max(80, len(exact_hits[0]) * 4):
        return exact_hits[0]
    if set(constraint.allowed_values) >= {"是", "否"}:
        has_negative = any(token in raw for token in _YES_NO_NEGATIVE)
        has_positive = any(token in raw for token in _YES_NO_POSITIVE)
        if has_negative and not has_positive:
            return "否"
        if has_positive and not has_negative:
            return "是"
    # Product-specific options such as "支持满期给付、否" use the same
    # conservative polarity rule while retaining ambiguous prose verbatim.
    negative = next((option for option in constraint.allowed_values if option == "否"), None)
    if negative is not None and any(token in raw for token in _YES_NO_NEGATIVE):
        positive_hits = tuple(
            option
            for option in constraint.allowed_values
            if option != negative and option in raw
        )
        if not positive_hits:
            return negative
    return value


def _multi_normalize(value: object, constraint: ValueConstraint) -> CandidateValue:
    if isinstance(value, (tuple, list)):
        raw_items = tuple(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, str):
        raw_items = tuple(
            item.strip()
            for item in _SPLIT_OPTIONS.split(value)
            if item.strip()
        )
        if not raw_items:
            return value
    else:
        return value  # type: ignore[return-value]

    normalized: list[str] = []
    ambiguous: list[str] = []
    for item in raw_items:
        compact = _compact(item)
        exact = _allowed_hit(compact, constraint.allowed_values)
        if exact is not None:
            normalized.append(exact)
            continue
        if constraint.allow_other:
            ambiguous.append(item)
            continue
        hits = tuple(option for option in constraint.allowed_values if option in compact)
        if len(hits) == 1 and len(compact) <= max(80, len(hits[0]) * 4):
            normalized.append(hits[0])
        else:
            ambiguous.append(item)
    if ambiguous:
        return raw_items
    order = {option: index for index, option in enumerate(constraint.allowed_values)}
    return tuple(sorted(set(normalized), key=order.__getitem__))


def normalize_field_value(
    definition: FieldDefinition,
    value: CandidateValue | list[object] | None,
) -> CandidateValue | None:
    constraint = parse_value_guidance(definition.value_guidance)
    if value is None or constraint.kind == ValueConstraintKind.FREE_TEXT:
        return value
    if constraint.kind == ValueConstraintKind.MULTI:
        return _multi_normalize(value, constraint)
    if isinstance(value, (tuple, list)):
        return tuple(
            _single_normalize(str(item), constraint)
            for item in value
            if str(item).strip()
        )
    if isinstance(value, str):
        return _single_normalize(value, constraint)
    return value


__all__ = [
    "ValueConstraint",
    "ValueConstraintKind",
    "normalize_field_value",
    "parse_value_guidance",
]
