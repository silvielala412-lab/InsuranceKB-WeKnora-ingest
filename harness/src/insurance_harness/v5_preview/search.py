from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import CandidateValue, V5CandidatePreview
from .llm_plugin import LlmPluginError
from .trial_contracts import V5ProviderTrialRun


class V5SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("V5_SEARCH_QUERY_REQUIRED")
        return value


class V5SearchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    locator: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=1, max_length=2000)
    verification_status: Literal[
        "VERIFIED", "NORMALIZED_MATCH", "UNRESOLVED", "AMBIGUOUS"
    ]


class V5SearchMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    product_id: str = Field(min_length=1)
    product_version_id: str = Field(min_length=1)
    product_display_name: str = Field(min_length=1)
    insurance_class: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    field_display_name: str = Field(min_length=1)
    category_display_name: str = Field(min_length=1)
    value: CandidateValue
    score: int = Field(ge=1)
    evidence: tuple[V5SearchEvidence, ...] = ()


class V5SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    contract: Literal["insurance-v5-search-response.v1"]
    query: str = Field(min_length=1)
    provider: Literal["local", "bailian"]
    model: str | None
    answer: str = Field(min_length=1)
    matches: tuple[V5SearchMatch, ...]
    provider_error: str | None = None


class SearchCompletion(Protocol):
    model: str

    def complete(self, *, system: str, user: str) -> str: ...


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")
_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "产品简称": ("产品简称", "险种简称"),
    "产品名称": ("产品名称", "险种名称"),
    "保险责任": ("保险责任", "保障责任", "保什么"),
}


def _value_text(value: CandidateValue) -> str:
    if isinstance(value, tuple):
        return "、".join(value)
    return str(value)


def _query_tokens(query: str) -> tuple[str, ...]:
    terms = _QUERY_ALIASES.get(query, (query,))
    tokens = tuple(
        token.casefold()
        for term in terms
        for token in _TOKEN_RE.findall(term)
    )
    return tokens or (query.casefold(),)


def _score_match(preview: V5CandidatePreview, field: object, query: str, tokens: Sequence[str]) -> int:
    # The caller passes a CandidateField, but keeping this helper independent of the
    # concrete pydantic class makes it easier to exercise with frozen fixtures.
    field_value = getattr(field, "value")
    value_text = _value_text(field_value).casefold()
    field_name = str(getattr(field, "display_name")).casefold()
    field_id = str(getattr(field, "field_id")).casefold()
    category = str(getattr(field, "category_display_name")).casefold()
    evidence_text = " ".join(item.quote for item in getattr(field, "evidence")).casefold()
    product_text = " ".join(
        (preview.product_id, preview.product_display_name, preview.insurance_class),
    ).casefold()
    haystack = " ".join((field_name, field_id, category, value_text, evidence_text, product_text))
    normalized_query = query.casefold()
    if normalized_query not in haystack and not any(token in haystack for token in tokens):
        return 0
    score = 0
    if normalized_query in haystack:
        score += 8
    for token in tokens:
        if token in field_name:
            score += 5
        elif token in field_id or token in category:
            score += 4
        elif token in product_text:
            score += 3
        elif token in value_text:
            score += 3
        elif token in evidence_text:
            score += 1
    return score


def build_v5_search_matches(
    provider_run: V5ProviderTrialRun,
    query: str,
    limit: int,
) -> tuple[V5SearchMatch, ...]:
    tokens = _query_tokens(query)
    ranked: list[tuple[int, int, int, V5SearchMatch]] = []
    for product_ordinal, product in enumerate(provider_run.products):
        preview = product.preview
        if preview is None:
            continue
        for field in preview.fields:
            if field.state != "present" or field.value is None:
                continue
            score = _score_match(preview, field, query, tokens)
            if score <= 0:
                continue
            ranked.append(
                (
                    score,
                    product_ordinal,
                    field.ordinal,
                    V5SearchMatch(
                        product_id=preview.product_id,
                        product_version_id=preview.product_version_id,
                        product_display_name=preview.product_display_name,
                        insurance_class=preview.insurance_class,
                        field_id=field.field_id,
                        field_display_name=field.display_name,
                        category_display_name=field.category_display_name,
                        value=field.value,
                        score=score,
                        evidence=tuple(
                            V5SearchEvidence(
                                locator=item.locator,
                                quote=item.quote,
                                verification_status=item.verification_status,
                            )
                            for item in field.evidence
                        ),
                    ),
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return tuple(item[3] for item in ranked[:limit])


def _local_answer(query: str, matches: Sequence[V5SearchMatch]) -> str:
    if not matches:
        return f'当前已加载的产品结果中未检索到与“{query}”直接匹配的字段。'
    products = len({match.product_id for match in matches})
    return f'检索到 {len(matches)} 条相关字段，涉及 {products} 款产品；结果按字段、产品和 Evidence 的匹配度排序。'


def _llm_answer(
    completion: SearchCompletion,
    query: str,
    matches: Sequence[V5SearchMatch],
) -> str:
    context = [
        {
            "index": index,
            "product": match.product_display_name,
            "insurance_class": match.insurance_class,
            "field": match.field_display_name,
            "field_id": match.field_id,
            "value": match.value,
            "evidence": [item.quote for item in match.evidence[:3]],
        }
        for index, match in enumerate(matches)
    ]
    raw = completion.complete(
        system=(
            "你是保险产品知识检索助手。只使用给定的已抽取字段和 Evidence 回答用户问题，"
            "不得补充材料之外的事实。只输出 JSON 对象，结构为 "
            '{"answer":"简洁回答","match_indices":[0]}。'
        ),
        user=json.dumps({"query": query, "matches": context}, ensure_ascii=False),
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID")
    answer = payload["answer"].strip()
    indices = payload.get("match_indices", [])
    if not answer or not isinstance(indices, list) or not all(
        isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(matches)
        for index in indices
    ):
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID")
    return answer


def search_provider_run(
    provider_run: V5ProviderTrialRun,
    request: V5SearchRequest,
    *,
    completion: SearchCompletion | None = None,
) -> V5SearchResponse:
    matches = build_v5_search_matches(provider_run, request.query, request.limit)
    answer = _local_answer(request.query, matches)
    provider: Literal["local", "bailian"] = "local"
    model: str | None = None
    provider_error: str | None = None
    if completion is not None and matches:
        try:
            answer = _llm_answer(completion, request.query, matches)
            provider = "bailian"
            model = completion.model
        except (LlmPluginError, ValueError, httpx.HTTPError):
            provider_error = "V5_SEARCH_PROVIDER_FAILED"
    return V5SearchResponse(
        contract="insurance-v5-search-response.v1",
        query=request.query,
        provider=provider,
        model=model,
        answer=answer,
        matches=matches,
        provider_error=provider_error,
    )


__all__ = [
    "V5SearchRequest",
    "V5SearchResponse",
    "V5SearchMatch",
    "build_v5_search_matches",
    "search_provider_run",
]
