"""Low-level source material loading for the V5 provider trial.

The module owns file identity checks, PDF page projection, and deterministic
text/digest helpers. Product selection and extraction orchestration stay in
``provider_trial``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pdfplumber

from .source_evidence import SourcePage, classify_evidence
from .trial_contracts import ProviderTrialError, SourceFileReceipt

if TYPE_CHECKING:
    from .provider_trial import ApprovedProduct


class PdfSpec(Protocol):
    """Minimum immutable source identity required by the page loader."""

    @property
    def file_name(self) -> str: ...

    @property
    def sha256(self) -> str: ...

    @property
    def page_count(self) -> int: ...


@dataclass(frozen=True, slots=True)
class PreparedProduct:
    """Validated product material handed from loading into extraction."""

    approved: ApprovedProduct
    source_revision_id: str
    source_manifest_sha256: str
    files: tuple[SourceFileReceipt, ...]
    pages: tuple[SourcePage, ...]
    base_pages: tuple[SourcePage, ...]
    supplemental_pages: tuple[SourcePage, ...]
    source_text: str
    metadata: Mapping[str, object]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(domain: str, payload: object) -> str:
    encoded = json.dumps(
        {"domain": domain, "payload": payload},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _read_pdf_pages(path: Path) -> tuple[str, ...]:
    with pdfplumber.open(path) as document:
        return tuple(page.extract_text() or "" for page in document.pages)


def load_frozen_pdf_pages(
    path: Path,
    spec: PdfSpec,
    *,
    page_reader: Callable[[Path], tuple[str, ...]] = _read_pdf_pages,
    ocr_page_reader: Callable[[Path, int], str] | None = None,
) -> tuple[SourceFileReceipt, tuple[SourcePage, ...]]:
    """Read a PDF only when its approved identity and page count still match."""

    if path.name != spec.file_name or not path.is_file():
        raise ProviderTrialError("V5_SOURCE_FILE_MISSING")
    actual_sha256 = _sha256_bytes(path.read_bytes())
    if actual_sha256 != spec.sha256:
        raise ProviderTrialError("V5_SOURCE_SHA256_DRIFT")
    texts = page_reader(path)
    if len(texts) != spec.page_count:
        raise ProviderTrialError("V5_SOURCE_PAGE_COUNT_DRIFT")
    if ocr_page_reader is not None:
        texts = tuple(
            text if text.strip() else ocr_page_reader(path, page_number)
            for page_number, text in enumerate(texts, 1)
        )
    if any(not text.strip() for text in texts):
        raise ProviderTrialError("V5_SOURCE_PAGE_TEXT_MISSING")
    receipt = SourceFileReceipt(
        file_name=spec.file_name,
        sha256=spec.sha256,
        page_count=spec.page_count,
    )
    pages = tuple(
        SourcePage(
            document_name=spec.file_name,
            document_sha256=spec.sha256,
            page_number=index,
            text=text,
        )
        for index, text in enumerate(texts, 1)
    )
    return receipt, pages


def build_source_text(pages: Sequence[SourcePage]) -> str:
    """Render page identities alongside text for model context."""

    return "\n\n".join(
        f"【文档：{page.document_name}｜页码：{page.page_number}】\n{page.text}" for page in pages
    )


def resolve_evidence_locator(
    pages: Sequence[SourcePage],
    quote: str,
    advisory_locator: str | None = None,
) -> str:
    """Resolve a quote to a verified page or raise a typed trial error."""

    resolution = classify_evidence(
        pages,
        quote,
        advisory_locator or "unresolved:evidence",
    )
    if resolution.verification_status in {"VERIFIED", "NORMALIZED_MATCH"}:
        return resolution.locator
    raise ProviderTrialError(resolution.verification_error or "V5_EVIDENCE_PAGE_NOT_FOUND")


__all__ = [
    "PreparedProduct",
    "build_source_text",
    "load_frozen_pdf_pages",
    "resolve_evidence_locator",
]
