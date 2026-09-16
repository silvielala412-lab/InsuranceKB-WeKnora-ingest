from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .business_field_quality import normalize_business_field_value
from .contracts import (
    CandidateEvidence,
    CandidateValue,
    EvidenceResolution,
    FieldDefinition,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
    PluginResult,
)
from .field_profiles import field_extraction_profile
from .value_constraints import normalize_field_value, parse_value_guidance


class LlmPluginError(ValueError):
    """The model response cannot be admitted to the closed preview boundary."""


class CompletionPort(Protocol):
    model: str

    def complete(self, *, system: str, user: str) -> str: ...


class CompletionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    response_id: str
    response_model: str
    finish_reason: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class OpenAICompatibleCompletion:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        model_family: Literal["qwen", "minimax"],
        timeout_seconds: float = 180.0,
        max_calls: int = 6,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if model_family not in {"qwen", "minimax"}:
            raise ValueError("V5_PREVIEW_MODEL_FAMILY_NOT_ALLOWED")
        self.model = model
        self._model_family = model_family
        self._max_calls = max_calls
        self._call_count = 0
        self._receipts: list[CompletionReceipt] = []
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    def complete(self, *, system: str, user: str) -> str:
        if self._call_count >= self._max_calls:
            raise LlmPluginError("V5_PREVIEW_PROVIDER_CALL_BUDGET_EXHAUSTED")
        self._call_count += 1
        body: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self._model_family == "qwen":
            body["enable_thinking"] = False
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
            return self._complete_qwen_stream(body)
        return self._complete_json(body)

    def _complete_json(self, body: dict[str, object]) -> str:
        response = self._client.post(
            "/chat/completions",
            json=body,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise LlmPluginError("LLM_RESULT_ENVELOPE_INVALID")
        choice = choices[0]
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LlmPluginError("LLM_RESULT_EMPTY")
        usage = payload.get("usage")
        typed_usage = usage if isinstance(usage, dict) else {}
        receipt = CompletionReceipt(
            response_id=str(payload.get("id") or "provider-response-id-unavailable"),
            response_model=str(payload.get("model") or self.model),
            finish_reason=str(choice.get("finish_reason") or "unknown"),
            prompt_tokens=_optional_int(typed_usage.get("prompt_tokens")),
            completion_tokens=_optional_int(typed_usage.get("completion_tokens")),
            total_tokens=_optional_int(typed_usage.get("total_tokens")),
        )
        self._receipts.append(receipt)
        if receipt.finish_reason != "stop":
            raise LlmPluginError("LLM_RESULT_NOT_COMPLETE")
        return content

    def _complete_qwen_stream(self, body: dict[str, object]) -> str:
        content_parts: list[str] = []
        response_id = "provider-response-id-unavailable"
        response_model = self.model
        finish_reason = "unknown"
        usage: dict[str, Any] = {}
        saw_done = False
        with self._client.stream("POST", "/chat/completions", json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    chunk: dict[str, Any] = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise LlmPluginError("LLM_STREAM_CHUNK_INVALID") from exc
                response_id = str(chunk.get("id") or response_id)
                response_model = str(chunk.get("model") or response_model)
                chunk_usage = chunk.get("usage")
                if isinstance(chunk_usage, dict):
                    usage = chunk_usage
                choices = chunk.get("choices")
                if not isinstance(choices, list):
                    raise LlmPluginError("LLM_STREAM_CHUNK_INVALID")
                if not choices:
                    continue
                if len(choices) != 1 or not isinstance(choices[0], dict):
                    raise LlmPluginError("LLM_STREAM_CHUNK_INVALID")
                choice = choices[0]
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    raise LlmPluginError("LLM_STREAM_CHUNK_INVALID")
                content = delta.get("content")
                if content is not None:
                    if not isinstance(content, str):
                        raise LlmPluginError("LLM_STREAM_CHUNK_INVALID")
                    content_parts.append(content)
                if choice.get("finish_reason") is not None:
                    finish_reason = str(choice["finish_reason"])
        receipt = CompletionReceipt(
            response_id=response_id,
            response_model=response_model,
            finish_reason=finish_reason,
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
        )
        self._receipts.append(receipt)
        content = "".join(content_parts)
        if not saw_done or receipt.finish_reason != "stop":
            raise LlmPluginError("LLM_RESULT_NOT_COMPLETE")
        if not content.strip():
            raise LlmPluginError("LLM_RESULT_EMPTY")
        return content

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def receipts(self) -> tuple[CompletionReceipt, ...]:
        return tuple(self._receipts)

    def close(self) -> None:
        self._client.close()


_SYSTEM_PROMPT = """你是寿险产品知识 Schema 抽取器。只输出一个 JSON 对象，不要 Markdown。
必须对给定的目标字段按原 ordinal 和 field_id 输出一行，不能遗漏、增加或改序。
state 只能是 present、absent_explicitly、unknown：
- present 必须有 value 和至少一条 evidence；
- absent_explicitly 仅在原文明确说明不存在时使用，value 为 null 且必须有 evidence；
- unknown 的 value 必须为 null，evidence 必须为空数组。
evidence 只含 locator 和 quote，quote 必须逐字出现在原文，足以支持字段且不超过2000字符。
locator 必须按页标题填写为 pdf:<文件名>#page=<页码>；它只是建议值，系统仍会
核对该页确实逐字包含 quote 后才采纳。
不得引用系统插入的文档/页码标题，不得用常识补全事实。
value 只允许字符串、数字、布尔或字符串数组；复杂结构请转为语义完整的字符串。
value_constraint.allow_other=true 表示 allowed_values 只是示例，不是封闭全集；必须以材料为准
保留产品特有值。跨多个文件出现的同一字段必须合并，不能用说明书摘要覆盖或替代条款细节。
对要求清单、组成部分、条件或限制的字段，宁可分项详实表达，也不得为了简短而省略材料中
已经明确给出的事实。
保险责任、责任免除、疾病定义与认定标准等长条款字段，value 使用逐项编号的完整字符串；
每个原子项目至少给一条直接 Evidence，Evidence 顺序与项目顺序一致。不得用“等”、
“包括但不限于”或“详见条款”替代材料中已经给出的项目。
`coverage_summary`（字段名“保什么”）是保障责任汇总字段：即使原文没有“保什么”标题，
也要从所有给出的材料中合并“保险责任、我们承担、给付、保险金、医疗费用、身故、满期、
生存、重大疾病、意外”等明确责任表达。保留每项责任的触发条件、给付限制和适用范围，
不要把营销话术、责任免除、保单贷款、自动垫交、减额交清、退保、分红或其他保全权益
写成保障内容；这些内容应由各自字段承接。每个写入汇总的责任项目都要给出对应逐字 Evidence。
Content 或 LLM生成字段仍只是对应知识角色的候选内容，不得伪装成 Fact。
当目标字段是纯 LLM生成的产品简介或产品概览时，如果输入材料足以支撑，必须生成
受材料约束的简洁总结；生成文本可以不是原文逐字复制，但必须用逐字 Evidence 支撑
其中的主要事实，材料不足时才返回 unknown。
返回结构严格为一个只含 fields 数组的 JSON 对象；字段行只含 ordinal、field_id、
state、value、evidence。"""


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _field_extraction_instruction(field: FieldDefinition) -> str | None:
    profile = field_extraction_profile(field.field_id)
    if profile is not None:
        if field.field_id == "policyholder_rights":
            return (
                profile.instruction
                + "每项权益都必须有直接支持该项的独立 Evidence。"
            )
        return profile.instruction
    instructions = {
        "coverage_responsibilities": (
            "保险责任：遍历全部材料后合并所有正式责任项目。按原子责任逐项编号，保留责任名称、"
            "触发条件、给付口径、次数/比例/限额和适用范围；不得使用‘等’或‘详见条款’省略责任项目；"
            "每个项目至少被一条直接 Evidence 支持；同一段完整条款可支持其中多个项目。材料涉及"
            "主险、附加险或其他合同时，逐项写清适用对象，不得把其他合同责任并入当前产品。"
        ),
        "exclusions": (
            "责任免除：只整理正式免责条款，按原子免责情形逐项编号，保留前置条件、例外和适用责任；"
            "不得把等待期、健康告知或普通责任限制混成免责，不得使用‘等’或‘详见条款’省略责任项目；"
            "每个项目至少被一条直接 Evidence 支持；同一段完整条款可支持其中多个项目。材料涉及"
            "主险、附加险或其他合同时，逐项写清适用对象，不得把其他合同免责并入当前产品。"
        ),
        "disease_definitions_and_criteria": (
            "疾病定义与认定标准：汇总材料明确给出的疾病名称、定义、诊断/手术/状态要求、持续时间、"
            "分组或赔付关联条件，按疾病或共同标准逐项编号；不得使用‘等’或‘详见条款’省略责任项目；"
            "每个项目至少被一条直接 Evidence 支持；同一段完整定义可支持其中多个项目。材料涉及"
            "主险、附加险或其他合同时，逐项写清适用对象。"
        ),
        "premium_payment_term": (
            "缴费期限：抽取正式投保规则中全部可选交费期间并去重；示例或利益演示中的单一交费期间"
            "不能当成完整可选集合。保留趸交与各年期，只用正式选项句作为 Evidence。"
        ),
        "premium_payment_frequency": (
            "缴费方式：抽取正式投保规则中全部可选频次并去重，例如趸交、年交、半年交、季交、月交；"
            "示例或利益演示中的单一方式不能当成完整集合，只用正式选项句作为 Evidence。"
        ),
        "waiting_period": (
            "等待期：完整抽取等待期时长、起算点、适用责任、意外原因是否例外，以及等待期内发生"
            "保险事故的处理后果；不得只返回天数。每个组成部分都要有直接 Evidence。"
        ),
        "coverage_summary": (
            "保什么：汇总所有材料中明确写出的保障责任，不要求出现字段同名标题；"
            "跨页合并并保留责任条件；只写保险责任和核心给付，不写保单贷款、自动垫交、"
            "减额交清、退保、分红等保全权益；每个责任项目都提供原文 Evidence。"
        ),
        "target_customer_profile": (
            "适用人群：可根据投保年龄、投保范围、被保险人范围、家庭成员、成人/少儿、"
            "产品用途等材料语义归纳一个有边界的客群描述；不要求出现‘适用人群’标题，"
            "但必须给出支撑归纳的逐字 Evidence，不得把常识当成客群。"
        ),
        "premium_grace_period": (
            "宽限期：只抽取正式条款中续期/分期保费到期后的宽限期间、起算、期间内责任和"
            "终止规则；等待期、保险期间届满后的重新投保窗口不属于宽限期；证据不足保持 unknown。"
        ),
        "premium_adjustment_rules": (
            "费率可调：只有原文明确说明产品费率可调整、调整机制或重新定价时才填值；"
            "家庭费率因子、核保加费、年龄错误导致提高费率，不等于一般费率可调；"
            "证据不足保持 unknown。"
        ),
        "product_conversion_rules": (
            "险种转换：只有原文明确说明险种转换、转保或转换权时才填值；"
            "普通续保、附加险或保险期间届满不等于险种转换；证据不足保持 unknown。"
        ),
        "product_summary": (
            "产品简介：基于所有输入材料归纳约200字的产品定位、主要特色、保障范围和关键限制；"
            "可以是总结文本，不要求逐字复制原文，但每项主要事实都必须有逐字 Evidence。"
            "材料不足的部分不要猜测，也不要把营销话术当成承诺。"
        ),
        "product_overview": (
            "产品概览：基于所有输入材料整理便于展示的一屏概览，覆盖产品类型、核心保障/给付、"
            "投保与费用规则、重要限制或权益；可以是结构化总结文本，但只能使用材料和已验证事实，"
            "每项主要事实都必须有逐字 Evidence。材料不足时保留 unknown。"
        ),
        "policyholder_rights": (
            "保单权益：只抽取保险合同项下的保单贷款、减额交清、自动垫交、退保等权益；"
            "健康服务项目不能冒充保单权益。每项权益都必须有直接支持该项的独立 Evidence；"
            "材料明确未约定或只有相似字样时不得填入。若当前产品是附加险，‘适用主险合同’"
            "只能说明主险权益，不得作为当前附加险自身享有该权益的依据。"
        ),
        "eligible_service_packages": (
            "可享服务：从服务手册或服务清单归纳产品对应的服务大类和明确服务名称；"
            "保留使用次数、适用阶段或申请条件，不把保险责任当成服务。"
        ),
        "medical_service_benefits": (
            "增值服务：抽取材料明确提供的问诊、就医协助、陪诊、直付垫付、特药和康复等服务；"
            "合并同类项目但保留关键次数与条件，每类服务都给出逐字 Evidence。"
        ),
        "product_faq": (
            "产品Q&A：只根据材料中明确的问答段落归纳常见问题与答案；没有明确答案时保持 unknown，"
            "不得自行设计营销问答。"
        ),
    }
    return instructions.get(field.field_id)


def _schema_prompt(
    request: IngestRequest,
    schema: InsuranceSchema,
    *,
    target_fields: tuple[FieldDefinition, ...] | None = None,
    repair_hint: str | None = None,
    synthesis_context: str | None = None,
) -> str:
    fields = target_fields if target_fields is not None else schema.fields
    schema_rows = [
        {
            "ordinal": field.ordinal,
            "category": f"{field.category_id} {field.category_display_name}",
            "field_id": field.field_id,
            "label": field.display_name,
            "value_guidance": field.value_guidance,
            "description": field.description,
            "source_guidance": field.source_guidance,
            "formation_modes": field.formation_modes,
            "knowledge_role": field.knowledge_role,
            "value_constraint": parse_value_guidance(
                field.value_guidance
            ).as_prompt_dict(),
            "extraction_instruction": _field_extraction_instruction(field),
        }
        for field in fields
    ]
    return json.dumps(
        {
            "source_revision_id": request.source_revision_id,
            "insurance_class": schema.insurance_class,
            "product_id": request.product_id,
            "product_version_id": request.product_version_id,
            "product_display_name": request.product_display_name,
            "schema_id": schema.schema_id,
            "schema_fields": schema_rows,
            "source_text": request.source_text,
            "repair_hint": repair_hint,
            "synthesis_context": synthesis_context,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _closed_keys(value: object, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def _evidence_quote_chunks(quote: str, *, limit: int = 1900) -> tuple[str, ...]:
    remaining = quote.strip()
    chunks: list[str] = []
    while len(remaining) > limit:
        split_at = max(
            remaining.rfind("\n", 0, limit),
            remaining.rfind("。", 0, limit),
            remaining.rfind("；", 0, limit),
        )
        if split_at < limit // 2:
            split_at = limit
        elif remaining[split_at] != "\n":
            split_at += 1
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


class SchemaGuidedLlmPlugin:
    plugin_id = "schema-guided-openai-compatible-v1"

    def __init__(
        self,
        *,
        completion: CompletionPort,
        evidence_resolver: Callable[[str, str], EvidenceResolution] | None = None,
        repair_hint: str | None = None,
        target_field_ids: tuple[str, ...] | None = None,
        synthesis_context: str | None = None,
    ) -> None:
        self._completion = completion
        self._evidence_resolver = evidence_resolver
        self._repair_hint = repair_hint
        self._target_field_ids = target_field_ids
        self._synthesis_context = synthesis_context

    def _target_fields(self, schema: InsuranceSchema) -> tuple[FieldDefinition, ...]:
        if self._target_field_ids is None:
            return tuple(schema.fields)
        if not self._target_field_ids or len(set(self._target_field_ids)) != len(
            self._target_field_ids
        ):
            raise LlmPluginError("LLM_TARGET_FIELD_SET_INVALID")
        requested = set(self._target_field_ids)
        fields = tuple(field for field in schema.fields if field.field_id in requested)
        if tuple(field.field_id for field in fields) != self._target_field_ids:
            raise LlmPluginError("LLM_TARGET_FIELD_SET_INVALID")
        return fields

    def extract(self, request: IngestRequest, schema: InsuranceSchema) -> PluginResult:
        if not request.source_text.strip():
            raise LlmPluginError("LLM_SOURCE_TEXT_REQUIRED")
        target_fields = self._target_fields(schema)
        raw = self._completion.complete(
            system=_SYSTEM_PROMPT,
            user=_schema_prompt(
                request,
                schema,
                target_fields=target_fields,
                repair_hint=self._repair_hint,
                synthesis_context=self._synthesis_context,
            ),
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LlmPluginError("LLM_RESULT_INVALID_JSON") from exc
        if not _closed_keys(payload, {"fields"}) or not isinstance(payload["fields"], list):
            raise LlmPluginError("LLM_RESULT_ENVELOPE_INVALID")
        if len(payload["fields"]) != len(target_fields):
            raise LlmPluginError("LLM_RESULT_SCHEMA_TOPOLOGY_DRIFT")

        targeted_results: dict[str, PluginFieldResult] = {}
        for definition, row in zip(target_fields, payload["fields"], strict=True):
            if not _closed_keys(row, {"ordinal", "field_id", "state", "value", "evidence"}):
                raise LlmPluginError("LLM_RESULT_FIELD_INVALID")
            if row["ordinal"] != definition.ordinal or row["field_id"] != definition.field_id:
                raise LlmPluginError("LLM_RESULT_SCHEMA_TOPOLOGY_DRIFT")
            if not isinstance(row["evidence"], list):
                targeted_results[definition.field_id] = PluginFieldResult(
                    ordinal=definition.ordinal,
                    field_id=definition.field_id,
                    state="unknown",
                )
                continue
            evidence: list[CandidateEvidence] = []
            field_evidence_invalid = False
            for item in row["evidence"]:
                if (
                    not _closed_keys(item, {"locator", "quote"})
                    or not isinstance(item["locator"], str)
                    or not isinstance(item["quote"], str)
                    or not item["locator"].strip()
                    or not item["quote"].strip()
                ):
                    field_evidence_invalid = True
                    break
                try:
                    for quote in _evidence_quote_chunks(item["quote"]):
                        if self._evidence_resolver is None:
                            is_verified = quote in request.source_text
                            resolution = EvidenceResolution(
                                locator=item["locator"],
                                verification_status=(
                                    "VERIFIED" if is_verified else "UNRESOLVED"
                                ),
                                verification_error=(
                                    None if is_verified else "V5_EVIDENCE_PAGE_NOT_FOUND"
                                ),
                            )
                        else:
                            resolution = self._evidence_resolver(quote, item["locator"])
                        evidence.append(
                            CandidateEvidence(
                                source_revision_id=request.source_revision_id,
                                locator=resolution.locator,
                                quote=quote,
                                verification_status=resolution.verification_status,
                                verification_error=resolution.verification_error,
                            )
                        )
                except ValidationError:
                    field_evidence_invalid = True
                    break
                except ValueError:
                    field_evidence_invalid = True
                    break
            if field_evidence_invalid:
                targeted_results[definition.field_id] = PluginFieldResult(
                    ordinal=definition.ordinal,
                    field_id=definition.field_id,
                    state="unknown",
                )
                continue
            try:
                raw_value = (
                    tuple(row["value"])
                    if isinstance(row["value"], list)
                    else row["value"]
                )
                normalized_value = (
                    normalize_field_value(definition, raw_value)
                    if row["state"] == "present"
                    else raw_value
                )
                if row["state"] == "present":
                    normalized_value = normalize_business_field_value(
                        definition.field_id,
                        cast(CandidateValue, normalized_value),
                        tuple(
                            item.quote
                            for item in evidence
                            if item.verification_status
                            in {"VERIFIED", "NORMALIZED_MATCH"}
                        ),
                    )
                targeted_results[definition.field_id] = PluginFieldResult(
                    ordinal=row["ordinal"],
                    field_id=row["field_id"],
                    state=row["state"],
                    value=normalized_value,
                    evidence=tuple(evidence),
                )
            except ValidationError:
                targeted_results[definition.field_id] = PluginFieldResult(
                    ordinal=definition.ordinal,
                    field_id=definition.field_id,
                    state="unknown",
                )

        results = tuple(
            targeted_results.get(field.field_id)
            or PluginFieldResult(
                ordinal=field.ordinal,
                field_id=field.field_id,
                state="unknown",
            )
            for field in schema.fields
        )

        return PluginResult(
            plugin_id=self.plugin_id,
            source_revision_id=request.source_revision_id,
            insurance_class=schema.insurance_class,
            product_id=request.product_id,
            product_version_id=request.product_version_id,
            schema_id=schema.schema_id,
            fields=results,
        )


__all__ = [
    "CompletionPort",
    "CompletionReceipt",
    "LlmPluginError",
    "OpenAICompatibleCompletion",
    "SchemaGuidedLlmPlugin",
]
