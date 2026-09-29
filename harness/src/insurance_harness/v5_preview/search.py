from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
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

    def complete_stream(
        self,
        *,
        system: str,
        user: str,
        on_content_delta: Callable[[str], None],
    ) -> str: ...


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")
_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "产品简称": ("产品简称", "险种简称"),
    "产品名称": ("产品名称", "险种名称"),
    "保险责任": ("保险责任", "保障责任", "保什么"),
    "等待期": ("等待期", "等待时间"),
    "投保范围": ("投保范围", "投保年龄", "可投保职业", "职业限制"),
    "投保年龄": ("投保年龄", "年龄范围"),
    "可投保职业": ("可投保职业", "投保职业", "职业限制"),
    "宽限期": ("宽限期", "缴费宽限"),
    "外购药/特药责任": ("外购药", "特药责任", "外购药/特药责任"),
    "销售状态": ("销售状态", "在售", "在售状态", "停售", "停止销售"),
}

# Search results remain useful to the UI, while the provider receives a much
# smaller evidence-backed context. These are deliberately independent limits:
# a user can still inspect all returned matches without making the model parse
# every long field value and every product metadata row.
_LLM_CONTEXT_MATCH_LIMIT = 20
_LLM_CONTEXT_MAX_PER_PRODUCT = 3
_LLM_CONTEXT_VALUE_CHARS = 600
_LLM_CONTEXT_EVIDENCE_CHARS = 220
_LLM_CONTEXT_MAX_EVIDENCE = 2
_PRODUCT_COUNT_QUERY_RE = re.compile(
    r"(?:\d+|[一二三四五六七八九十百千万两]+)款产品",
)


def _value_text(value: CandidateValue) -> str:
    if isinstance(value, tuple):
        return "、".join(value)
    return str(value)


def _query_tokens(
    query: str,
    provider_run: V5ProviderTrialRun | None = None,
) -> tuple[str, ...]:
    folded_query = query.casefold()
    terms = list(_QUERY_ALIASES.get(query, (query,)))
    # Natural questions usually contain a field label inside a longer sentence
    # (for example, "哪些产品有等待期？"). Include matching aliases instead of
    # treating the whole sentence as one opaque token.
    for aliases in _QUERY_ALIASES.values():
        if any(alias.casefold() in folded_query for alias in aliases):
            terms.extend(aliases)
    tokens = list(
        token.casefold()
        for term in terms
        for token in _TOKEN_RE.findall(term)
    )
    if provider_run is not None:
        for product in provider_run.products:
            if product.preview is None:
                continue
            for field in product.preview.fields:
                for term in (field.display_name, field.field_id):
                    normalized = term.casefold()
                    if len(normalized) >= 2 and normalized in folded_query:
                        tokens.append(normalized)
    return tuple(dict.fromkeys(tokens)) or (query.casefold(),)


def _direct_match_score(field: object, tokens: Sequence[str]) -> int:
    """Return a positive score when the query names this field directly."""

    field_name = str(getattr(field, "display_name")).casefold()
    field_id = str(getattr(field, "field_id")).casefold()
    score = 0
    for token in tokens:
        # One-character Chinese tokens (for example "的") are too broad to
        # distinguish a schema field from an incidental evidence hit.
        if len(token) < 2:
            continue
        if token in field_name:
            score += 5
        elif token in field_id:
            score += 4
    return score


def _product_query_score(preview: V5CandidatePreview, query: str) -> int:
    """Score explicit product references so one product does not fan out to all."""

    product_text = " ".join(
        (preview.product_id, preview.product_display_name, preview.insurance_class),
    ).casefold()
    normalized_query = query.casefold()
    if normalized_query in product_text:
        return 10
    # Natural questions commonly put the product reference before "的" or a
    # question word. Only scope the search when that prefix is a meaningful
    # product phrase; generic words such as "产品" and "平安" must not scope
    # every product in the catalogue.
    prefix = re.split(r"的|哪些|什么|哪|有", normalized_query, maxsplit=1)[0]
    prefix = re.sub(r"[\s，。！？?、]", "", prefix)
    if len(prefix) >= 3 and prefix in product_text:
        return 10
    compact_query = re.sub(r"[\s，。！？?、（）()【】\[\]《》:：;；/]", "", normalized_query)
    compact_product = re.sub(r"[\s，。！？?、（）()【】\[\]《》:：;；/]", "", product_text)
    if "e生保" in compact_query and "尊享版" in compact_query:
        return 10 if "e生保" in compact_product and "尊享版" in compact_product else 0
    # Product names in natural questions often include a version marker that
    # is separated by parentheses in the extracted display name.
    for start in range(max(0, len(compact_product) - 3)):
        for end in range(len(compact_product), start + 3, -1):
            if end - start >= 4 and compact_product[start:end] in compact_query:
                return 10
    return 0


