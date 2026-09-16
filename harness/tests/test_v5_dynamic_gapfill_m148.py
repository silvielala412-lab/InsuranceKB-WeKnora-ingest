from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from insurance_harness.v5_preview.api import create_app
from insurance_harness.v5_preview.catalog import catalog_sha256, load_v5_catalog
from insurance_harness.v5_preview.contracts import (
    CandidateEvidence,
    CandidateField,
    CategoryDefinition,
    PluginFieldResult,
    V5CandidatePreview,
)
from insurance_harness.v5_preview.dynamic_gapfill import (
    DynamicFieldGapfillRequest,
    DynamicFieldGapfillService,
    DynamicMaterialBundle,
    DynamicMaterialPage,
    InMemoryDynamicMaterialRepository,
)
from insurance_harness.v5_preview.ingest import preview_digest


def _preview(*, state: str = "unknown", value: object = None) -> V5CandidatePreview:
    catalog = load_v5_catalog()
    schema = catalog.schema_for("医疗险")
    target = next(field for field in schema.fields if field.field_id == "target_customer_profile")
    evidence = (
        CandidateEvidence(
            source_revision_id="source-1",
            locator="pdf:条款.pdf#page=1",
            quote="适合家庭成员投保",
        ),
    ) if state != "unknown" else ()
    fields = tuple(
        CandidateField(
            ordinal=field.ordinal,
            category_id=field.category_id,
            category_display_name=field.category_display_name,
            field_id=field.field_id,
            display_name=field.display_name,
            knowledge_role=field.knowledge_role,
            formation_modes=field.formation_modes,
            output_kind=field.output_kind,
            state=state if field.field_id == target.field_id else "unknown",
            value=value if field.field_id == target.field_id else None,
            evidence=evidence if field.field_id == target.field_id else (),
        )
        for field in schema.fields
    )
    category_ids = tuple(dict.fromkeys(field.category_id for field in fields))
    categories = tuple(
        CategoryDefinition(
            ordinal=category.ordinal,
            category_id=category.category_id,
            display_name=category.display_name,
        )
        for category in catalog.categories
        if category.category_id in category_ids
    )
    payload = {
        "contract": "insurance-v5-candidate-preview.v2",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog_sha256(catalog),
        "schema_id": schema.schema_id,
        "source_revision_id": "source-1",
        "insurance_class": "医疗险",
        "product_id": "596",
        "product_version_id": "596-1",
        "product_display_name": "测试医疗险",
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "categories": [item.model_dump(mode="json") for item in categories],
        "fields": [item.model_dump(mode="json") for item in fields],
    }
    return V5CandidatePreview(
        contract="insurance-v5-candidate-preview.v2",
        catalog_id=catalog.catalog_id,
        catalog_sha256=catalog_sha256(catalog),
        schema_id=schema.schema_id,
        source_revision_id="source-1",
        insurance_class="医疗险",
        product_id="596",
        product_version_id="596-1",
        product_display_name="测试医疗险",
        serving_effect="NONE",
        review_publish_admission=False,
        categories=categories,
        fields=fields,
        preview_sha256=preview_digest(payload),
    )


def _materials() -> InMemoryDynamicMaterialRepository:
    digest = "b" * 64
    return InMemoryDynamicMaterialRepository(
        (
            DynamicMaterialBundle(
                product_version_id="596-1",
                source_revision_id="source-1",
                pages=(
                    DynamicMaterialPage(
                        document_name="条款.pdf",
                        document_sha256=digest,
                        page_number=1,
                        text="本产品面向希望获得医疗保障的家庭。",
                    ),
                    DynamicMaterialPage(
                        document_name="条款.pdf",
                        document_sha256=digest,
                        page_number=2,
                        text="适用人群包括家庭成员，成人和少儿均可投保。",
                    ),
                    DynamicMaterialPage(
                        document_name="条款.pdf",
                        document_sha256=digest,
                        page_number=3,
                        text="投保年龄以投保时周岁计算。",
                    ),
                ),
            ),
        )
    )


