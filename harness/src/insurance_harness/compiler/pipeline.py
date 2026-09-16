"""LangGraph 编排（004 T7；spec E1；设计 04 §5.1）。

- 每产品一个 graph run；节点 = load → split_route → extract → gapfill → vote → finalize；
- **状态机是确定性的，LLM 只存在于节点内部**；状态为 JSON 可序列化 dict（pydantic
  模型 dump 后入 state），SqliteSaver checkpoint 持久化，kill 后从最后完成节点续跑（E1.1）；
- 节点内传输级失败指数退避重试，超限记死信且**不中断其他字段组**（E1.2）；
- run manifest 记录 schema 版本/模型/prompt 版本/耗时/调用与 token 统计/族指纹（E1.3）。
"""

import asyncio
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Literal, TypedDict, cast
from weakref import WeakKeyDictionary

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..adapters.weknora.scope import scope_log_context
from ..db.scope import KnowledgeScope, ScopeViolation
from ..goldenset.pdf import PageText
from ..goldenset.records import Evidence
from ..schemas import FieldSpec, ProductLineSchema, SchemaRegistry
from ..sources import (
    DocumentSource,
    MaterializedBatch,
    SourceDocument,
    SourceRevision,
    match_quote_to_chunks,
    source_ordering_identity_token,
)
from .attempts import SqliteAttemptLedger
from .experiment import AssignmentPolicy, assign_arm, experiment_digest
from .extract import (
    Sleeper,
    TransportRetryError,
    Window,
    WindowExtractor,
    build_windows,
    with_transport_retry,
)
from .feedability import score_feedability
from .gapfill import gapfill_eligibility, gapfill_field
from .judge import JudgeDispatcher, make_judge_request, write_judge_queue
from .llm import (
    CallStats,
    GapfillBudgetExhausted,
    MeteredClient,
    ModelClient,
    ProductionEntrypointDenied,
    _require_production_compiler_client,
)
from .models import (
    AuditAttempt,
    BaselineAdmissionIdentity,
    DataQuality,
    DeadLetter,
    DocManifestEntry,
    DocPayload,
    ExtractionAudit,
    FieldCandidate,
    Judgement,
    JudgeRequest,
    PredRecord,
    RunManifest,
)
from .prompts import PROMPT_VERSION
from .routing_data import GROUP_ORDER, group_of_field
from .sections import family_fingerprint, route_groups, split_sections
from .semantic_resolution import resolve_candidates
from .templates import TemplateRegistry, run_fastpath
from .templates.tables import TableStructureProvider
from .variants import VariantRegistry
from .verification import quote_verified
from .voting import vote_field


class PipelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_fields_per_call: int = Field(default=10, strict=True, gt=0)  # E3.1
    window_chars: int = Field(default=4_000, strict=True, gt=0)
    section_target_chars: int = Field(default=2_000, strict=True, gt=0)
    transport_attempts: int = Field(default=3, strict=True, gt=0)  # E1.2（可配）
    backoff_base_s: float = Field(
        default=1.0, strict=True, ge=0, allow_inf_nan=False
    )
    gapfill_top_n: int = Field(default=3, strict=True, gt=0)
    # 024 E3：补漏 LLM 调用总预算（None=不限）；并发下原子扣减（单事件循环内
    # 预约后再 await，不存在两任务同看余额的窗口）
    gapfill_max_calls: int | None = Field(default=None, strict=True, ge=0)
    # 024 E7：变体注册表与实验分桶策略由此注入（节点不得各自取全局默认）
    variant_registry: VariantRegistry = Field(default_factory=VariantRegistry.default)
    assignment: AssignmentPolicy = Field(default_factory=AssignmentPolicy)
    concurrency: int = Field(default=6, strict=True, gt=0)
    judge_mode: str = "claude-session"
    model_profile: Literal["disabled", "production", "offline-eval", "replay"] = (
        "disabled"
    )


@dataclass(frozen=True, slots=True)
class _ProductionPipelineState:
    """Code-owned runtime snapshot; caller-visible attributes are non-authoritative."""

    client: ModelClient
    registry: SchemaRegistry
    model_id: str
    config: PipelineConfig
    scope: KnowledgeScope


_PRODUCTION_PIPELINE_STATES: WeakKeyDictionary[object, _ProductionPipelineState] = (
    WeakKeyDictionary()
)
_PRODUCTION_PIPELINE_LOCK = RLock()


def _production_pipeline_state(value: object) -> _ProductionPipelineState | None:
    with _PRODUCTION_PIPELINE_LOCK:
        return _PRODUCTION_PIPELINE_STATES.get(value)


def _register_production_pipeline(
    value: object,
    *,
    client: ModelClient,
    registry: SchemaRegistry,
    model_id: str,
    config: PipelineConfig,
    scope: KnowledgeScope,
) -> None:
    state = _ProductionPipelineState(
        client=client,
        registry=registry.model_copy(deep=True),
        model_id=model_id,
        config=config.model_copy(deep=True),
        scope=scope.model_copy(deep=True),
    )
    with _PRODUCTION_PIPELINE_LOCK:
        _PRODUCTION_PIPELINE_STATES[value] = state


class PipelineState(TypedDict, total=False):
    product_dir: str
    run_dir: str
    checkpoint_path: str
    run_id: str
    line_key: str
    product_id: str
    product_name: str
    model_id: str
    schema_version: str
    prompt_version: str
    variant_digest: str
    gapfill_calls_used: int
    judge_mode: str
    fail_nodes: list[str]  # 测试用注入失败节点（E1.1 用例）
    source_documents: list[dict[str, Any]]
    docs: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    dead_letters: list[dict[str, Any]]
    judge_queue: list[dict[str, Any]]
    manifest: dict[str, Any]


class RunResult(BaseModel):
    manifest: RunManifest
    records: list[PredRecord] = Field(default_factory=list)
    pred_path: Path
    manifest_path: Path
    judge_queue_path: Path


@dataclass(frozen=True, slots=True)
class RunArtifactCommitCandidate:
    """Exact staged bytes presented to an optional precommit admission gate."""

    pred: bytes
    manifest: bytes
    judge_queue: bytes
    dead_letters: bytes


class _RunIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    run_dir: str
    checkpoint_path: str
    product_dir: str
    product_id: str
    product_name: str
    line_key: str
    model_id: str
    schema_version: str
    prompt_version: str
    judge_mode: str
    variant_digest: str = ""


_DOC_PRIORITY = ("保险条款", "条款", "产品说明书", "说明书")  # 合并时的来源优先级
_RUNTIME_SOURCE_PATHS: ContextVar[Mapping[str, Path] | None] = ContextVar(
    "insurance_harness_compiler_source_paths", default=None
)
_RUNTIME_SOURCE_DOCUMENTS: ContextVar[tuple[SourceDocument, ...] | None] = ContextVar(
    "insurance_harness_compiler_source_documents", default=None
)
_GRAPH_NODE_NAMES = frozenset(
    {"load", "split_route", "extract", "gapfill", "vote", "finalize"}
)
_STATE_PATCH_KEYS = frozenset({"fail_nodes"})
_SCHEMA_FACT_DOMAIN = b"insurancekb.compiler.schema-registry.v1\0"