def _query_requests_table(query: str) -> bool:
    normalized = re.sub(r"\s+", "", query.casefold())
    return any(term in normalized for term in ("表格", "表单", "markdowntable", "markdown表格"))


def _query_requests_product_coverage(query: str) -> bool:
    normalized = re.sub(r"\s+", "", query.casefold())
    return bool(_PRODUCT_COUNT_QUERY_RE.search(normalized)) or any(
        term in normalized
        for term in ("各产品", "每款产品", "全部产品", "所有产品", "各款产品")
    )


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
    tokens = _query_tokens(query, provider_run)
    ranked: list[tuple[int, int, int, int, int, V5SearchMatch]] = []
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
            direct_score = _direct_match_score(field, tokens)
            product_score = _product_query_score(preview, query)
            ranked.append(
                (
                    product_score,
                    direct_score,
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
    referenced_products = {item[5].product_id for item in ranked if item[0] > 0}
    product_scoped = (
        [item for item in ranked if item[5].product_id in referenced_products]
        if referenced_products
        else ranked
    )
    direct = [item for item in product_scoped if item[1] > 0]
    candidates = direct if direct else product_scoped
    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3], item[4]))
    if not _query_requests_product_coverage(query):
        return tuple(item[5] for item in candidates[:limit])

    # Broad/table questions need at least one evidence-backed row per product.
    # A plain top-N slice can hide the last products when one product has many
    # matching fields, even though the loaded run contains all products.
    selected: list[tuple[int, int, int, int, int, V5SearchMatch]] = []
    seen_products: set[str] = set()
    for item in candidates:
        product_id = item[5].product_id
        if product_id in seen_products:
            continue
        selected.append(item)
        seen_products.add(product_id)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        selected_keys = {(item[5].product_id, item[5].field_id) for item in selected}
        for item in candidates:
            key = (item[5].product_id, item[5].field_id)
            if key in selected_keys:
                continue
            selected.append(item)
            selected_keys.add(key)
            if len(selected) >= limit:
                break
    return tuple(item[5] for item in selected[:limit])


def _table_representatives(matches: Sequence[V5SearchMatch]) -> tuple[V5SearchMatch, ...]:
    by_product: dict[str, list[V5SearchMatch]] = {}
    product_order: list[str] = []
    for match in matches:
        if match.product_id not in by_product:
            by_product[match.product_id] = []
            product_order.append(match.product_id)
        by_product[match.product_id].append(match)
    representatives: list[V5SearchMatch] = []
    for product_id in product_order:
        product_matches = by_product[product_id]
        representatives.append(
            next(
                (
                    match
                    for match in product_matches
                    if "投保年龄" in match.field_display_name
                ),
                product_matches[0],
            )
        )
    return tuple(representatives)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _table_answer(query: str, matches: Sequence[V5SearchMatch]) -> str:
    representatives = _table_representatives(matches)
    if not representatives:
        return f'当前已加载的产品结果中未检索到与“{query}”直接匹配的字段。'
    rows = [
        "| 产品 | 匹配字段 | 抽取值 |",
        "| --- | --- | --- |",
    ]
    rows.extend(
        f"| {_markdown_cell(match.product_display_name)} | "
        f"{_markdown_cell(match.field_display_name)} | "
        f"{_markdown_cell(_value_text(match.value))} |"
        for match in representatives
    )
    return (
        f"基于当前已抽取结果，关于“{query}”命中 {len(matches)} 条字段，"
        f"覆盖 {len(representatives)} 款产品：\n\n"
        + "\n".join(rows)
    )


def _local_answer(query: str, matches: Sequence[V5SearchMatch]) -> str:
    if _query_requests_table(query):
        return _table_answer(query, matches)
    if not matches:
        return f'当前已加载的产品结果中未检索到与“{query}”直接匹配的字段。'
    products = len({match.product_id for match in matches})
    detailed_query = any(
        term in query
        for term in ("理赔", "材料", "事故通知", "核定", "给付", "时限")
    )
    value_limit = 1800 if detailed_query else 240
    details = []
    for match in matches[:8]:
        value = _value_text(match.value)
        if len(value) > value_limit:
            value = _compact_text(value, value_limit)
        details.append(f"{match.product_display_name}｜{match.field_display_name}：{value}")
    return (
        f'基于当前已抽取结果，关于“{query}”命中 {len(matches)} 条字段，涉及 {products} 款产品：\n'
        + "\n".join(details)
    )


