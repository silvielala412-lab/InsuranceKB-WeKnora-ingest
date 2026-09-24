from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .catalog import catalog_sha256, load_v5_catalog
from .contracts import (
    CandidateEvidence,
    IngestRequest,
    InsuranceSchema,
    PluginFieldResult,
    PluginResult,
    V5CandidatePreview,
)
from .dynamic_gapfill import (
    DynamicFieldGapfillRequest,
    DynamicFieldGapfillResponse,
    DynamicFieldGapfillService,
)
from .ingest import IngestPluginRegistry, PreviewCompilationError, V5PreviewCompiler
from .llm_plugin import LlmPluginError, OpenAICompatibleCompletion, SchemaGuidedLlmPlugin
from .provider_trial import V5ProviderTrialRun, load_provider_trial_run
from .search import V5SearchRequest, V5SearchResponse, search_provider_run


class FixturePreviewPlugin:
    plugin_id = "v5-local-fixture-v1"

    def extract(self, request: IngestRequest, schema: InsuranceSchema) -> PluginResult:
        fields = []
        for field in schema.fields:
            if field.field_id == "product_name":
                fields.append(
                    PluginFieldResult(
                        ordinal=field.ordinal,
                        field_id=field.field_id,
                        state="present",
                        value=request.product_display_name,
                        evidence=(
                            CandidateEvidence(
                                source_revision_id=request.source_revision_id,
                                locator="fixture:product-identity",
                                quote=request.product_display_name,
                            ),
                        ),
                    )
                )
            else:
                fields.append(
                    PluginFieldResult(
                        ordinal=field.ordinal,
                        field_id=field.field_id,
                        state="unknown",
                    )
                )
        return PluginResult(
            plugin_id=self.plugin_id,
            source_revision_id=request.source_revision_id,
            insurance_class=schema.insurance_class,
            product_id=request.product_id,
            product_version_id=request.product_version_id,
            schema_id=schema.schema_id,
            fields=tuple(fields),
        )


def _compiler(plugin: object) -> V5PreviewCompiler:
    registry = IngestPluginRegistry()
    registry.register(catalog_id="insurance-product-schema-v5", plugin=plugin)  # type: ignore[arg-type]
    return V5PreviewCompiler(catalog=load_v5_catalog(), registry=registry)


def _llm_plugin_from_environment() -> SchemaGuidedLlmPlugin:
    required = {
        key: os.environ.get(key, "").strip()
        for key in (
            "HARNESS_LLM_BASE_URL",
            "HARNESS_LLM_API_KEY",
            "HARNESS_LLM_MODEL_WEAK",
            "V5_PREVIEW_LLM_FAMILY",
        )
    }
    if not all(required.values()):
        raise ValueError("V5_PREVIEW_PROVIDER_NOT_CONFIGURED")
    family = required["V5_PREVIEW_LLM_FAMILY"]
    if family not in {"qwen", "minimax"}:
        raise ValueError("V5_PREVIEW_MODEL_FAMILY_NOT_ALLOWED")
    completion = OpenAICompatibleCompletion(
        base_url=required["HARNESS_LLM_BASE_URL"],
        api_key=required["HARNESS_LLM_API_KEY"],
        model=required["HARNESS_LLM_MODEL_WEAK"],
        model_family=family,  # type: ignore[arg-type]
    )
    return SchemaGuidedLlmPlugin(completion=completion)


