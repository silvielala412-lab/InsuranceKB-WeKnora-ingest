"""统一模型客户端（004 T1/T4；设计 docs/insurance-kb/04 §2.1）。

002 goldenset 与 004 抽取管道共用同一 ``ModelClient`` Protocol：
- ``ReplayClient``：录制回放夹具（测试/无网关凭据时唯一可用通道）；
- ``LiteLLMClient``：经 new-api 网关的真实调用（08 选型），litellm 为可选
  extra ``llm``，延迟导入——CI 不装该组也能 import 本模块。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol, cast
from weakref import WeakKeyDictionary

import httpx
from pydantic import BaseModel

from ..model_policy import (
    GuardedModelClient,
    ModelCallFacts,
    ModelCallRequest,
    ModelIdentity,
    ModelRole,
    VerifiedAdmission,
)
from ..model_policy.admission import _is_verified_admission


class ModelClient(Protocol):
    async def complete(self, system: str, user: str) -> str: ...


_COMPILER_TEMPLATE_DOMAIN = b"insurancekb.compiler.model-template.v1\0"
_COMPILER_INPUT_FACT_DOMAIN = b"insurancekb.compiler.model-input-fact.v1\0"
_ATTEMPT_ID = re.compile(r"^(?P<sequence>[0-9]{8}):(?P<stage>[^:]+):(?P<key>[0-9a-f]{12})$")
_PRODUCTION_CLIENT_SEAL = object()


class ProductionEntrypointDenied(PermissionError):
    """Typed refusal when compiler call facts cannot be produced canonically."""

    _MESSAGES = {
        "invalid_production_client": "production compiler model client is unavailable",
        "canonical_adapter_unavailable": "canonical production model adapter is unavailable",
        "invalid_model_profile": "model profile is not valid for this entrypoint",
        "invalid_production_judge": "production compiler judge route is unavailable",
        "replay_fixture_required": "replay profile requires an immutable fixture directory",
        "reserved_call_required": "production model call requires a durable reserved attempt",
        "reserved_call_mismatch": "production model call does not match its reserved attempt",
        "role_not_admitted": "production model role is not admitted",
    }

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(self._MESSAGES.get(reason_code, "production model call denied"))


@dataclass(frozen=True, slots=True)
class _ProductionCompilerClientState:
    verified_admission: VerifiedAdmission
    guarded_clients: tuple[tuple[ModelRole, GuardedModelClient, ModelIdentity], ...]
    retained_resources: tuple[object, ...]


_PRODUCTION_CLIENT_STATES: WeakKeyDictionary[
    object, _ProductionCompilerClientState
] = WeakKeyDictionary()
_PRODUCTION_CLIENT_LOCK = RLock()


class ProductionCompilerClient:
    """Sealed compatibility adapter; direct unscoped calls always fail closed."""

    __slots__ = ("__weakref__",)

    def __new__(
        cls,
        *_args: object,
        _seal: object | None = None,
        **_kwargs: object,
    ) -> ProductionCompilerClient:
        if cls is not ProductionCompilerClient or _seal is not _PRODUCTION_CLIENT_SEAL:
            raise TypeError("ProductionCompilerClient is built only by composition root")
        return super().__new__(cls)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("ProductionCompilerClient is immutable")

    async def complete(self, system: str, user: str) -> str:
        del system, user
        raise ProductionEntrypointDenied("reserved_call_required")


def _compiler_template_hash(*, stage: str, prompt_version: str, system: str) -> str:
    """Address the exact code-owned prompt template; not a 028 TemplatePackage hash."""

    payload = json.dumps(
        {
            "prompt_version": prompt_version,
            "stage": stage,
            "system": system,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(_COMPILER_TEMPLATE_DOMAIN + payload).hexdigest()


def _compiler_input_digest(
    *,
    run_id: str,
    call_stage: str,
    attempt_id: str,
    field_ids: tuple[str, ...],
    reserved_request_key: str,
) -> str:
    """Bind job fields and durable reservation separately from request content."""

    if any(type(field_id) is not str or not field_id.strip() for field_id in field_ids):
        raise ProductionEntrypointDenied("reserved_call_mismatch")
    payload = json.dumps(
        {
            "attempt_id": attempt_id,
            "field_ids": list(dict.fromkeys(field_ids)),
            "request_key": reserved_request_key,
            "run_id": run_id,
            "stage": call_stage,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(_COMPILER_INPUT_FACT_DOMAIN + payload).hexdigest()


def _get_production_client_state(value: object) -> _ProductionCompilerClientState | None:
    if type(value) is not ProductionCompilerClient:
        return None
    with _PRODUCTION_CLIENT_LOCK:
        return _PRODUCTION_CLIENT_STATES.get(value)


def _is_production_compiler_client(value: object) -> bool:
    return _get_production_client_state(value) is not None


def _require_production_compiler_client(
    value: object,
    *,
    schema_hash: str,
    model_id: str,
    space_id: str | None,
) -> ProductionCompilerClient:
    """Validate the sealed adapter against independently observed pipeline facts."""

    state = _get_production_client_state(value)
    if state is None:
        raise ProductionEntrypointDenied("invalid_production_client")
    expected = state.verified_admission.request
    extract_route = next(
        (entry for entry in state.guarded_clients if entry[0] == "extract"), None
    )
    if (
        extract_route is None
        or schema_hash != expected.expected_schema_hash
        or model_id != extract_route[2].deployment_id
        or space_id is None
        or space_id != expected.expected_space_id
    ):
        raise ProductionEntrypointDenied("invalid_production_client")
    return cast(ProductionCompilerClient, value)


def _build_production_compiler_client_for_test(
    *,
    guarded_clients: Mapping[str, GuardedModelClient],
    verified_admission: VerifiedAdmission,
    retained_resources: tuple[object, ...],
) -> ProductionCompilerClient:
    """Test-only bridge; production accepts no caller-provided guard map."""

    if not _is_verified_admission(verified_admission):
        raise ProductionEntrypointDenied("invalid_production_client")
    approved = {
        identity.role: identity
        for identity in verified_admission.binding.approved_identities
    }
    entries: list[tuple[ModelRole, GuardedModelClient, ModelIdentity]] = []
    for raw_role, guard in guarded_clients.items():
        role = cast(ModelRole, raw_role)
        identity = approved.get(role)
        if (
            identity is None
            or type(guard) is not GuardedModelClient
            or raw_role not in {"classify", "extract", "gap", "verify", "consensus"}
        ):
            raise ProductionEntrypointDenied("invalid_production_client")
        entries.append((role, guard, identity))
    if not entries:
        raise ProductionEntrypointDenied("invalid_production_client")
    client = ProductionCompilerClient.__new__(
        ProductionCompilerClient,
        _seal=_PRODUCTION_CLIENT_SEAL,
    )
    state = _ProductionCompilerClientState(
        verified_admission=verified_admission,
        guarded_clients=tuple(sorted(entries, key=lambda entry: entry[0])),
        retained_resources=tuple(retained_resources),
    )
    with _PRODUCTION_CLIENT_LOCK:
        _PRODUCTION_CLIENT_STATES[client] = state
    return client


def _role_for_stage(stage: str) -> ModelRole:
    base_stage = stage.removesuffix("_retry")
    if base_stage.startswith("extract") or base_stage == "semantic_resolve":
        return "extract"
    if base_stage == "gapfill":
        return "gap"
    if base_stage == "vote":
        return "verify"
    if base_stage == "judge":
        return "consensus"
    if base_stage == "classify":
        return "classify"
    raise ProductionEntrypointDenied("role_not_admitted")


async def _complete_reserved_model_call(
    client: ModelClient,
    system: str,
    user: str,
    *,
    run_id: str,
    call_stage: str,
    prompt_version: str,
    attempt_id: str,
    reserved_request_key: str,
    field_ids: tuple[str, ...],
) -> str:
    """Use durable reservation facts for production; preserve offline transports."""

    state = _get_production_client_state(client)
    metered: MeteredClient | None = None
    if state is None and type(client) is MeteredClient:
        metered = client
        state = _get_production_client_state(client._inner)
    if state is None:
        return await client.complete(system, user)

    match = _ATTEMPT_ID.fullmatch(attempt_id)
    current_key = request_key(system, user)
    if (
        match is None
        or match.group("stage") != call_stage
        or match.group("key") != current_key[:12]
        or reserved_request_key != current_key
        or run_id != state.verified_admission.request.expected_run_id
    ):
        raise ProductionEntrypointDenied("reserved_call_mismatch")
    attempt = int(match.group("sequence"))
    role = _role_for_stage(call_stage)
    route = next((entry for entry in state.guarded_clients if entry[0] == role), None)
    if route is None:
        raise ProductionEntrypointDenied("role_not_admitted")
    _role, guard, identity = route
    expected = state.verified_admission.request
    request = ModelCallRequest(
        content=user.encode("utf-8", errors="strict"),
        rendered_prompt=system.encode("utf-8", errors="strict"),
    )
    facts = ModelCallFacts(
        job_id=expected.expected_run_id,
        stage=call_stage,
        attempt=attempt,
        input_digest=_compiler_input_digest(
            run_id=run_id,
            call_stage=call_stage,
            attempt_id=attempt_id,
            field_ids=field_ids,
            reserved_request_key=reserved_request_key,
        ),
        content_digest=hashlib.sha256(request.content).hexdigest(),
        rendered_prompt_digest=hashlib.sha256(request.rendered_prompt).hexdigest(),
        purpose=expected.expected_purpose,
        run_schema_version=expected.expected_run_schema_version,
        space_id=expected.expected_space_id,
        run_id=expected.expected_run_id,
        run_revision=expected.expected_run_revision,
        admission_artifact_digest=expected.expected_admission_artifact_digest,
        template_hash=_compiler_template_hash(
            stage=call_stage,
            prompt_version=prompt_version,
            system=system,
        ),
        model_plan_hash=expected.expected_model_plan_hash,
        identity=identity,
        role=role,
    )
    result = await guard.call(state.verified_admission, facts, request)
    if metered is not None:
        metered.stats.record(system, user, result)
    return result


def request_key(system: str, user: str) -> str:
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:16]


class ReplayClient:
    """从夹具目录回放录制响应（002 spec G5.1 / 004 spec E5.3）。文件名 = request_key + .txt。"""

    def __init__(self, fixture_dir: Path) -> None:
        self._dir = fixture_dir
        self.calls = 0

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        path = self._dir / f"{request_key(system, user)}.txt"
        if not path.exists():
            raise FileNotFoundError(
                f"ReplayClient 缺少夹具 {path.name}（system/user 变更会导致 key 变化）"
            )
        return path.read_text(encoding="utf-8")


class CallStats(BaseModel):
    """LLM 调用统计（E1.3 run manifest）。无网关侧 token 计数时以字符数为估算基础。"""

    calls: int = 0
    prompt_chars: int = 0
    completion_chars: int = 0

    def record(self, system: str, user: str, completion: str) -> None:
        self.calls += 1
        self.prompt_chars += len(system) + len(user)
        self.completion_chars += len(completion)

    @property
    def est_tokens(self) -> int:
        # 中文语料下 1 token ≈ 1.5 字符的保守估算（仅用于 manifest 量级参考）
        return int((self.prompt_chars + self.completion_chars) / 1.5)


class MeteredClient:
    """包装任意 ModelClient，把调用量记入 CallStats（E1.3）。"""

    def __init__(self, inner: ModelClient, stats: CallStats) -> None:
        self._inner = inner
        self.stats = stats

    async def complete(self, system: str, user: str) -> str:
        out = await self._inner.complete(system, user)
        self.stats.record(system, user, out)
        return out


class TruncatedOutputError(Exception):
    """模型输出为空或 finish_reason=length——按内容级重试处理。

    推理型模型（deepseek-v4-flash / MiniMax-M2.5 均返回 reasoning_content）在
    max_tokens 不足时会把预算全部耗在推理上，正文为空。
    """


def openai_compat_request_bytes(
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    system: str,
    user: str,
    thinking: Literal["enabled", "disabled"] | None = None,
    response_format: Literal["json_object"] | None = None,
) -> bytes:
    """Serialize the exact HTTP JSON envelope used by OpenAICompatClient."""

    payload: dict[str, object] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if thinking is not None:
        payload["thinking"] = {"type": thinking}
    if response_format is not None:
        if response_format != "json_object":  # pragma: no cover - typing guard
            raise ValueError("unsupported OpenAI-compatible response format")
        payload["response_format"] = {"type": response_format}
    payload["messages"] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class OpenAICompatClient:
    """OpenAI 兼容端点直连（坑清单 #9：trust_env=False）。

    推理型模型约定（业务方 2026-07-12 实测）：
    - max_tokens 必须给足（默认 4096），否则 reasoning_content 吃掉全部预算；
    - 可由调用方显式冻结官方 ``thinking`` 模式；未指定时保持兼容旧调用；
    - 可选 ``response_format=json_object``；未指定时保持旧请求 bytes；
    - 只取 message.content，忽略 reasoning_content；
    - content 为空或 finish_reason=length → 抛 TruncatedOutputError（可重试）。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout_s: float = 180.0,
        thinking: Literal["enabled", "disabled"] | None = None,
        response_format: Literal["json_object"] | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._thinking = thinking
        self._response_format = response_format
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
            trust_env=False,  # 本机 SOCKS 代理环境变量曾导致 httpx 全挂（HANDOFF 坑 #9）
        )

    @property
    def model(self) -> str:
        return self._model

    async def complete(self, system: str, user: str) -> str:
        body = openai_compat_request_bytes(
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            system=system,
            user=user,
            thinking=self._thinking,
            response_format=self._response_format,
        )
        resp = await self._client.post(
            "/chat/completions",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        choice = data["choices"][0]
        content = str(choice.get("message", {}).get("content") or "")
        finish = str(choice.get("finish_reason", ""))
        if finish == "length":
            raise TruncatedOutputError(
                f"模型 {self._model} 输出被截断（finish_reason={finish}）——"
                "按截断重试"
            )
        if not content.strip():
            raise TruncatedOutputError(
                f"模型 {self._model} 输出正文为空（finish_reason={finish}）——"
                "疑似 reasoning 耗尽 max_tokens，按截断重试"
            )
        return content

    async def aclose(self) -> None:
        await self._client.aclose()


class LiteLLMClient:
    """经模型网关的真实调用（08 选型：new-api + litellm）。依赖可选 extra ``llm``。

    002 的 goldenset.annotator.LiteLLMClient 是本类的 settings 包装。
    """

    def __init__(
        self,
        model: str,
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        if not model:
            raise ValueError("缺少模型标识（如 HARNESS_EXTRACTION_MODEL）")
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "litellm 未安装：请 `uv sync --extra llm` 后再使用真实模型"
            ) from exc
        self._litellm = litellm
        self._model = model
        self._api_base = api_base
        self._api_key = api_key
        self._temperature = temperature

    async def complete(self, system: str, user: str) -> str:  # pragma: no cover - 需真实网关
        resp = await self._litellm.acompletion(
            model=self._model,
            api_base=self._api_base,
            api_key=self._api_key,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return cast(str, resp.choices[0].message.content or "")


class GapfillBudgetExhausted(RuntimeError):
    """024 E3 R2：补漏预算耗尽——出站前拒绝，绝不发请求。"""
