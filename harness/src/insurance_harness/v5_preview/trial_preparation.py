"""Frozen source preparation and material-support diagnostics for V5 trials."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from .catalog import load_v5_catalog
from .contracts import InsuranceSchema, V5CandidatePreview
from .dynamic_ingest import (
    build_candidate_source_text,
    build_full_material_field_source_text,
    locate_field_candidates,
)
from .material_loader import (
    PreparedProduct,
    _canonical_digest,
    _sha256_bytes,
    build_source_text,
    load_frozen_pdf_pages,
)
from .material_support import (
    MaterialSupportDecision,
    MaterialSupportMetrics,
    classify_material_support,
    compute_material_supported_extraction_rate,
    is_pdf_extractable_field,
)
from .source_evidence import SourcePage
from .source_manifest import (
    _EXPECTED_SCHEMA_FIELDS_BY_CLASS,
    APPROVED_PRODUCTS,
    M146_SUPPLEMENTAL_PDFS,
    ApprovedProduct,
)
from .trial_contracts import ProviderTrialError, SourceFileReceipt

M146_SERVICE_FIELD_IDS: tuple[str, ...] = (
    "policyholder_rights",
    "eligible_service_packages",
    "medical_service_benefits",
    "product_faq",
)
_MAX_PREPARED_SOURCE_CHARACTERS = 200_000


def _material_support_for_product(
    *,
    prepared: PreparedProduct,
    schema: InsuranceSchema,
    preview: V5CandidatePreview | None,
) -> tuple[tuple[MaterialSupportDecision, ...], MaterialSupportMetrics | None]:
    """Build source-support diagnostics after extraction, without changing states."""

    if preview is None:
        return (), None
    supplemental_ids = set(M146_SERVICE_FIELD_IDS) if prepared.supplemental_pages else set()
    base_extractable_ids = tuple(
        field.field_id for field in schema.fields if is_pdf_extractable_field(field)
    )
    base_located = locate_field_candidates(
        prepared.base_pages,
        schema,
        base_extractable_ids,
    )
    base_candidate_locators = {
        field_id: tuple(candidate.locator for candidate in candidates)
        for field_id, candidates in base_located.items()
    }
    supplemental_located = (
        locate_field_candidates(
            prepared.supplemental_pages,
            schema,
            tuple(field.field_id for field in schema.fields if field.field_id in supplemental_ids),
        )
        if supplemental_ids
        else {}
    )
    decisions = tuple(
        classify_material_support(
            field,
            (prepared.pages if field.field_id in supplemental_ids else prepared.base_pages),
            (
                (
                    *base_candidate_locators.get(field.field_id, ()),
                    *tuple(
                        candidate.locator
                        for candidate in supplemental_located.get(field.field_id, ())
                    ),
                )
                if field.field_id in supplemental_ids
                else base_candidate_locators.get(field.field_id, ())
            ),
            allow_external_source=field.field_id in supplemental_ids,
        )
        for field in schema.fields
    )
    return decisions, compute_material_supported_extraction_rate(preview, decisions)


def build_m146_repair_source_text(
    *,
    base_pages: Sequence[SourcePage],
    supplemental_pages: Sequence[SourcePage],
    schema: InsuranceSchema,
    target_field_ids: Sequence[str],
    max_characters: int = 100_000,
) -> str:
    """Build a repair prompt scoped to service fields and their source pages."""

    definitions = {field.field_id for field in schema.fields}
    requested = tuple(target_field_ids)
    if (
        not requested
        or len(set(requested)) != len(requested)
        or any(field_id not in definitions for field_id in requested)
    ):
        raise ProviderTrialError("M146_REPAIR_FIELD_SET_INVALID")
    service_ids = tuple(field_id for field_id in requested if field_id in M146_SERVICE_FIELD_IDS)
    base_ids = tuple(field_id for field_id in requested if field_id not in M146_SERVICE_FIELD_IDS)
    sections: list[str] = []
    if base_ids:
        sections.append(
            build_candidate_source_text(
                base_pages,
                schema,
                base_ids,
                max_pages=24,
                max_characters=55_000,
            )
        )
    if service_ids:
        service_header = (
            "【M146 服务补充材料仅用于：" + ",".join(service_ids) + "；禁止据此改写其他字段】"
        )
        service_text = build_full_material_field_source_text(
            supplemental_pages,
            schema,
            service_ids,
            max_characters=42_000,
        )
        sections.append(f"{service_header}\n{service_text}")
    return "\n\n".join(section for section in sections if section)[:max_characters]


def prepare_approved_product(
    root: Path,
    approved: ApprovedProduct,
    *,
    supplemental_root_596: Path | None = None,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> PreparedProduct:
    """Validate and project one frozen product directory into page material."""

    folder = root / approved.directory_name
    expected_names = {"product_meta.json", *(pdf.file_name for pdf in approved.pdfs)}
    actual_names = (
        {path.name for path in folder.iterdir() if path.is_file()} if folder.is_dir() else set()
    )
    if actual_names != expected_names:
        raise ProviderTrialError("V5_SOURCE_SET_DRIFT")
    metadata_path = folder / "product_meta.json"
    metadata_bytes = metadata_path.read_bytes()
    if _sha256_bytes(metadata_bytes) != approved.metadata_sha256:
        raise ProviderTrialError("V5_SOURCE_METADATA_SHA256_DRIFT")
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderTrialError("V5_SOURCE_METADATA_INVALID") from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("planCode") != approved.product_id
        or metadata.get("versionNo") != approved.product_version_id
        or metadata.get("clauseName") != approved.product_display_name
    ):
        raise ProviderTrialError("V5_SOURCE_PRODUCT_IDENTITY_DRIFT")

    files: list[SourceFileReceipt] = []
    base_pages: list[SourcePage] = []
    for pdf in approved.pdfs:
        receipt, pdf_pages = load_frozen_pdf_pages(folder / pdf.file_name, pdf)
        files.append(receipt)
        base_pages.extend(pdf_pages)
    supplemental_pages: list[SourcePage] = []
    if supplemental_root_596 is not None and approved.product_id == "596":
        expected_supplement_names = {pdf.file_name for pdf in M146_SUPPLEMENTAL_PDFS}
        actual_supplement_names = (
            {path.name for path in supplemental_root_596.iterdir() if path.is_file()}
            if supplemental_root_596.is_dir()
            else set()
        )
        if actual_supplement_names != expected_supplement_names:
            raise ProviderTrialError("M146_SUPPLEMENTAL_SOURCE_SET_DRIFT")
        for pdf in M146_SUPPLEMENTAL_PDFS:
            receipt, pdf_pages = load_frozen_pdf_pages(
                supplemental_root_596 / pdf.file_name,
                pdf,
                ocr_page_reader=ocr_page_reader,
            )
            files.append(receipt)
            supplemental_pages.extend(pdf_pages)
    pages = [*base_pages, *supplemental_pages]
    manifest_payload = {
        "metadata_sha256": approved.metadata_sha256,
        "product_id": approved.product_id,
        "product_version_id": approved.product_version_id,
        "product_display_name": approved.product_display_name,
        "insurance_class": approved.insurance_class,
        "files": [file.model_dump(mode="json") for file in files],
        "supplemental_field_ids": (list(M146_SERVICE_FIELD_IDS) if supplemental_pages else []),
        "page_text_sha256": _canonical_digest(
            "v5-provider-page-text.v1",
            [
                {
                    "document_name": page.document_name,
                    "page_number": page.page_number,
                    "text": page.text,
                }
                for page in pages
            ],
        ),
    }
    manifest_sha256 = _canonical_digest("v5-provider-source-manifest.v1", manifest_payload)
    # Supplemental service material is intentionally excluded from the primary
    # all-field prompt. It is exposed only in the scoped repair context below.
    source_text = build_source_text(base_pages)
    if len(source_text) > _MAX_PREPARED_SOURCE_CHARACTERS:
        schema = load_v5_catalog().schema_for(approved.insurance_class)
        eligible_field_ids = tuple(
            field.field_id for field in schema.fields if is_pdf_extractable_field(field)
        )
        source_text = build_candidate_source_text(
            base_pages,
            schema,
            eligible_field_ids,
            max_pages=36,
            max_characters=180_000,
            max_pages_per_field=8,
            snippet_characters=1_000,
        )
    if len(source_text) > _MAX_PREPARED_SOURCE_CHARACTERS:
        raise ProviderTrialError("V5_BOUNDED_SOURCE_TEXT_TOO_LARGE")
    return PreparedProduct(
        approved=approved,
        source_revision_id=f"v5-source-{manifest_sha256}",
        source_manifest_sha256=manifest_sha256,
        files=tuple(files),
        pages=tuple(pages),
        base_pages=tuple(base_pages),
        supplemental_pages=tuple(supplemental_pages),
        source_text=source_text,
        metadata=metadata,
    )


def prepare_approved_products(
    root: Path,
    *,
    approved_products: Sequence[ApprovedProduct] = APPROVED_PRODUCTS,
    supplemental_root_596: Path | None = None,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> tuple[PreparedProduct, ...]:
    """Prepare a validated product set and check its schema topology."""

    selected = tuple(approved_products)
    if not selected or len({item.product_version_id for item in selected}) != len(selected):
        raise ProviderTrialError("V5_APPROVED_PRODUCT_SET_INVALID")
    prepared = tuple(
        prepare_approved_product(
            root,
            item,
            supplemental_root_596=supplemental_root_596,
            ocr_page_reader=ocr_page_reader,
        )
        for item in selected
    )
    catalog = load_v5_catalog()
    expected = tuple(
        _EXPECTED_SCHEMA_FIELDS_BY_CLASS[item.approved.insurance_class] for item in prepared
    )
    actual = tuple(
        len(catalog.schema_for(item.approved.insurance_class).fields) for item in prepared
    )
    if actual != expected:
        raise ProviderTrialError("V5_APPROVED_SCHEMA_TOPOLOGY_DRIFT")
    return prepared


__all__ = [
    "M146_SERVICE_FIELD_IDS",
    "build_m146_repair_source_text",
    "prepare_approved_product",
    "prepare_approved_products",
]