def _compiler_schema_hash(registry: SchemaRegistry) -> str:
    """Content address the exact code-owned schema bytes used by this pipeline."""

    payload = json.dumps(
        registry.model_dump(mode="json", round_trip=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(_SCHEMA_FACT_DOMAIN + payload).hexdigest()


def _doc_rank(doc: str) -> int:
    for i, kw in enumerate(_DOC_PRIORITY):
        if kw in doc:
            return i
    return len(_DOC_PRIORITY)


def merge_candidates(cands: list[FieldCandidate]) -> dict[str, FieldCandidate]:
    """按 field_id 合并多 (doc, window) 候选：present>absent>unknown、
    judge>semantic_resolve>vote>gapfill>fastpath>extract、证据多/值长者优先、条款优先于说明书。

    semantic_resolve 是对确定性候选的 LLM 裁决；原始 fastpath 候选不会直接出场。"""
    tri_rank = {"present": 0, "absent_explicitly": 1, "unknown": 2}
    origin_rank = {
        "judge": 0,
        "semantic_resolve": 1,
        "vote": 2,
        "gapfill": 3,
        "fastpath": 4,
        "extract": 5,
    }

    def rank(c: FieldCandidate) -> tuple[int, int, int, int, int, int]:
        return (
            tri_rank[c.tri_state],
            origin_rank[c.origin],
            0 if c.pending_judge else 1,  # 在途裁决必须在 pred 中显性可见
            _doc_rank(c.doc),
            -len(c.evidence),
            -len(c.value or ""),
        )

    best: dict[str, FieldCandidate] = {}
    for c in cands:
        cur = best.get(c.field_id)
        if cur is None or rank(c) < rank(cur):
            best[c.field_id] = c
    # E7（codex PR#13 阻断2）：merge 不再按注册表 membership 补盖变体标签——
    # prompt_variant_used 只在真实使用处记录（gapfill/fastpath），其余路径在
    # _to_pred 按 origin 如实落 baseline（首轮/vote/judge 都经 baseline prompt）。
    return best


def _maybe_fail(node: str, state: PipelineState) -> None:
    if node in (state.get("fail_nodes") or []):
        raise RuntimeError(f"注入失败：节点 {node}（E1.1 测试用）")


class ExtractionPipeline:
    def __getattribute__(self, name: str) -> Any:
        if name in {"_client", "_registry", "_model_id", "_cfg", "_scope", "_judge"}:
            state = _production_pipeline_state(self)
            if state is not None:
                if name == "_client":
                    return state.client
                if name == "_registry":
                    return state.registry.model_copy(deep=True)
                if name == "_model_id":
                    return state.model_id
                if name == "_cfg":
                    return state.config.model_copy(deep=True)
                if name == "_scope":
                    return state.scope.model_copy(deep=True)
                return JudgeDispatcher(mode="guarded", client=state.client)
        return object.__getattribute__(self, name)

    def __init__(
        self,
        client: ModelClient,
        registry: SchemaRegistry,
        model_id: str,
        source: DocumentSource[Any],
        config: PipelineConfig | None = None,
        judge: JudgeDispatcher | None = None,
        sleep: Sleeper | None = None,
        template_registry: TemplateRegistry | None = None,
        table_provider: TableStructureProvider | None = None,
        scope: KnowledgeScope | None = None,
        baseline_admission_identity: BaselineAdmissionIdentity | None = None,
        precommit_validator: Callable[[RunArtifactCommitCandidate], None] | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._model_id = model_id
        resolved_config = config or PipelineConfig()
        self._cfg = resolved_config
        if resolved_config.model_profile == "production":
            if resolved_config.judge_mode != "guarded":
                raise ProductionEntrypointDenied("invalid_production_judge")
            scope_fields = scope_log_context(scope) if scope is not None else {}
            _require_production_compiler_client(
                client,
                schema_hash=_compiler_schema_hash(registry),
                model_id=model_id,
                space_id=scope_fields.get("space_id"),
            )
            if judge is not None:
                raise ValueError("production judge is built only by composition root")
            self._judge = JudgeDispatcher(mode="guarded", client=client)
        elif resolved_config.model_profile == "disabled":
            raise ProductionEntrypointDenied("invalid_production_client")
        else:
            self._judge = judge or JudgeDispatcher(mode=resolved_config.judge_mode)
        self._sleep: Sleeper = sleep if sleep is not None else asyncio.sleep
        self._source = source
        # 006 F3：模板注册表未提供/为空 → fast path 整体旁路（004 行为不变）
        self._templates = template_registry
        self._table_provider = table_provider
        self._scope = scope
        if baseline_admission_identity is not None and precommit_validator is None:
            raise ValueError(
                "baseline admission identity requires a precommit validator"
            )
        self._baseline_admission_identity = baseline_admission_identity
        self._precommit_validator = precommit_validator
        if scope is not None:
            scope_log_context(scope)
        if resolved_config.model_profile == "production":
            if scope is None:
                raise ProductionEntrypointDenied("invalid_production_client")
            _register_production_pipeline(
                self,
                client=client,
                registry=registry,
                model_id=model_id,
                config=resolved_config,
                scope=scope,
            )

    # --- 节点 ---

    def _line(self, state: PipelineState) -> ProductLineSchema:
        return self._registry.line(state["line_key"])

    def _attempt_ledger(self, state: PipelineState) -> SqliteAttemptLedger:
        return SqliteAttemptLedger(
            Path(state["run_dir"]) / "llm-attempts.sqlite",
            run_id=state["run_id"],
        )

    def _require_manifest_scope(self, raw_manifest: object) -> RunManifest:
        manifest = _parse_run_manifest(raw_manifest)
        if manifest is None:
            raise ScopeViolation("scope mismatch")
        if self._scope is None:
            expected = {"space_id": "", "tenant_id": "", "raw_kb_id": ""}
        else:
            expected = scope_log_context(self._scope)
        actual = {
            "space_id": manifest.space_id,
            "tenant_id": manifest.tenant_id,
            "raw_kb_id": manifest.raw_kb_id,
        }
        if actual != expected:
            raise ScopeViolation("scope mismatch")
        return manifest

    async def _require_checkpoint_identity(
        self,
        app: Any,
        config: dict[str, Any],
        documents: tuple[SourceDocument, ...],
        identity: _RunIdentity,
        *,
        resume: bool,
    ) -> None:
        snapshot = await app.aget_state(config)
        values = snapshot.values
        if not values:
            if resume:
                raise ScopeViolation("run identity mismatch")
            return
        if not resume:
            raise ScopeViolation("run identity mismatch")
        if not isinstance(values, dict) or "manifest" not in values:
            raise ScopeViolation("run identity mismatch")
        manifest = self._require_manifest_sources(values["manifest"], documents)
        if _checkpoint_source_identities(values.get("source_documents")) != [
            _source_document_identity(document) for document in documents
        ]:
            raise ScopeViolation("source identity mismatch")
        if (
            _parse_state_run_identity(values) != identity
            or _manifest_run_identity(manifest) != identity
        ):
            raise ScopeViolation("run identity mismatch")

    def _require_manifest_sources(
        self,
        raw_manifest: object,
        documents: tuple[SourceDocument, ...],
    ) -> RunManifest:
        manifest = self._require_manifest_scope(raw_manifest)
        expected = [_source_document_identity(document)[:8] for document in documents]
        actual = [
            (
                entry.doc,
                entry.source_id,
                entry.knowledge_id,
                entry.source_revision,
                source_ordering_identity_token(entry.ordering),
                entry.file_hash,
                entry.original_digest,
                entry.parser_fingerprint,
            )
            for entry in manifest.docs
        ]
        if not actual or actual != expected:
            raise ScopeViolation("source identity mismatch")
        return manifest

    def _require_materialized_scope(
        self,
        documents: tuple[SourceDocument, ...],
    ) -> None:
        file_names = [document.file_name for document in documents]
        if len(file_names) != len(set(file_names)):
            raise ScopeViolation("source identity mismatch")
        if self._scope is None:
            if any(
                document.scope is not None
                or document.knowledge_id is not None
                or document.raw_kb_id is not None
                for document in documents
            ):
                raise ScopeViolation("scope mismatch")
            return
        expected = (
            self._scope.space_id,
            self._scope.tenant_id,
            self._scope.raw_kb_id,
            self._scope.wiki_kb_id,
        )
        for document in documents:
            source_scope = document.scope
            if (
                source_scope is None
                or not document.knowledge_id
                or not document.raw_kb_id
                or document.raw_kb_id != self._scope.raw_kb_id
            ):
                raise ScopeViolation("scope mismatch")
            if (
                source_scope.space_id,
                source_scope.tenant_id,
                source_scope.raw_kb_id,
                source_scope.wiki_kb_id,
            ) != expected:
                raise ScopeViolation("scope mismatch")

    def _canonicalize_state_patch(
        self,
        state_patch: dict[str, Any],
    ) -> dict[str, Any]:
        if not set(state_patch).issubset(_STATE_PATCH_KEYS):
            raise ScopeViolation("state patch mismatch")
        canonical: dict[str, Any] = {}
        if "fail_nodes" in state_patch:
            fail_nodes = state_patch["fail_nodes"]
            if not isinstance(fail_nodes, list) or any(
                type(node) is not str or node not in _GRAPH_NODE_NAMES
                for node in fail_nodes
            ):
                raise ScopeViolation("state patch mismatch")
            canonical["fail_nodes"] = list(fail_nodes)
        return canonical

    def _resolve_run_identity(
        self,
        *,
        run_dir: Path,
        checkpoint_path: Path | None,
        product_dir: Path | None,
        product_id: str | None,
        product_name: str | None,
        line_key: str | None,
        thread_id: str | None,
    ) -> _RunIdentity:
        from ..goldenset.runner import infer_line_key
        from ..goldenset.verify import load_product_meta

        canonical_run_dir = run_dir.expanduser().resolve()
        canonical_checkpoint_path = (
            checkpoint_path.expanduser().resolve()
            if checkpoint_path is not None
            else canonical_run_dir / "checkpoint.sqlite"
        )
        canonical_product_dir = (
            None if product_dir is None else product_dir.expanduser().resolve()
        )
        explicit_product_id = (product_id or "").strip()
        explicit_product_name = (product_name or "").strip()
        if canonical_product_dir is None and (
            not explicit_product_id or not explicit_product_name
        ):
            raise ValueError("product_id and product_name are required without product_dir")
        if (explicit_product_id and not explicit_product_name) or (
            explicit_product_name and not explicit_product_id
        ):
            raise ValueError("product_id and product_name must be provided together")
        resolved_product_id = explicit_product_id
        resolved_product_name = explicit_product_name
        if not resolved_product_id or not resolved_product_name:
            assert canonical_product_dir is not None
            resolved_product_name = canonical_product_dir.name
            meta = load_product_meta(canonical_product_dir)
            resolved_product_id = str(
                meta.get("planCode") or resolved_product_name
            ).strip()
        resolved_line_key = (line_key or "").strip() or infer_line_key(
            resolved_product_name
        )
        self._registry.line(resolved_line_key)
        default_run_id = (
            explicit_product_id
            or (
                canonical_product_dir.name
                if canonical_product_dir is not None
                else resolved_product_id
            )
        )
        resolved_run_id = (thread_id or "").strip() or default_run_id
        return _RunIdentity(
            run_id=resolved_run_id,
            run_dir=str(canonical_run_dir),
            checkpoint_path=str(canonical_checkpoint_path),
            product_dir=(
                "" if canonical_product_dir is None else str(canonical_product_dir)
            ),
            product_id=resolved_product_id,
            product_name=resolved_product_name,
            line_key=resolved_line_key,
            model_id=self._model_id,
            schema_version=self._registry.version,
            prompt_version=PROMPT_VERSION,
            judge_mode=self._judge.mode,
            variant_digest=experiment_digest(
                self._cfg.variant_registry, self._cfg.assignment
            ),
        )

    async def _node_load(self, state: PipelineState) -> dict[str, Any]:
        # 延迟导入：goldenset 包 __init__ 会加载 annotator（其依赖 compiler.llm），
        # 模块级互相导入会成环（annotator→compiler→pipeline→goldenset）
        from ..goldenset.runner import infer_line_key
        from ..goldenset.verify import load_product_meta

        _maybe_fail("load", state)
        product_dir_raw = state.get("product_dir", "")
        product_dir = Path(product_dir_raw) if product_dir_raw else None
        product_name = state.get("product_name", "").strip()
        product_id = state.get("product_id", "").strip()
        if not product_name or not product_id:
            if product_dir is None:
                raise ScopeViolation("source identity mismatch")
            product_name = product_dir.name
            meta = load_product_meta(product_dir)
            product_id = str(meta.get("planCode") or product_name).strip()
        line_key = state.get("line_key") or infer_line_key(product_name)
        runtime_documents = _RUNTIME_SOURCE_DOCUMENTS.get()
        if runtime_documents is None:
            source_documents = [
                SourceDocument.model_validate(raw) for raw in state["source_documents"]
            ]
        else:
            source_documents = list(runtime_documents)
            if _checkpoint_source_identities(state.get("source_documents")) != [
                _source_document_identity(document) for document in source_documents
            ]:
                raise ScopeViolation("source identity mismatch")
        file_names = [document.file_name for document in source_documents]
        if len(file_names) != len(set(file_names)):
            raise ScopeViolation("source identity mismatch")
        docs: list[dict[str, Any]] = []
        dead: list[dict[str, Any]] = list(state.get("dead_letters") or [])
        for document in source_documents:
            docs.append(
                DocPayload(doc=document.file_name, pages=list(document.pages)).model_dump(
                    mode="json"
                )
            )
        scope_fields = scope_log_context(self._scope) if self._scope is not None else {}
        manifest = RunManifest(
            run_id=state["run_id"],
            product_dir=product_dir_raw,
            run_dir=state.get("run_dir", ""),
            checkpoint_path=state.get("checkpoint_path", ""),
            space_id=scope_fields.get("space_id", ""),
            tenant_id=scope_fields.get("tenant_id", ""),
            raw_kb_id=scope_fields.get("raw_kb_id", ""),
            product_id=product_id,
            product_name=product_name,
            line_key=line_key,
            schema_version=state.get("schema_version", self._registry.version),
            model_id=state.get("model_id", self._model_id),
            judge_mode=state.get("judge_mode", self._judge.mode),
            prompt_version=state.get("prompt_version", PROMPT_VERSION),
            variant_digest=state.get(
                "variant_digest",
                experiment_digest(self._cfg.variant_registry, self._cfg.assignment),
            ),
            started_at=datetime.now(UTC),
            docs=[
                DocManifestEntry(
                    doc=document.file_name,
                    source_id=document.source_id,
                    knowledge_id=document.knowledge_id,
                    source_revision=document.source_revision.value,
                    ordering=document.source_revision.ordering,
                    file_hash=document.source_revision.file_hash,
                    original_digest=document.original_digest,
                    parser_fingerprint=document.source_revision.parser_fingerprint,
                    doc_pages=len(document.pages),
                )
                for document in source_documents
            ],
            baseline_admission=self._baseline_admission_identity,
        )
        return {
            "product_id": product_id,
            "product_name": product_name,
            "line_key": line_key,
            "docs": docs,
            "dead_letters": dead,
            "manifest": manifest.model_dump(mode="json"),
        }

    async def _node_split_route(self, state: PipelineState) -> dict[str, Any]:
        _maybe_fail("split_route", state)
        manifest = self._require_manifest_scope(state.get("manifest"))
        docs: list[dict[str, Any]] = []
        manifest_by_doc = {entry.doc: entry for entry in manifest.docs}
        for raw in state["docs"]:
            payload = DocPayload.model_validate(raw)
            sections = split_sections(
                payload.pages, target_chars=self._cfg.section_target_chars, min_chars=0
            )
            routing = route_groups(sections)
            payload.sections = sections
            payload.by_group = {g: list(ids) for g, ids in routing.by_group.items()}
            payload.family_id = family_fingerprint(sections)
            # 006 F4.2：可喂性评分记入 manifest（只报告不拦截；硬门禁待升级链 L1+）
            feed = score_feedability(payload.doc, payload.pages)
            entry = manifest_by_doc.get(payload.doc)
            if entry is None:
                raise ScopeViolation("source identity mismatch")
            manifest_by_doc[payload.doc] = entry.model_copy(
                update={
                    "doc_pages": len(payload.pages),
                    "sections": len(sections),
                    "family_id": payload.family_id,
                    "routed_pairs": routing.routed_pairs,
                    "total_pairs": routing.total_pairs,
                    "compression_ratio": routing.compression_ratio,
                    "feedability_score": feed.score,
                    "feedability_ok": feed.feedable,
                }
            )
            docs.append(payload.model_dump(mode="json"))
        manifest.docs = [manifest_by_doc[entry.doc] for entry in manifest.docs]
        return {"docs": docs, "manifest": manifest.model_dump(mode="json")}

    async def _node_extract(self, state: PipelineState) -> dict[str, Any]:
        _maybe_fail("extract", state)
        manifest = self._require_manifest_scope(state.get("manifest"))
        line = self._line(state)
        stats = CallStats()
        metered = MeteredClient(self._client, stats)
        ledger = self._attempt_ledger(state)
        sem = asyncio.Semaphore(self._cfg.concurrency)
        candidates: list[FieldCandidate] = []
        dead: list[DeadLetter] = [
            DeadLetter.model_validate(d) for d in state.get("dead_letters") or []
        ]

        async def do_window(
            extractor: WindowExtractor,
            window: Window,
            fields: list[FieldSpec],
            doc: str,
            group: str,
        ) -> list[FieldCandidate]:
            async with sem:
                try:
                    return await with_transport_retry(
                        lambda: extractor.extract(window, fields),
                        attempts=self._cfg.transport_attempts,
                        base_delay_s=self._cfg.backoff_base_s,
                        sleep=self._sleep,
                    )
                except TransportRetryError as exc:  # 死信，不中断其他字段组（E1.2）
                    dead.append(
                        DeadLetter(
                            product=state["product_name"], doc=doc, group=group,
                            window_ref=window.ref, field_ids=[f.field_id for f in fields],
                            error=str(exc), attempts=self._cfg.transport_attempts,
                        )
                    )
                    return [
                        FieldCandidate(
                            field_id=f.field_id, field_name=f.name, group=group,
                            doc=doc, tri_state="unknown", unknown_reason="dead_letter",
                        )
                        for f in fields
                    ]

        # 006 F3 + Mission 136：fast path 只产生候选；候选汇总后统一交给 LLM
        # 语义裁决，不能再因为规则命中而直接成为最终字段值。
        fastpath_covered: set[str] = set()
        if self._templates is not None:
            fields_by_id = {f.field_id: f for f in line.extractable_fields}
            fastpath_candidates: list[FieldCandidate] = []
            pages_by_doc: dict[str, list[PageText]] = {}
            for raw in state["docs"]:
                payload = DocPayload.model_validate(raw)
                pages_by_doc[payload.doc] = payload.pages
                template = self._templates.find(payload.family_id, payload.doc)
                if template is None:
                    continue
                entries = [entry for entry in manifest.docs if entry.doc == payload.doc]
                runtime_paths = _RUNTIME_SOURCE_PATHS.get()
                if len(entries) != 1 or runtime_paths is None:
                    raise ScopeViolation("source identity mismatch")
                runtime_path = runtime_paths.get(entries[0].source_id)
                if runtime_path is None:
                    raise ScopeViolation("source identity mismatch")
                fp_cands = run_fastpath(
                    template,
                    fields_by_id,
                    payload.doc,
                    payload.pages,
                    pdf_path=runtime_path,
                    provider=self._table_provider,
                    sections=payload.sections,
                )
                fastpath_candidates.extend(fp_cands)
                for entry in manifest.docs:
                    if entry.doc == payload.doc:
                        entry.fastpath_fields = len(fp_cands)
            by_field: dict[str, list[FieldCandidate]] = {}
            for candidate in fastpath_candidates:
                by_field.setdefault(candidate.field_id, []).append(candidate)
            for field_id, field_candidates in by_field.items():
                field = fields_by_id[field_id]
                resolved = await resolve_candidates(
                    metered,
                    state["product_name"],
                    field,
                    field_candidates,
                    pages_by_doc,
                    ledger=ledger,
                )
                candidates.append(resolved)
                # 只有语义裁决成功的字段才退出通用抽取；失败字段仍可由通用
                # 抽取/补漏恢复，原始规则候选不会成为最终值。
                if resolved.tri_state != "unknown":
                    fastpath_covered.add(field_id)
            manifest.template_registry_version = self._templates.version
            manifest.fastpath_fields = len(fastpath_covered)

        tasks: list[asyncio.Task[list[FieldCandidate]]] = []
        for raw in state["docs"]:
            payload = DocPayload.model_validate(raw)
            sec_by_id = {s.section_id: s for s in payload.sections}
            extractor = WindowExtractor(
                metered, state["product_name"], payload.doc, payload.pages,
                max_fields_per_call=self._cfg.max_fields_per_call,
                ledger=ledger,
            )
            for group in GROUP_ORDER:
                fields = [
                    f
                    for f in line.extractable_fields
                    if group_of_field(f.name) == group and f.field_id not in fastpath_covered
                ]
                sec_ids = payload.by_group.get(group, [])
                if not fields or not sec_ids:
                    continue
                windows = build_windows(
                    [(sid, sec_by_id[sid].fragments) for sid in sec_ids],
                    window_chars=self._cfg.window_chars,
                )
                for window in windows:
                    tasks.append(
                        asyncio.ensure_future(
                            do_window(extractor, window, fields, payload.doc, group)
                        )
                    )
        for chunk in await asyncio.gather(*tasks):
            candidates.extend(chunk)

        manifest.stats = _merge_stats(manifest.stats, stats)
        return {
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "dead_letters": [d.model_dump(mode="json") for d in dead],
            "manifest": manifest.model_dump(mode="json"),
        }

    async def _node_gapfill(self, state: PipelineState) -> dict[str, Any]:
        _maybe_fail("gapfill", state)
        manifest = self._require_manifest_scope(state.get("manifest"))
        line = self._line(state)
        stats = CallStats()
        metered = MeteredClient(self._client, stats)
        ledger = self._attempt_ledger(state)
        candidates = [FieldCandidate.model_validate(c) for c in state.get("candidates") or []]
        merged = merge_candidates(candidates)
        payloads = [DocPayload.model_validate(raw) for raw in state["docs"]]
        section_pool = [(p.doc, s) for p in payloads for s in p.sections]
        pages_by_doc: dict[str, list[PageText]] = {p.doc: p.pages for p in payloads}
        sem = asyncio.Semaphore(self._cfg.concurrency)

        # 024 E3：SQLite reservation commits before every outbound call. The ledger,
        # not checkpoint state, is the budget authority and survives a hard crash.
        ledger.ensure_budget("gapfill", self._cfg.gapfill_max_calls)
        used = ledger.used("gapfill")
        checkpoint_used = int(state.get("gapfill_calls_used") or 0)
        if checkpoint_used > used:
            # A pre-ledger or corrupted checkpoint cannot safely restore an
            # already-spent external-call budget. Refuse instead of resetting it.
            raise ScopeViolation("attempt ledger mismatch")
        remaining = (
            None
            if self._cfg.gapfill_max_calls is None
            else max(0, self._cfg.gapfill_max_calls - used)
        )

        async def do_field(field: FieldSpec) -> FieldCandidate | None:
            async with sem:
                prior = merged.get(field.field_id)
                arm = assign_arm(
                    self._cfg.assignment, state["product_id"], field.field_id
                )
                ledger.record_assignment(field.field_id, arm)
                try:
                    cand = await with_transport_retry(
                        lambda: gapfill_field(
                            metered, state["product_name"], field, section_pool,
                            pages_by_doc, top_n=self._cfg.gapfill_top_n,
                            registry=self._cfg.variant_registry, arm=arm,
                            ledger=ledger,
                            budget_limit=self._cfg.gapfill_max_calls,
                            source_pointer=(
                                prior.source_pointer if prior is not None else None
                            ),
                        ),
                        attempts=self._cfg.transport_attempts,
                        base_delay_s=self._cfg.backoff_base_s,
                        sleep=self._sleep,
                    )
                except GapfillBudgetExhausted:
                    return None  # 预算耗尽：后续字段不再出站（E3）
                except TransportRetryError:
                    return None
                return cand

        # E3 触发合同：字段属适用 schema（line 过滤）+ requiredness∈{required,
        # expected} + 首轮空/unknown/source_pointer + 预算允许（纯函数判定，金标零参与）；
        # 候选章节存在性由 gapfill_field 检索层裁定（无候选=零 LLM 调用零额度）。
        targets = [
            f
            for f in line.extractable_fields
            if gapfill_eligibility(
                f, merged.get(f.field_id), budget_remaining=remaining
            ).eligible
        ]
        results = await asyncio.gather(*(do_field(f) for f in targets))
        for cand in results:
            if cand is not None:
                candidates.append(cand)
        manifest.stats = _merge_stats(manifest.stats, stats)
        return {
            "gapfill_calls_used": ledger.used("gapfill"),
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "manifest": manifest.model_dump(mode="json"),
        }

    async def _node_vote(self, state: PipelineState) -> dict[str, Any]:
        _maybe_fail("vote", state)
        manifest = self._require_manifest_scope(state.get("manifest"))
        line = self._line(state)
        stats = CallStats()
        metered = MeteredClient(self._client, stats)
        ledger = self._attempt_ledger(state)
        candidates = [FieldCandidate.model_validate(c) for c in state.get("candidates") or []]
        dead = [DeadLetter.model_validate(d) for d in state.get("dead_letters") or []]
        merged = merge_candidates(candidates)
        payloads = {p.doc: p for p in (DocPayload.model_validate(r) for r in state["docs"])}
        judge_queue = list(state.get("judge_queue") or [])
        sem = asyncio.Semaphore(self._cfg.concurrency)

        async def do_vote(
            field: FieldSpec,
            cand: FieldCandidate,
        ) -> tuple[FieldCandidate, TransportRetryError | None]:
            async with sem:
                pages = payloads[cand.doc].pages if cand.doc in payloads else []
                try:
                    return (
                        await with_transport_retry(
                            lambda: vote_field(
                                metered, state["product_name"], field, cand, pages,
                                ledger=ledger,
                            ),
                            attempts=self._cfg.transport_attempts,
                            base_delay_s=self._cfg.backoff_base_s,
                            sleep=self._sleep,
                        ),
                        None,
                    )
                except TransportRetryError as exc:
                    return cand, exc

        async def dispatch_judge(
            request: JudgeRequest,
        ) -> tuple[Judgement | None, str | None, TransportRetryError | None]:
            try:
                judgement, attempt_id = await with_transport_retry(
                    lambda: self._judge.dispatch_audited(request, ledger=ledger),
                    attempts=self._cfg.transport_attempts,
                    base_delay_s=self._cfg.backoff_base_s,
                    sleep=self._sleep,
                )
            except TransportRetryError as exc:
                return None, None, exc
            return judgement, attempt_id, None

        def block_field(
            cand: FieldCandidate,
            *,
            stage: str,
            error: TransportRetryError,
        ) -> None:
            """Supersede every candidate for a failed verification field."""

            candidates[:] = [
                existing
                for existing in candidates
                if existing.field_id != cand.field_id
            ]
            candidates.append(
                cand.model_copy(
                    update={
                        "value": None,
                        "tri_state": "unknown",
                        "evidence": [],
                        "confidence": "low",
                        "unknown_reason": "dead_letter",
                        "pending_judge": False,
                    }
                )
            )
            dead.append(
                DeadLetter(
                    product=state["product_name"],
                    doc=cand.doc,
                    group=cand.group,
                    window_ref=f"{stage}:{cand.field_id}",
                    field_ids=[cand.field_id],
                    error=str(error),
                    attempts=self._cfg.transport_attempts,
                )
            )

        # 投票只对 risk_level=high 且已有 present 候选的字段发生（E4.2/E4.3）；
        # 已完成模板候选的语义裁决字段也退出投票；投票只补充尚未经过
        # LLM 语义选择的通用抽取结果（006 F3.4，12 #1）。
        vote_targets = [
            (f, merged[f.field_id])
            for f in line.extractable_fields
            if f.risk_level == "high"
            and f.field_id in merged
            and merged[f.field_id].tri_state == "present"
            and merged[f.field_id].origin not in {"fastpath", "semantic_resolve"}
        ]
        voted = await asyncio.gather(*(do_vote(f, c) for f, c in vote_targets))
        for (_field, _), (cand, vote_error) in zip(vote_targets, voted, strict=True):
            if vote_error is not None:
                block_field(cand, stage="vote", error=vote_error)
                continue
            if cand.vote_agreement == 1:  # 三票三样 → 裁决（E4.2）
                context = "\n".join(e.quote for e in cand.evidence)
                req = make_judge_request(
                    state["product_id"], state["product_name"], cand,
                    "vote_disagreement", context,
                )
                judgement, judge_attempt_id, judge_error = await dispatch_judge(req)
                if judge_error is not None:
                    block_field(cand, stage="judge", error=judge_error)
                    continue
                if judgement is None:
                    cand = cand.model_copy(update={"pending_judge": True})
                    judge_queue.append(req.model_dump(mode="json"))
                else:
                    meta = dict(cand.metadata)
                    if judge_attempt_id is not None:
                        meta["winning_attempt_id"] = judge_attempt_id
                    cand = cand.model_copy(
                        update={
                            "value": judgement.value,
                            "tri_state": judgement.tri_state,
                            "evidence": judgement.evidence,
                            "confidence": judgement.confidence,
                            "origin": "judge",
                            "metadata": meta,
                        }
                    )
            candidates.append(cand)

        # E3.2 高风险字段二次回验仍失败 → 裁决请求（不出场，但留裁决线索）
        for f in line.extractable_fields:
            cand2 = merged.get(f.field_id)
            if (
                cand2 is not None
                and f.risk_level == "high"
                and cand2.tri_state == "unknown"
                and cand2.unknown_reason == "quote_mismatch"
                and cand2.metadata.get("rejected_value") is not None
            ):
                req = make_judge_request(
                    state["product_id"], state["product_name"], cand2,
                    "quote_mismatch_high_risk", "",
                )
                judgement, judge_attempt_id, judge_error = await dispatch_judge(req)
                if judge_error is not None:
                    block_field(cand2, stage="judge", error=judge_error)
                    continue
                if judgement is None:
                    candidates.append(cand2.model_copy(update={"pending_judge": True}))
                    judge_queue.append(req.model_dump(mode="json"))
                else:
                    meta = dict(cand2.metadata)
                    if judge_attempt_id is not None:
                        meta["winning_attempt_id"] = judge_attempt_id
                    candidates.append(
                        cand2.model_copy(
                            update={
                                "value": judgement.value,
                                "tri_state": judgement.tri_state,
                                "evidence": judgement.evidence,
                                "confidence": judgement.confidence,
                                "origin": "judge",
                                "metadata": meta,
                            }
                        )
                    )

        manifest.stats = _merge_stats(manifest.stats, stats)
        return {
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "dead_letters": [d.model_dump(mode="json") for d in dead],
            "judge_queue": judge_queue,
            "manifest": manifest.model_dump(mode="json"),
        }

    async def _node_finalize(self, state: PipelineState) -> dict[str, Any]:
        _maybe_fail("finalize", state)
        manifest = self._require_manifest_scope(state.get("manifest"))
        runtime_documents = _RUNTIME_SOURCE_DOCUMENTS.get()
        documents_by_name: dict[str, SourceDocument] = {}
        if runtime_documents is not None:
            manifest = self._require_manifest_sources(
                state.get("manifest"), runtime_documents
            )
            documents_by_name = {
                document.file_name: document for document in runtime_documents
            }
        line = self._line(state)
        ledger = self._attempt_ledger(state)
        candidates = [FieldCandidate.model_validate(c) for c in state.get("candidates") or []]
        merged = merge_candidates(candidates)
        created = datetime.now(UTC)
        records: list[PredRecord] = []
        for f in line.extractable_fields:
            cand = merged.get(f.field_id)
            if cand is None:
                cand = FieldCandidate(
                    field_id=f.field_id, field_name=f.name,
                    group=group_of_field(f.name), doc="", tri_state="unknown",
                )
            audit_metadata = dict(cand.metadata)
            durable_attempts = ledger.attempts_for_field(f.field_id)
            legacy_attempts = audit_metadata.get("attempts")
            if isinstance(legacy_attempts, list) and legacy_attempts and not durable_attempts:
                raise ScopeViolation("attempt ledger mismatch")
            audit_metadata["attempts"] = [
                attempt.model_dump() for attempt in durable_attempts
            ]
            assignment = ledger.assignment_for_field(f.field_id)
            if assignment is not None:
                audit_metadata["variant_assignment"] = assignment
            document = documents_by_name.get(cand.doc)
            cand = cand.model_copy(
                update={
                    "evidence": _source_aware_evidence(cand, document),
                    "metadata": audit_metadata,
                }
            )
            records.append(_to_pred(cand, state, self._model_id, manifest, created))

        manifest.dead_letters = [
            DeadLetter.model_validate(d) for d in state.get("dead_letters") or []
        ]
        manifest.pending_judge_count = sum(1 for r in records if r.pending_judge)
        manifest.finished_at = datetime.now(UTC)
        if manifest.started_at is not None:
            manifest.duration_s = (manifest.finished_at - manifest.started_at).total_seconds()

        run_dir = Path(state["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        _commit_run_artifacts(
            run_dir=run_dir,
            pred_text="".join(
                record.model_dump_json() + "\n" for record in records
            ),
            manifest_text=manifest.model_dump_json(indent=2),
            judge_requests=[
                JudgeRequest.model_validate(j)
                for j in state.get("judge_queue") or []
            ],
            dead_letter_text="".join(
                dead.model_dump_json() + "\n" for dead in manifest.dead_letters
            ),
            precommit_validator=self._precommit_validator,
        )
        return {"manifest": manifest.model_dump(mode="json")}

    # --- 编排 ---

    def _build(self, checkpointer: AsyncSqliteSaver) -> Any:
        g: StateGraph[PipelineState] = StateGraph(PipelineState)
        g.add_node("load", self._node_load)
        g.add_node("split_route", self._node_split_route)
        g.add_node("extract", self._node_extract)
        g.add_node("gapfill", self._node_gapfill)
        g.add_node("vote", self._node_vote)
        g.add_node("finalize", self._node_finalize)
        g.add_edge(START, "load")
        g.add_edge("load", "split_route")
        g.add_edge("split_route", "extract")
        g.add_edge("extract", "gapfill")
        g.add_edge("gapfill", "vote")
        g.add_edge("vote", "finalize")
        g.add_edge("finalize", END)
        return g.compile(checkpointer=checkpointer)

    @asynccontextmanager
    async def _materialize_locked_run(
        self,
        *,
        run_dir: Path,
        source_request: BaseModel,
        resume: bool,
    ) -> AsyncIterator[MaterializedBatch]:
        async with _exclusive_run_directory(run_dir):
            if not resume and (run_dir / "manifest.json").is_file():
                raise ScopeViolation("run identity mismatch")
            async with self._source.materialize(source_request) as batch:
                yield batch

    async def run(
        self,
        run_dir: Path,
        source_request: BaseModel,
        product_dir: Path | None = None,
        product_id: str | None = None,
        product_name: str | None = None,
        line_key: str | None = None,
        thread_id: str | None = None,
        checkpoint_path: Path | None = None,
        resume: bool = False,
        fail_nodes: list[str] | None = None,
        state_patch: dict[str, Any] | None = None,
    ) -> RunResult:
        """执行（或续跑）一个产品的抽取 run；checkpoint 落 SQLite（E1.1）。"""
        identity = self._resolve_run_identity(
            run_dir=run_dir,
            checkpoint_path=checkpoint_path,
            product_dir=product_dir,
            product_id=product_id,
            product_name=product_name,
            line_key=line_key,
            thread_id=thread_id,
        )
        canonical_run_dir = Path(identity.run_dir)
        canonical_run_dir.mkdir(parents=True, exist_ok=True)
        ckpt = Path(identity.checkpoint_path)
        async with self._materialize_locked_run(
            run_dir=canonical_run_dir,
            source_request=source_request,
            resume=resume,
        ) as batch:
            self._require_materialized_scope(batch.documents)
            runtime_token = _RUNTIME_SOURCE_PATHS.set(batch.local_paths)
            document_token = _RUNTIME_SOURCE_DOCUMENTS.set(batch.documents)
            try:
                async with aiosqlite.connect(str(ckpt)) as conn:
                    saver = AsyncSqliteSaver(conn)
                    app = self._build(saver)
                    config = {"configurable": {"thread_id": identity.run_id}}
                    await self._require_checkpoint_identity(
                        app,
                        config,
                        batch.documents,
                        identity,
                        resume=resume,
                    )
                    if state_patch:
                        canonical_patch = self._canonicalize_state_patch(state_patch)
                        await app.aupdate_state(config, canonical_patch)
                        await self._require_checkpoint_identity(
                            app,
                            config,
                            batch.documents,
                            identity,
                            resume=True,
                        )
                    initial: PipelineState | None
                    if resume:
                        initial = None
                    else:
                        initial = cast(
                            PipelineState,
                            {
                                **identity.model_dump(),
                                "fail_nodes": fail_nodes or [],
                                "source_documents": [
                                    document.model_dump(mode="json")
                                    for document in batch.documents
                                ],
                            },
                        )
                    out = cast(PipelineState, await app.ainvoke(initial, config=config))
                    if not isinstance(out, dict):
                        raise ScopeViolation("scope mismatch")
                    manifest = self._require_manifest_scope(out.get("manifest"))
                    if _manifest_run_identity(manifest) != identity:
                        raise ScopeViolation("run identity mismatch")
            finally:
                _RUNTIME_SOURCE_DOCUMENTS.reset(document_token)
                _RUNTIME_SOURCE_PATHS.reset(runtime_token)
            manifest = self._require_manifest_scope(manifest)
            pred_path = canonical_run_dir / "pred.jsonl"
            if not (canonical_run_dir / "manifest.json").is_file():
                raise ScopeViolation("artifact commit mismatch")
            records = [
                PredRecord.model_validate_json(line)
                for line in pred_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return RunResult(
                manifest=manifest,
                records=records,
                pred_path=pred_path,
                manifest_path=canonical_run_dir / "manifest.json",
                judge_queue_path=canonical_run_dir / "judge-queue.jsonl",
            )


@asynccontextmanager
async def _exclusive_run_directory(run_dir: Path) -> AsyncIterator[None]:
    run_descriptor: int | None = None
    file_descriptor: int | None = None
    acquired = False
    try:
        validation_failed = False
        try:
            run_descriptor = os.open(
                run_dir,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            run_metadata = os.fstat(run_descriptor)
            if (
                not stat.S_ISDIR(run_metadata.st_mode)
                or run_metadata.st_uid != os.geteuid()
                or run_metadata.st_mode & 0o022
            ):
                validation_failed = True
            if not validation_failed:
                file_descriptor = os.open(
                    ".run.lock",
                    os.O_CREAT
                    | os.O_RDWR
                    | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    0o600,
                    dir_fd=run_descriptor,
                )
                lock_metadata = os.fstat(file_descriptor)
                if (
                    not stat.S_ISREG(lock_metadata.st_mode)
                    or lock_metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(lock_metadata.st_mode) != 0o600
                    or lock_metadata.st_nlink != 1
                ):
                    validation_failed = True
        except OSError:
            validation_failed = True
        if validation_failed or file_descriptor is None:
            raise RuntimeError("run directory lock is unsafe") from None
        while not acquired:
            try:
                fcntl.flock(
                    file_descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                acquired = True
            except BlockingIOError:
                await asyncio.sleep(0.01)
        yield
    finally:
        if acquired and file_descriptor is not None:
            fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        if file_descriptor is not None:
            os.close(file_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)


@asynccontextmanager
async def run_settlement_guard(run_dir: Path) -> AsyncIterator[None]:
    """Hold the run's validated ``.run.lock`` across final validation and settle."""

    async with _exclusive_run_directory(run_dir):
        yield


def _commit_run_artifacts(
    *,
    run_dir: Path,
    pred_text: str,
    manifest_text: str,
    judge_requests: list[JudgeRequest],
    dead_letter_text: str,
    precommit_validator: Callable[[RunArtifactCommitCandidate], None] | None = None,
) -> None:
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".artifacts-", suffix=".staging", dir=run_dir)
    )
    artifact_names = (
        "pred.jsonl",
        "judge-queue.jsonl",
        "dead-letters.jsonl",
        "manifest.json",
    )
    data_artifact_names = artifact_names[:-1]
    manifest_name = artifact_names[-1]
    failed = False
    readback_failed = False
    staging_cleanup_failed = False
    control_flow_error: BaseException | None = None
    commit_started = False

    def fsync_file(path: Path) -> None:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def fsync_run_directory() -> None:
        descriptor = os.open(
            run_dir,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def remove_committed_targets(*, best_effort: bool) -> None:
        manifest_retired = True
        try:
            (run_dir / manifest_name).unlink(missing_ok=True)
        except OSError:
            manifest_retired = False
            if not best_effort:
                raise
        try:
            fsync_run_directory()
        except OSError:
            manifest_retired = False
            if not best_effort:
                raise

        # Never remove data while an old commit marker may still be durable. A
        # later retry can clear it safely; deleting data first would let that
        # marker claim an incomplete run after a crash.
        if not manifest_retired:
            return

        for name in data_artifact_names:
            try:
                (run_dir / name).unlink(missing_ok=True)
            except OSError:
                if not best_effort:
                    raise
        try:
            fsync_run_directory()
        except OSError:
            if not best_effort:
                raise

    try:
        try:
            (staging_dir / "pred.jsonl").write_text(pred_text, encoding="utf-8")
            write_judge_queue(staging_dir / "judge-queue.jsonl", judge_requests)
            (staging_dir / "dead-letters.jsonl").write_text(
                dead_letter_text, encoding="utf-8"
            )
            (staging_dir / "manifest.json").write_text(
                manifest_text, encoding="utf-8"
            )

            for name in artifact_names:
                fsync_file(staging_dir / name)

            if precommit_validator is not None:
                try:
                    precommit_validator(
                        RunArtifactCommitCandidate(
                            pred=(staging_dir / "pred.jsonl").read_bytes(),
                            manifest=(staging_dir / "manifest.json").read_bytes(),
                            judge_queue=(staging_dir / "judge-queue.jsonl").read_bytes(),
                            dead_letters=(staging_dir / "dead-letters.jsonl").read_bytes(),
                        )
                    )
                except BaseException as error:
                    control_flow_error = error

            if control_flow_error is None:
                # Retire any previous commit marker durably before removing or replacing
                # the data that it names.
                commit_started = True
                remove_committed_targets(best_effort=False)
                for name in data_artifact_names:
                    os.replace(staging_dir / name, run_dir / name)
                commit_marker = run_dir / manifest_name
                os.replace(staging_dir / manifest_name, commit_marker)
                fsync_run_directory()

                readback_failed = True
                if commit_marker.read_bytes() == manifest_text.encode():
                    readback_failed = False
        except BaseException as error:
            if isinstance(error, Exception):
                failed = True
            else:
                control_flow_error = error
        if commit_started and (failed or readback_failed or control_flow_error is not None):
            try:
                remove_committed_targets(best_effort=True)
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception):
                    if control_flow_error is None:
                        control_flow_error = cleanup_error
                else:
                    failed = True
    finally:
        try:
            shutil.rmtree(staging_dir)
        except FileNotFoundError:
            pass
        except BaseException as cleanup_error:
            if isinstance(cleanup_error, Exception):
                staging_cleanup_failed = True
            elif control_flow_error is None:
                control_flow_error = cleanup_error
        if os.path.lexists(staging_dir):
            staging_cleanup_failed = True
        try:
            fsync_run_directory()
        except BaseException as cleanup_error:
            if isinstance(cleanup_error, Exception):
                staging_cleanup_failed = True
            elif control_flow_error is None:
                control_flow_error = cleanup_error
    if control_flow_error is not None:
        raise control_flow_error
    if staging_cleanup_failed:
        raise RuntimeError("run artifact staging cleanup failed") from None
    if failed or readback_failed:
        message = (
            "run artifact manifest read-back failed"
            if readback_failed
            else "run artifact commit failed"
        )
        raise RuntimeError(message) from None


def _merge_stats(a: CallStats, b: CallStats) -> CallStats:
    return CallStats(
        calls=a.calls + b.calls,
        prompt_chars=a.prompt_chars + b.prompt_chars,
        completion_chars=a.completion_chars + b.completion_chars,
    )


def _parse_state_run_identity(values: dict[str, Any]) -> _RunIdentity:
    try:
        return _RunIdentity.model_validate(
            {
                field: values[field]
                for field in _RunIdentity.model_fields
            }
        )
    except (KeyError, TypeError, ValidationError):
        raise ScopeViolation("run identity mismatch") from None


def _manifest_run_identity(manifest: RunManifest) -> _RunIdentity:
    return _RunIdentity(
        run_id=manifest.run_id,
        run_dir=manifest.run_dir,
        checkpoint_path=manifest.checkpoint_path,
        product_dir=manifest.product_dir,
        product_id=manifest.product_id,
        product_name=manifest.product_name,
        line_key=manifest.line_key,
        model_id=manifest.model_id,
        schema_version=manifest.schema_version,
        prompt_version=manifest.prompt_version,
        judge_mode=manifest.judge_mode,
        variant_digest=manifest.variant_digest,
    )


def _source_document_identity(document: SourceDocument) -> tuple[object, ...]:
    scope = document.scope
    return (
        document.file_name,
        document.source_id,
        document.knowledge_id,
        document.source_revision.value,
        source_ordering_identity_token(document.source_revision.ordering),
        document.source_revision.file_hash,
        document.original_digest,
        document.source_revision.parser_fingerprint,
        None
        if scope is None
        else (scope.space_id, scope.tenant_id, scope.raw_kb_id, scope.wiki_kb_id),
    )


def _checkpoint_source_identities(raw_documents: object) -> list[tuple[object, ...]]:
    if not isinstance(raw_documents, list):
        raise ScopeViolation("source identity mismatch")
    identities: list[tuple[object, ...]] = []
    try:
        for raw in raw_documents:
            if not isinstance(raw, dict):
                raise TypeError
            revision = raw["source_revision"]
            if not isinstance(revision, dict):
                raise TypeError
            validated_revision = SourceRevision.model_validate(revision)
            raw_scope = raw["scope"]
            if raw_scope is None:
                scope: tuple[object, ...] | None = None
            elif isinstance(raw_scope, dict):
                scope = (
                    raw_scope["space_id"],
                    raw_scope["tenant_id"],
                    raw_scope["raw_kb_id"],
                    raw_scope["wiki_kb_id"],
                )
            else:
                raise TypeError
            identities.append(
                (
                    raw["file_name"],
                    raw["source_id"],
                    raw["knowledge_id"],
                    validated_revision.value,
                    source_ordering_identity_token(validated_revision.ordering),
                    validated_revision.file_hash,
                    raw["original_digest"],
                    validated_revision.parser_fingerprint,
                    scope,
                )
            )
    except (KeyError, TypeError, ValidationError):
        raise ScopeViolation("source identity mismatch") from None
    return identities


def _parse_run_manifest(raw_manifest: object) -> RunManifest | None:
    try:
        return RunManifest.model_validate(raw_manifest)
    except (ValidationError, TypeError):
        return None


def _to_pred(
    cand: FieldCandidate,
    state: PipelineState,
    model_id: str,
    manifest: RunManifest,
    created: datetime,
) -> PredRecord:
    # 置信度分级（04 Step 7 简化版）：quote 回验通过+投票一致=high；补漏=medium；其余 low
    confidence = cand.confidence
    if cand.origin == "extract" and cand.tri_state in ("present", "absent_explicitly"):
        confidence = "high"  # 出场即已通过回验（校验链保证）
    # 006 F3.5（12 #2）：来源可信度分级——确定性候选经过语义裁决后按模型抽取记账
    dq_raw = cand.metadata.get("data_quality")
    data_quality: DataQuality = (
        cast(DataQuality, dq_raw)
        if dq_raw in ("structured_direct", "table_parsed", "llm_extracted", "llm_inferred")
        else "llm_extracted"
    )
    # E7：prompt_variant_used 在真实使用处记录（gapfill stamp）；未 stamp 的
    # 候选按 origin 如实归因——fastpath=确定性直取（无 prompt）、其余（含 semantic_resolve/
    # vote/judge/dead_letter）均经 baseline 抽取 prompt。注册表 membership 不参与。
    raw_attempts = cand.metadata.get("attempts")
    attempts = tuple(
        AuditAttempt.model_validate(a)
        for a in (raw_attempts if isinstance(raw_attempts, list) else [])
        if isinstance(a, dict)
    )
    raw_winner = cand.metadata.get("winning_attempt_id")
    winning_attempt_id = raw_winner if isinstance(raw_winner, str) else None
    winner = next(
        (a for a in attempts if a.attempt_id == winning_attempt_id), None
    )
    if winning_attempt_id is not None and winner is None and cand.origin != "fastpath":
        raise ScopeViolation("attempt ledger mismatch")
    # E7 R2：prompt_variant_used 由 winning attempt 派生（stage 消歧）；无 winner
    # 时按来源如实兜底——fastpath=非 LLM 直取、其余 unknown/未出值仍归 baseline。
    if winner is not None:
        used = winner.prompt_version
        winning_origin = _attempt_origin(winner.stage)
    elif cand.origin == "fastpath":
        used = "fastpath"
        winning_origin = "fastpath"
    else:
        used = f"baseline@{manifest.prompt_version or PROMPT_VERSION}"
        winning_origin = cand.origin
    raw_arm = cand.metadata.get("variant_assignment")
    raw_compat = cand.metadata.get("compat_reject")
    raw_terms = cand.metadata.get("pointer_terms")
    audit = ExtractionAudit(
        prompt_variant_used=used,
        variant_assignment=raw_arm if isinstance(raw_arm, str) else None,
        attempts=attempts,
        winning_attempt_id=(
            winning_attempt_id if cand.origin != "fastpath" else None
        ),
        winning_origin=winning_origin,
        compat_reject=raw_compat if isinstance(raw_compat, str) else None,
        pointer_terms=(
            tuple(str(t) for t in raw_terms) if isinstance(raw_terms, list) else ()
        ),
    )
    return PredRecord(
        extraction_audit=audit,
        data_quality=data_quality,
        source_mode="weknora" if manifest.space_id else "directory_replay",
        product_id=state["product_id"],
        product_name=state["product_name"],
        doc=cand.doc or "-",
        field_id=cand.field_id,
        field_name=cand.field_name,
        value=cand.value,
        tri_state=cand.tri_state,
        evidence=cand.evidence,
        annotator_model=model_id,
        schema_version=manifest.schema_version,
        created_at=created,
        confidence=confidence,
        pending_judge=cand.pending_judge,
        unknown_reason=cand.unknown_reason,
    )


def _attempt_origin(stage: str) -> str:
    """Map retry/detail stages back to the value-producing pipeline origin."""
    for origin in ("extract", "gapfill", "vote", "judge", "semantic_resolve"):
        if stage == origin or stage.startswith(f"{origin}_"):
            return origin
    return stage


def _source_aware_evidence(
    candidate: FieldCandidate,
    document: SourceDocument | None,
) -> list[Evidence]:
    """Discard preloaded audit and rederive it only from a verified source quote."""
    clean_evidence = [
        Evidence(page=evidence.page, quote=evidence.quote)
        for evidence in candidate.evidence
    ]
    if (
        candidate.tri_state == "unknown"
        or not clean_evidence
        or document is None
    ):
        return clean_evidence

    enriched: list[Evidence] = []
    for evidence in clean_evidence:
        if not quote_verified(evidence, document.pages):
            enriched.append(evidence)
            continue

        lineage = match_quote_to_chunks(evidence.quote, document.chunks)
        chunk_id = lineage.chunk_id
        chunk_hash = lineage.chunk_hash
        lineage_status = lineage.lineage_status
        if document.knowledge_id is None:
            # Directory replay chunks have no attested upstream identity.
            chunk_id = None
            chunk_hash = None
            if lineage_status == "linked":
                lineage_status = "page_only"
        enriched.append(
            Evidence.model_validate(
                {
                    **evidence.model_dump(mode="python"),
                    "knowledge_id": document.knowledge_id,
                    "raw_kb_id": document.raw_kb_id,
                    "source_revision": document.source_revision.value,
                    "file_hash": document.source_revision.file_hash,
                    "original_digest": document.original_digest,
                    "parser_version": document.source_revision.parser_fingerprint,
                    "chunk_id": chunk_id,
                    "chunk_hash": chunk_hash,
                    "lineage_status": lineage_status,
                }
            )
        )
    return enriched
