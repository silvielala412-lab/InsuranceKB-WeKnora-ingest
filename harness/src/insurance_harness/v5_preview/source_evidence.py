"""Source-page identity and evidence resolution shared by V5 workflows."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .contracts import EvidenceResolution


class SourcePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    document_name: Annotated[str, Field(min_length=1)]
    document_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_number: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1)]


def _normalized_evidence_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _page_locator(page: SourcePage) -> str:
    return f"pdf:{page.document_name}#page={page.page_number}"


def _select_advisory_page(
    matches: Sequence[SourcePage],
    advisory_locator: str,
) -> SourcePage | None:
    return next(
        (page for page in matches if _page_locator(page) == advisory_locator),
        None,
    )


def classify_evidence(
    pages: Sequence[SourcePage],
    quote: str,
    advisory_locator: str,
) -> EvidenceResolution:
    exact_matches = [page for page in pages if quote in page.text]
    if exact_matches:
        selected = (
            exact_matches[0]
            if len(exact_matches) == 1
            else _select_advisory_page(exact_matches, advisory_locator)
        )
        if selected is not None:
            return EvidenceResolution(
                locator=_page_locator(selected),
                verification_status="VERIFIED",
            )
        return EvidenceResolution(
            locator=advisory_locator,
            verification_status="AMBIGUOUS",
            verification_error="V5_EVIDENCE_PAGE_AMBIGUOUS",
        )

    normalized_quote = _normalized_evidence_text(quote)
    normalized_matches = [
        page
        for page in pages
        if normalized_quote and normalized_quote in _normalized_evidence_text(page.text)
    ]
    if normalized_matches:
        selected = (
            normalized_matches[0]
            if len(normalized_matches) == 1
            else _select_advisory_page(normalized_matches, advisory_locator)
        )
        if selected is not None:
            return EvidenceResolution(
                locator=_page_locator(selected),
                verification_status="NORMALIZED_MATCH",
            )
        return EvidenceResolution(
            locator=advisory_locator,
            verification_status="AMBIGUOUS",
            verification_error="V5_EVIDENCE_PAGE_AMBIGUOUS",
        )

    return EvidenceResolution(
        locator=advisory_locator,
        verification_status="UNRESOLVED",
        verification_error="V5_EVIDENCE_PAGE_NOT_FOUND",
    )


__all__ = ["SourcePage", "classify_evidence"]