class ScriptedExecutor:
    def __init__(self, outputs: Mapping[str, PluginFieldResult]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    def extract(
        self,
        *,
        preview: V5CandidatePreview,
        field_ids: tuple[str, ...],
        source_text: str,
        scope: str,
        action: str,
        pages: tuple[DynamicMaterialPage, ...],
    ) -> tuple[PluginFieldResult, ...]:
        self.calls.append((scope, field_ids, source_text))
        result = self.outputs.get(scope)
        if result is None:
            ordinal = next(
                field.ordinal for field in preview.fields if field.field_id == field_ids[0]
            )
            result = PluginFieldResult(
                ordinal=ordinal,
                field_id=field_ids[0],
                state="unknown",
            )
        return (result,)


def _request(preview: V5CandidatePreview, action: str = "gapfill") -> DynamicFieldGapfillRequest:
    return DynamicFieldGapfillRequest(
        contract="insurance-v5-dynamic-field-gapfill-request.v1",
        product_version_id=preview.product_version_id,
        preview_sha256=preview.preview_sha256,
        action=action,
        field_ids=["target_customer_profile"],
    )


def _result(*, value: str, status: str = "VERIFIED") -> PluginFieldResult:
    return PluginFieldResult(
        ordinal=next(
            field.ordinal
            for field in load_v5_catalog().schema_for("医疗险").fields
            if field.field_id == "target_customer_profile"
        ),
        field_id="target_customer_profile",
        state="present",
        value=value,
        evidence=(
            CandidateEvidence(
                source_revision_id="source-1",
                locator="pdf:条款.pdf#page=2",
                quote="适用人群包括家庭成员，成人和少儿均可投保。",
                verification_status=status,
                verification_error=(
                    None if status in {"VERIFIED", "NORMALIZED_MATCH"}
                    else "V5_EVIDENCE_PAGE_NOT_FOUND"
                ),
            ),
        ),
    )


def test_request_is_bounded_and_rejects_duplicate_fields() -> None:
    preview = _preview()
    with pytest.raises(ValidationError):
        DynamicFieldGapfillRequest(
            contract="insurance-v5-dynamic-field-gapfill-request.v1",
            product_version_id=preview.product_version_id,
            preview_sha256=preview.preview_sha256,
            action="gapfill",
            field_ids=["target_customer_profile", "target_customer_profile"],
        )


def test_gapfill_rejects_existing_value_before_executor_call() -> None:
    preview = _preview(state="present", value="家庭成员")
    executor = ScriptedExecutor({})
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=executor,
    )

    with pytest.raises(ValueError, match="M148_GAPFILL_REQUIRES_UNKNOWN"):
        service.run(_request(preview))
    assert executor.calls == []


def test_preview_identity_drift_is_rejected_before_executor_call() -> None:
    preview = _preview()
    executor = ScriptedExecutor({})
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=executor,
    )
    request = _request(preview).model_copy(update={"preview_sha256": "f" * 64})

    with pytest.raises(ValueError, match="M148_PREVIEW_IDENTITY_DRIFT"):
        service.run(request)
    assert executor.calls == []


def test_gapfill_expands_scopes_then_stops_on_verified_candidate() -> None:
    preview = _preview()
    executor = ScriptedExecutor({"all_material": _result(value="家庭成员、成人及少儿")})
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=executor,
    )

    response = service.run(_request(preview))

    assert [call[0] for call in executor.calls] == [
        "matched_snippets",
        "adjacent_pages",
        "all_material",
    ]
    assert response.status == "IMPROVED"
    assert response.call_count == 3
    assert response.fields[0].status == "FILLED"
    assert response.fields[0].scope_used == "all_material"
    assert response.fields[0].before.state == "unknown"
    assert response.fields[0].proposed is not None
    assert response.fields[0].after.value == "家庭成员、成人及少儿"
    assert response.candidate_preview.serving_effect == "NONE"
    assert response.candidate_preview.review_publish_admission is False

    follow_up = service.run(
        _request(response.candidate_preview, action="review")
    )
    assert follow_up.status == "CONFIRMED"
    assert follow_up.base_preview_sha256 == response.candidate_preview.preview_sha256


def test_unverified_gapfill_value_is_retained_as_review_candidate() -> None:
    preview = _preview()
    executor = ScriptedExecutor(
        {
            scope: _result(value="家庭成员、成人及少儿", status="UNRESOLVED")
            for scope in ("matched_snippets", "adjacent_pages", "all_material")
        }
    )
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=executor,
    )

    response = service.run(_request(preview))

    assert response.status == "NEEDS_REVIEW"
    assert response.fields[0].status == "FILLED"
    assert response.fields[0].after.value == "家庭成员、成人及少儿"
    assert response.fields[0].after.evidence[0].verification_status == "UNRESOLVED"
    assert response.candidate_preview.fields[
        next(
            index
            for index, field in enumerate(response.candidate_preview.fields)
            if field.field_id == "target_customer_profile"
        )
    ].state == "present"


def test_review_conflict_preserves_prior_value_and_surfaces_proposal() -> None:
    preview = _preview(state="present", value="家庭成员")
    executor = ScriptedExecutor(
        {
            "matched_snippets": _result(value="仅成人"),
            "adjacent_pages": _result(value="仅成人"),
            "all_material": _result(value="仅成人"),
        }
    )
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=executor,
    )

    response = service.run(_request(preview, action="review"))

    assert response.status == "NEEDS_REVIEW"
    assert response.fields[0].status == "CONFLICT"
    assert response.fields[0].before.value == "家庭成员"
    assert response.fields[0].proposed is not None
    assert response.fields[0].proposed.value == "仅成人"
    assert response.fields[0].after.value == "家庭成员"
    assert response.fields[0].changed is False


def test_api_forwards_closed_request_to_dynamic_backend() -> None:
    preview = _preview()
    service = DynamicFieldGapfillService(
        catalog=load_v5_catalog(),
        previews={preview.product_version_id: preview},
        materials=_materials(),
        executor=ScriptedExecutor({"matched_snippets": _result(value="家庭成员")}),
    )
    client = TestClient(
        create_app(enable_llm=False, dynamic_gapfill_service=service)
    )

    response = client.post(
        "/v5-preview-api/dynamic-field-gapfill",
        json=_request(preview).model_dump(mode="json"),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "IMPROVED"
    assert payload["candidate_preview"]["serving_effect"] == "NONE"
    assert payload["candidate_preview"]["review_publish_admission"] is False