def _compact_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    # Keep the beginning (usually the rule heading/condition) and the ending
    # (often the amount, exception, or limitation) while bounding prompt size.
    head = max(1, int(max_chars * 0.72))
    tail = max(1, max_chars - head - 1)
    return f"{value[:head]}…{value[-tail:]}"


def _normalize_provider_answer(value: str) -> str:
    """Repair harmless double-escaped Markdown line breaks from JSON mode."""

    normalized = (
        value
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
    )
    normalized = normalized.replace('">', "")
    normalized = re.sub(r"\\(?=[\\\-\[\]()>])", "", normalized)
    normalized = normalized.replace("\\", "")
    # Some JSON-mode responses repeat the closing quote/comma inside the
    # answer string. Trim only a suffix-shaped transport artifact, preserving
    # quotes and punctuation in the actual answer body.
    for marker in ('">', '", "match_indices"', '", "}'):
        position = normalized.rfind(marker)
        if position >= 0 and position >= len(normalized) - 80:
            normalized = normalized[:position]
    return normalized.rstrip(" \\n\r\t")


class _JsonAnswerDeltaExtractor:
    """Extract the answer string from an incrementally generated JSON object."""

    _ESCAPES = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""
        self._cursor = 0
        self._state = "seek"
        self._unicode = ""

    def feed(self, content: str) -> None:
        self._buffer += content
        while self._cursor < len(self._buffer):
            if self._state == "seek":
                marker = self._buffer.find('"answer"', self._cursor)
                if marker < 0:
                    self._cursor = max(0, len(self._buffer) - 10)
                    return
                self._cursor = marker + len('"answer"')
                self._state = "colon"
            elif self._state == "colon":
                char = self._buffer[self._cursor]
                if char.isspace():
                    self._cursor += 1
                elif char == ":":
                    self._cursor += 1
                    self._state = "quote"
                else:
                    self._state = "seek"
            elif self._state == "quote":
                char = self._buffer[self._cursor]
                if char.isspace():
                    self._cursor += 1
                elif char == '"':
                    self._cursor += 1
                    self._state = "string"
                else:
                    self._state = "seek"
            elif self._state == "string":
                char = self._buffer[self._cursor]
                self._cursor += 1
                if char == '"':
                    self._state = "done"
                elif char == "\\":
                    self._state = "escape"
                else:
                    self._emit(char)
            elif self._state == "escape":
                char = self._buffer[self._cursor]
                self._cursor += 1
                if char == "u":
                    self._unicode = ""
                    self._state = "unicode"
                else:
                    self._emit(self._ESCAPES.get(char, char))
                    self._state = "string"
            elif self._state == "unicode":
                char = self._buffer[self._cursor]
                self._cursor += 1
                if char.lower() not in "0123456789abcdef":
                    self._emit("\\u" + self._unicode + char)
                    self._state = "string"
                    continue
                self._unicode += char
                if len(self._unicode) == 4:
                    self._emit(chr(int(self._unicode, 16)))
                    self._state = "string"
            else:
                self._cursor = len(self._buffer)

    def finish(self) -> None:
        # A malformed/incomplete provider payload is rejected by the normal
        # JSON validation after the stream closes; no speculative text is sent.
        return


def _llm_context_matches(matches: Sequence[V5SearchMatch]) -> tuple[V5SearchMatch, ...]:
    # Keep the provider prompt proportional to the number of distinct products,
    # while preserving all direct field hits when the query names a schema field.
    # Broad questions can otherwise produce 20 long fields from the same product.
    selected: list[V5SearchMatch] = []
    product_counts: dict[str, int] = {}
    for match in matches:
        if len(selected) >= _LLM_CONTEXT_MATCH_LIMIT:
            break
        count = product_counts.get(match.product_id, 0)
        if count >= _LLM_CONTEXT_MAX_PER_PRODUCT:
            continue
        selected.append(match)
        product_counts[match.product_id] = count + 1
    return tuple(selected)


