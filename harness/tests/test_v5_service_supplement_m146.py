from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from insurance_harness.v5_preview.contracts import FieldDefinition, InsuranceSchema
from insurance_harness.v5_preview.material_support import classify_material_support
from insurance_harness.v5_preview.provider_trial import (
    M146_SERVICE_FIELD_IDS,
    M146_SUPPLEMENTAL_PDFS,
    ApprovedPdf,
    ProviderTrialError,
    SourcePage,
    build_m146_repair_source_text,
    load_frozen_pdf_pages,
)


def _schema() -> InsuranceSchema:
    definitions = (
        ("policyholder_rights", "保单权益", ("原文抽取",)),
        ("eligible_service_packages", "可享服务", ("外部映射",)),
        ("medical_service_benefits", "增值服务", ("原文抽取", "外部映射")),
        ("product_faq", "产品Q&A", ("原文抽取",)),
        ("coverage_responsibilities", "保险责任", ("原文抽取",)),
    )
    return InsuranceSchema(
        ordinal=0,
        insurance_class="医疗险",
        schema_id="insurance-product-schema-v5:医疗险",
        fields=tuple(
            FieldDefinition(
                ordinal=index,
                category_id="09" if index < 3 else "10" if index == 3 else "07",
                category_display_name="服务与权益" if index < 3 else "销售赋能",
                display_name=label,
                value_guidance="",
                field_id=field_id,
                description=label,
                source_guidance="服务手册",
                formation_modes=modes,
                knowledge_role="事实 Fact" if index != 3 else "内容 Content",
            )
            for index, (field_id, label, modes) in enumerate(definitions)
        ),
    )


def test_m146_supplement_identity_is_frozen() -> None:
    assert tuple(item.file_name for item in M146_SUPPLEMENTAL_PDFS) == (
        "安有医健康服务手册（尊享版）.pdf",
        "平安添瑞·安有医（安医保尊享版）一页纸.pdf",
    )
    assert tuple(item.page_count for item in M146_SUPPLEMENTAL_PDFS) == (60, 2)
    assert M146_SERVICE_FIELD_IDS == (
        "policyholder_rights",
        "eligible_service_packages",
        "medical_service_benefits",
        "product_faq",
    )


def test_empty_pdf_page_requires_ocr_and_keeps_page_identity(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"frozen-pdf")
    spec = ApprovedPdf(
        file_name="scan.pdf",
        sha256=hashlib.sha256(b"frozen-pdf").hexdigest(),
        page_count=2,
    )

    with pytest.raises(ProviderTrialError, match="V5_SOURCE_PAGE_TEXT_MISSING"):
        load_frozen_pdf_pages(path, spec, page_reader=lambda _: ("", "已有文本"))

    _, pages = load_frozen_pdf_pages(
        path,
        spec,
        page_reader=lambda _: ("", "已有文本"),
        ocr_page_reader=lambda _path, page: "OCR第一页" if page == 1 else "",
    )
    assert tuple(page.page_number for page in pages) == (1, 2)
    assert tuple(page.text for page in pages) == ("OCR第一页", "已有文本")


def test_supplement_context_is_strictly_service_scoped() -> None:
    digest = "a" * 64
    base_pages = (
        SourcePage(
            document_name="保险条款.pdf",
            document_sha256=digest,
            page_number=1,
            text="核心保险责任与费率内容",
        ),
    )
    supplemental_pages = (
        SourcePage(
            document_name="服务手册.pdf",
            document_sha256=digest,
            page_number=1,
            text="在线问诊、陪诊、住院照护和产品常见问题",
        ),
    )
    text = build_m146_repair_source_text(
        base_pages=base_pages,
        supplemental_pages=supplemental_pages,
        schema=_schema(),
        target_field_ids=("eligible_service_packages", "coverage_responsibilities"),
    )
    assert "在线问诊" in text
    assert "核心保险责任" in text
    assert "M146 服务补充材料仅用于" in text
    assert "coverage_responsibilities" not in text.split("M146 服务补充材料仅用于", 1)[1]


def test_external_service_field_is_supported_only_with_controlled_supplement() -> None:
    field = _schema().fields[1]
    pages = (
        SourcePage(
            document_name="服务手册.pdf",
            document_sha256="b" * 64,
            page_number=1,
            text="提供在线问诊和门诊预约协助服务。",
        ),
    )
    assert classify_material_support(field, pages).status == "unsupported"
    assert classify_material_support(
        field,
        pages,
        allow_external_source=True,
    ).status == "supported"