def _search_completion_from_environment() -> OpenAICompatibleCompletion | None:
    if os.environ.get("V5_SEARCH_LLM_ENABLED", "").strip() != "1":
        return None
    api_key = (
        os.environ.get("HARNESS_LLM_API_KEY", "").strip()
        or os.environ.get("DASHSCOPE_API_KEY", "").strip()
    )
    if not api_key:
        return None
    return OpenAICompatibleCompletion(
        base_url=(
            os.environ.get(
                "HARNESS_LLM_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).strip()
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        api_key=api_key,
        model=(os.environ.get("HARNESS_LLM_MODEL_WEAK", "qwen-plus").strip() or "qwen-plus"),
        model_family=(os.environ.get("V5_PREVIEW_LLM_FAMILY", "qwen").strip() or "qwen"),  # type: ignore[arg-type]
        timeout_seconds=float(os.environ.get("V5_SEARCH_LLM_TIMEOUT_SECONDS", "60")),
        max_calls=50,
    )


def create_app(
    *,
    enable_llm: bool | None = None,
    provider_run_path: str | Path | None = None,
    dynamic_gapfill_service: DynamicFieldGapfillService | None = None,
    search_completion: OpenAICompatibleCompletion | None = None,
) -> FastAPI:
    app = FastAPI(title="Insurance v5 Candidate Preview", version="1.0.0")
    catalog = load_v5_catalog()
    fixture_compiler = _compiler(FixturePreviewPlugin())
    llm_enabled = (
        os.environ.get("V5_PREVIEW_LLM_ENABLED", "").strip() == "1"
        if enable_llm is None
        else enable_llm
    )
    llm_compiler: V5PreviewCompiler | None = None
    if llm_enabled:
        try:
            llm_compiler = _compiler(_llm_plugin_from_environment())
        except ValueError:
            llm_compiler = None
    configured_run_path = (
        Path(provider_run_path)
        if provider_run_path is not None
        else Path(value)
        if (value := os.environ.get("V5_PREVIEW_RUN_ARTIFACT", "").strip())
        else None
    )
    provider_run = (
        load_provider_trial_run(configured_run_path)
        if configured_run_path is not None
        else None
    )
    configured_search_completion = (
        search_completion
        if search_completion is not None
        else _search_completion_from_environment()
    )

    @app.get("/v5-preview-api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "catalog_id": catalog.catalog_id,
            "catalog_sha256": catalog_sha256(catalog),
            "llm_configured": llm_compiler is not None,
            "provider_run_configured": provider_run is not None,
            "dynamic_gapfill_configured": dynamic_gapfill_service is not None,
            "search_configured": provider_run is not None,
            "search_llm_configured": configured_search_completion is not None,
            "serving_effect": "NONE",
        }

    @app.get("/v5-preview-api/catalog")
    def get_catalog() -> dict[str, object]:
        return {
            **catalog.model_dump(mode="json"),
            "catalog_sha256": catalog_sha256(catalog),
        }

    @app.get("/v5-preview-api/provider-run", response_model=V5ProviderTrialRun)
    def get_provider_run() -> V5ProviderTrialRun:
        if provider_run is None:
            raise HTTPException(status_code=404, detail="V5_PROVIDER_RUN_NOT_CONFIGURED")
        return provider_run

    @app.post("/v5-preview-api/search", response_model=V5SearchResponse)
    def search(request: V5SearchRequest) -> V5SearchResponse:
        if provider_run is None:
            raise HTTPException(status_code=503, detail="V5_SEARCH_DATA_NOT_CONFIGURED")
        return search_provider_run(
            provider_run,
            request,
            completion=configured_search_completion,
        )

    def compile_or_422(compiler: V5PreviewCompiler, request: IngestRequest) -> V5CandidatePreview:
        try:
            return compiler.compile(request)
        except (PreviewCompilationError, LlmPluginError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v5-preview-api/fixture-preview", response_model=V5CandidatePreview)
    def fixture_preview(request: IngestRequest) -> V5CandidatePreview:
        return compile_or_422(fixture_compiler, request)

    @app.post("/v5-preview-api/preview", response_model=V5CandidatePreview)
    def llm_preview(request: IngestRequest) -> V5CandidatePreview:
        if llm_compiler is None:
            raise HTTPException(status_code=503, detail="V5_PREVIEW_PROVIDER_NOT_CONFIGURED")
        return compile_or_422(llm_compiler, request)

    @app.post(
        "/v5-preview-api/dynamic-field-gapfill",
        response_model=DynamicFieldGapfillResponse,
    )
    def dynamic_field_gapfill(
        request: DynamicFieldGapfillRequest,
    ) -> DynamicFieldGapfillResponse:
        if dynamic_gapfill_service is None:
            raise HTTPException(
                status_code=503,
                detail="V5_DYNAMIC_GAPFILL_NOT_CONFIGURED",
            )
        try:
            return dynamic_gapfill_service.run(request)
        except (ValueError, LlmPluginError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


def app_factory() -> FastAPI:
    return create_app()


def api_main() -> None:
    import uvicorn

    uvicorn.run(
        "insurance_harness.v5_preview.api:app_factory",
        factory=True,
        host="127.0.0.1",
        port=8091,
    )


__all__ = ["FixturePreviewPlugin", "api_main", "app_factory", "create_app"]