def _llm_answer(
    completion: SearchCompletion,
    query: str,
    matches: Sequence[V5SearchMatch],
    loaded_products: Sequence[object] = (),
    on_answer_delta: Callable[[str], None] | None = None,
) -> str:
    context_matches = _llm_context_matches(matches)
    context = [
        {
            "index": index,
            "product": match.product_display_name,
            "insurance_class": match.insurance_class,
            "field": match.field_display_name,
            "field_id": match.field_id,
            "value": _compact_text(_value_text(match.value), _LLM_CONTEXT_VALUE_CHARS),
            "evidence": [
                _compact_text(item.quote, _LLM_CONTEXT_EVIDENCE_CHARS)
                for item in match.evidence[:_LLM_CONTEXT_MAX_EVIDENCE]
            ],
        }
        for index, match in enumerate(context_matches)
    ]
    relevant_product_ids = {match.product_id for match in context_matches}
    product_source = (
        [
            product
            for product in loaded_products
            if getattr(product, "product_id", "") in relevant_product_ids
        ]
        if relevant_product_ids
        else list(loaded_products)
    )
    products = [
        {
            "product_id": getattr(product, "product_id", ""),
            "product": getattr(product, "product_display_name", ""),
            "insurance_class": getattr(product, "insurance_class", ""),
        }
        for product in product_source
    ]
    system = (
            f"你是保险产品知识检索助手，当前模型是 {completion.model}。"
            "只使用给定的已抽取字段、Evidence 和已加载产品清单回答用户问题，"
            "不得补充材料之外的保险事实。若用户询问你的模型身份，可以直接回答当前模型名；"
            "如果材料不足以回答其他问题，要明确说明材料中没有依据。回答要完整、易读："
            "优先按产品分组，列出关键数值、条件和限制；有多个命中时用分点或短段落展开；"
            "如果用户明确要求表格，必须在 answer 中输出合法 Markdown 表格，"
            "表头和每行使用半角竖线 |，"
            "不要使用全角竖线｜替代表格分隔符；"
            "涉及材料、时限或规则时，必须逐项覆盖上下文中与用户每个子问题相关的字段，"
            "不要用概括句代替具体材料、天数、触发条件和处理后果；"
            "并在结尾注明依据不足的部分。只输出 JSON 对象，结构为 "
            '{"answer":"按材料详细回答","match_indices":[0]}。'
        )
    user = json.dumps(
            {"query": query, "loaded_products": products, "matches": context},
            ensure_ascii=False,
        )
    stream_completion = getattr(completion, "complete_stream", None)
    if on_answer_delta is not None and callable(stream_completion):
        extractor = _JsonAnswerDeltaExtractor(on_answer_delta)
        raw = stream_completion(system=system, user=user, on_content_delta=extractor.feed)
        extractor.finish()
    else:
        raw = completion.complete(system=system, user=user)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID")
    answer = _normalize_provider_answer(payload["answer"].strip())
    indices = payload.get("match_indices", [])
    if not answer or not isinstance(indices, list) or not all(
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(context_matches)
        for index in indices
    ):
        raise LlmPluginError("V5_SEARCH_PROVIDER_RESULT_INVALID")
    # A few OpenAI-compatible Qwen responses can leave a JSON escaping tail in
    # the answer when the completion is very short. Prefer the deterministic,
    # evidence-backed answer in that case so the user never sees transport
    # syntax instead of product facts.
    if answer.lstrip().startswith('{'):
        return _local_answer(query, matches)
    if (
        len(answer) < 240
        and matches
        and any(term in query for term in ("理赔", "材料", "事故通知", "核定", "给付", "时限"))
    ):
        return _local_answer(query, matches)
    return answer


def search_provider_run(
    provider_run: V5ProviderTrialRun,
    request: V5SearchRequest,
    *,
    completion: SearchCompletion | None = None,
    on_answer_delta: Callable[[str], None] | None = None,
) -> V5SearchResponse:
    matches = build_v5_search_matches(provider_run, request.query, request.limit)
    answer = _local_answer(request.query, matches)
    provider: Literal["local", "bailian"] = "local"
    model: str | None = None
    provider_error: str | None = None
    if completion is not None:
        try:
            answer = _llm_answer(
                completion,
                request.query,
                matches,
                loaded_products=provider_run.products,
                on_answer_delta=(
                    None if _query_requests_table(request.query) else on_answer_delta
                ),
            )
            if _query_requests_table(request.query):
                answer = _table_answer(request.query, matches)
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
