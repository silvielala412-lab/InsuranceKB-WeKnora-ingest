from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class M153IssueKind(StrEnum):
    missing = "missing"
    incomplete = "incomplete"
    wrong = "wrong"
    summary_incomplete = "summary_incomplete"
    summary_wrong = "summary_wrong"
    display_only = "display_only"
    schema_gap = "schema_gap"


M153_CATALOG_SHA256 = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M153_M152_RESULT_SHA256 = "a0aec0da238802cabaf002b4806bb8cf68c2af7ee95786816e41ab227f820bfe"
M153_WORKBOOK_SHA256: Mapping[str, str] = {
    "e生保尊享-问题.xlsx": "ced2804eb6ea274aeeadb10a7af5511986ff3cf0d5d4e3527a35217e29d25b1b",
    "年金-问题(1).xlsx": "be321b4edd84c8db130d7f5baa3f0abfd3512440336bd78b5d66ce2ed98bc7ae",
    "意外伤害-问题(1).xlsx": "91496a8c4503aa4f265218e345a6fb2de8baf2b2cb5d6d675a53279351bb604d",
    "盛世金越-问题.xlsx": "ef322a5dd17999669fc8a21f2806492e877f48ea65ef603438e2cfc9ba2c6a0a",
}


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class M153BusinessIssue(_ClosedModel):
    workbook_name: str = Field(min_length=1)
    sheet_name: str = Field(min_length=1)
    row_number: int = Field(ge=1)
    display_name: str = Field(min_length=1)
    field_id: str | None = None
    issue_kinds: tuple[M153IssueKind, ...] = Field(min_length=1)
    note: str
    required_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    allowed_values: tuple[str, ...] = ()
    embedded_asset_sha256: tuple[str, ...] = ()


class M153BusinessBaseline(_ClosedModel):
    workbook_name: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str = Field(min_length=1)
    sheet_names: tuple[str, ...] = Field(min_length=1)
    issues: tuple[M153BusinessIssue, ...] = Field(min_length=1)
    embedded_asset_sha256: tuple[str, ...] = ()


class M153ValueSnapshot(_ClosedModel):
    state: Literal["present", "absent_explicitly", "unknown"]
    value: str | int | float | bool | tuple[str, ...] | None
    evidence_quality: int = Field(ge=0, le=4)


class M153FieldDecision(_ClosedModel):
    decision: Literal["keep_baseline", "accept_candidate", "needs_review", "regression"]
    reason: str = Field(min_length=1)


class M153ContextPolicy(_ClosedModel):
    reextract: bool
    merge_all_candidate_facts: bool
    atomic_fact_first: bool
    forbidden_fact_check: bool


@dataclass(frozen=True, slots=True)
class TableCell:
    row_number: int
    column_number: int
    value: str


@dataclass(frozen=True, slots=True)
class TablePage:
    document_name: str
    page_number: int
    table_index: int
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    @classmethod
    def from_rows(
        cls,
        *,
        document_name: str,
        page_number: int,
        table_index: int,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> TablePage:
        if page_number < 1 or table_index < 1:
            raise ValueError("M153_TABLE_COORDINATE_INVALID")
        normalized_headers = tuple(str(value).strip() for value in headers)
        normalized_rows = tuple(
            tuple(str(value).strip() for value in row) for row in rows
        )
        return cls(
            document_name=document_name,
            page_number=page_number,
            table_index=table_index,
            headers=normalized_headers,
            rows=normalized_rows,
        )

    @property
    def locator(self) -> str:
        return f"pdf:{self.document_name}#page={self.page_number}"


class TableExtractionDiagnostic(_ClosedModel):
    document_name: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    table_count: int = Field(ge=0)
    status: Literal["extracted", "no_table", "failed"]
    error: str | None = None


def extract_pdf_tables(path: Path, *, document_name: str | None = None) -> tuple[
    tuple[TablePage, ...], tuple[TableExtractionDiagnostic, ...]
]:
    """Extract local table geometry; failures retain page-text fallback in the caller."""
    import pdfplumber

    name = document_name or path.name
    tables: list[TablePage] = []
    diagnostics: list[TableExtractionDiagnostic] = []
    try:
        with pdfplumber.open(path) as document:
            for page_number, page in enumerate(document.pages, 1):
                try:
                    extracted = page.extract_tables() or ()
                    for table_index, rows in enumerate(extracted, 1):
                        normalized = [
                            tuple(cell or "" for cell in row) for row in rows if row
                        ]
                        if not normalized:
                            continue
                        tables.append(
                            TablePage.from_rows(
                                document_name=name,
                                page_number=page_number,
                                table_index=table_index,
                                headers=normalized[0],
                                rows=normalized[1:],
                            )
                        )
                    diagnostics.append(
                        TableExtractionDiagnostic(
                            document_name=name,
                            page_number=page_number,
                            table_count=len(extracted),
                            status="extracted" if extracted else "no_table",
                        )
                    )
                except Exception as exc:
                    diagnostics.append(
                        TableExtractionDiagnostic(
                            document_name=name,
                            page_number=page_number,
                            table_count=0,
                            status="failed",
                            error=type(exc).__name__,
                        )
                    )
        return tuple(tables), tuple(diagnostics)
    except Exception as exc:  # page text remains the authoritative fallback
        return (), (
            TableExtractionDiagnostic(
                document_name=name,
                page_number=1,
                table_count=0,
                status="failed",
                error=type(exc).__name__,
            ),
        )


def normalize_issue_types(label: str) -> tuple[M153IssueKind, ...]:
    """Normalize business labels while preserving all meanings in one row."""
    value = str(label).strip()
    found: list[M153IssueKind] = []
    mappings = (
        ("抽取不全", M153IssueKind.incomplete),
        ("抽取错误", M153IssueKind.wrong),
        ("未抽取", M153IssueKind.missing),
        ("未识别", M153IssueKind.missing),
        ("LLM概括不全", M153IssueKind.summary_incomplete),
        ("LLM概括错误", M153IssueKind.summary_wrong),
        ("显示问题", M153IssueKind.display_only),
        ("记录待定", M153IssueKind.schema_gap),
    )
    for marker, kind in mappings:
        if marker in value and kind not in found:
            found.append(kind)
    return tuple(found) or (M153IssueKind.schema_gap,)


def policy_for_issue_types(issue_types: Sequence[M153IssueKind]) -> M153ContextPolicy:
    kinds = frozenset(issue_types)
    display_only = kinds == {M153IssueKind.display_only}
    return M153ContextPolicy(
        reextract=not display_only and M153IssueKind.schema_gap not in kinds,
        merge_all_candidate_facts=bool(
            kinds & {M153IssueKind.incomplete, M153IssueKind.summary_incomplete}
        ),
        atomic_fact_first=bool(
            kinds & {M153IssueKind.summary_incomplete, M153IssueKind.summary_wrong}
        ),
        forbidden_fact_check=bool(
            kinds & {M153IssueKind.wrong, M153IssueKind.summary_wrong}
        ),
    )


_PRODUCT_IDS = {
    "e生保尊享": "596",
    "年金": "1830",
    "意外伤害": "1814",
    "盛世金越": "5003",
}


def _product_id_for_workbook(name: str) -> str:
    for marker, product_id in _PRODUCT_IDS.items():
        if marker in name:
            return product_id
    raise ValueError(f"M153_WORKBOOK_PRODUCT_UNMAPPED: {name}")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELLIMAGE_NS = "http://www.wps.cn/officeDocument/2017/etCustomData"
_XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_OFFICE_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return ()
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return tuple(
        "".join(text.text or "" for text in item.iter(f"{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    )


def _cell_value(cell: ET.Element, strings: Sequence[str]) -> str:
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None:
        formula = cell.find(f"{{{_MAIN_NS}}}f")
        return (formula.text or "") if formula is not None else ""
    raw = value.text or ""
    return strings[int(raw)] if cell.attrib.get("t") == "s" else raw


def _embedded_assets(archive: zipfile.ZipFile) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return DISPIMG id -> media SHA and all embedded media SHAs."""
    media = {
        name: _sha256_bytes(archive.read(name))
        for name in archive.namelist()
        if name.startswith("xl/media/") and not name.endswith("/")
    }
    mapping: dict[str, str] = {}
    if "xl/cellimages.xml" not in archive.namelist():
        return mapping, tuple(sorted(media.values()))
    root = ET.fromstring(archive.read("xl/cellimages.xml"))
    rels: dict[str, str] = {}
    rel_name = "xl/_rels/cellimages.xml.rels"
    if rel_name in archive.namelist():
        rel_root = ET.fromstring(archive.read(rel_name))
        for rel in rel_root.findall(f"{{{_REL_NS}}}Relationship"):
            target = rel.attrib.get("Target", "").lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            rels[rel.attrib.get("Id", "")] = target
    for image in root.findall(f"{{{_CELLIMAGE_NS}}}cellImage"):
        name = image.find(f".//{{{_XDR_NS}}}cNvPr")
        blip = image.find(f".//{{{_DRAWING_NS}}}blip")
        if name is None or blip is None:
            continue
        media_name = rels.get(blip.attrib.get(f"{{{_OFFICE_NS}}}embed", ""))
        if media_name in media:
            mapping[name.attrib.get("name", "")] = media[media_name]
    return mapping, tuple(sorted(media.values()))


def _schema_field_id(display_name: str, product_id: str) -> str | None:
    # Avoid importing the provider trial target list; the catalog remains the authority.
    try:
        from .catalog import load_v5_catalog

        classes = {"596": "医疗险", "1830": "年金险", "1814": "意外险", "5003": "终身寿险"}
        fields = load_v5_catalog().schema_for(classes[product_id]).fields
    except (KeyError, ValueError):
        return None
    matches = [field.field_id for field in fields if field.display_name == display_name]
    return matches[0] if len(matches) == 1 else None


def _required_and_forbidden(note: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Extract only explicit constraint-like notes; this is audit metadata, not prompt data."""
    required: list[str] = []
    forbidden: list[str] = []
    allowed: list[str] = []
    for token in re.findall(r"[^，。；;]+", note):
        text = token.strip()
        if not text:
            continue
        expected = re.search(r"应为[“\"]?([^”\"]+?)[”\"]?$", text)
        if expected:
            values = tuple(
                part.strip() for part in re.split(r"[、,，]", expected.group(1)) if part.strip()
            )
            required.extend(values)
            allowed.extend(values)
            continue
        if any(marker in text for marker in ("必须", "至少", "包含")):
            required.append(text)
        for marker in ("不是", "不应", "不能", "无对应"):
            if marker in text:
                remainder = text.split(marker, 1)[1].strip(" ：:，,；;。")
                if remainder:
                    forbidden.append(remainder)
                break
        if re.search(r"^[^，。；;]+、[^，。；;]+$", text):
            allowed.extend(part.strip() for part in re.split(r"[、,，]", text) if part.strip())
    return tuple(required), tuple(forbidden), tuple(allowed)


def _parse_workbook(path: Path) -> M153BusinessBaseline:
    workbook_name = path.name
    product_id = _product_id_for_workbook(workbook_name)
    workbook_sha = _sha256_bytes(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        assets, all_asset_shas = _embedded_assets(archive)
        sheet_names = ("Sheet1", "Sheet2")
        sheet_file = "xl/worksheets/sheet1.xml"
        root = ET.fromstring(archive.read(sheet_file))
        issues: list[M153BusinessIssue] = []
        for row in root.findall(f".//{{{_MAIN_NS}}}row"):
            row_number = int(row.attrib.get("r", "0"))
            cells = {cell.attrib.get("r", ""): cell for cell in row.findall(f"{{{_MAIN_NS}}}c")}
            display_cell = next(
                (cell for address, cell in cells.items() if address.startswith("B")), None
            )
            kind_cell = next(
                (cell for address, cell in cells.items() if address.startswith("C")), None
            )
            note_cell = next(
                (cell for address, cell in cells.items() if address.startswith("D")), None
            )
            if display_cell is None or kind_cell is None:
                continue
            display_name = _cell_value(display_cell, strings).strip()
            label = _cell_value(kind_cell, strings).strip()
            if not display_name or display_name == "字段":
                continue
            note = _cell_value(note_cell, strings).strip() if note_cell is not None else ""
            formula = ""
            if note_cell is not None:
                formula_node = note_cell.find(f"{{{_MAIN_NS}}}f")
                formula = formula_node.text or "" if formula_node is not None else ""
            asset_sha = tuple(
                sha for image_id, sha in assets.items() if image_id in formula
            )
            required, forbidden, allowed = _required_and_forbidden(note)
            issues.append(
                M153BusinessIssue(
                    workbook_name=workbook_name,
                    sheet_name="Sheet1",
                    row_number=row_number,
                    display_name=display_name,
                    field_id=_schema_field_id(display_name, product_id),
                    issue_kinds=normalize_issue_types(label),
                    note=note,
                    required_facts=required,
                    forbidden_facts=forbidden,
                    allowed_values=allowed,
                    embedded_asset_sha256=asset_sha,
                )
            )
    return M153BusinessBaseline(
        workbook_name=workbook_name,
        sha256=workbook_sha,
        product_id=product_id,
        sheet_names=sheet_names,
        issues=tuple(issues),
        embedded_asset_sha256=all_asset_shas,
    )


def load_business_quality_baselines(root: Path) -> tuple[M153BusinessBaseline, ...]:
    baselines = tuple(_parse_workbook(root / name) for name in M153_WORKBOOK_SHA256)
    if any(
        baseline.sha256 != M153_WORKBOOK_SHA256[baseline.workbook_name]
        for baseline in baselines
    ):
        raise ValueError("M153_BUSINESS_WORKBOOK_SHA256_DRIFT")
    return baselines


def build_table_context(table_pages: Sequence[TablePage]) -> str:
    chunks: list[str] = []
    for table in table_pages:
        chunks.append(
            f"[{table.locator};table={table.table_index};headers={' | '.join(table.headers)}]"
        )
        for row_number, row in enumerate(table.rows, 1):
            for column_number, value in enumerate(row, 1):
                if value:
                    chunks.append(
                        f"[table={table.table_index};row={row_number};col={column_number}] {value}"
                    )
    return "\n".join(chunks)


def select_table_pages(
    table_pages: Sequence[TablePage], field_ids: Sequence[str]
) -> tuple[TablePage, ...]:
    terms: set[str] = set()
    for field_id in field_ids:
        if "premium" in field_id or "rate" in field_id:
            terms.update(("保费", "费率", "缴费", "交费"))
        if "annuity" in field_id or "payment" in field_id:
            terms.update(("领取", "年金", "年龄", "保险金"))
        if "amount" in field_id or "benefit" in field_id:
            terms.update(("保险金额", "保额", "给付", "金额"))
        if "reduction" in field_id:
            terms.update(("减保", "现金价值", "保额"))
    selected: list[TablePage] = []
    for table in table_pages:
        searchable = " ".join(
            (table.document_name, *table.headers, *(" ".join(row) for row in table.rows[:3]))
        )
        if ("费率表" in table.document_name and terms) or any(
            term in searchable for term in terms
        ):
            selected.append(table)
    return tuple(selected)


def _is_rate_field(field_id: str) -> bool:
    terms = ("premium", "annuity", "benefit", "amount", "payment", "rate", "reduction")
    return any(term in field_id for term in terms)


def field_needs_table_context(field_id: str) -> bool:
    return _is_rate_field(field_id)


class RunExtractionIndex:
    """Per-run in-memory index; it deliberately has no disk or cross-run state."""

    def __init__(
        self,
        *,
        pages: Sequence[Mapping[str, Any]],
        table_pages: Sequence[TablePage] = (),
    ) -> None:
        self._pages = tuple(pages)
        self._table_pages = tuple(table_pages)
        self._built_fields: set[str] = set()
        self._page_by_field: dict[str, tuple[Mapping[str, Any], ...]] = {}
        self._built_at = time.perf_counter()

    @property
    def candidate_build_count(self) -> int:
        return len(self._built_fields)

    def _pages_for(self, field_id: str) -> tuple[Mapping[str, Any], ...]:
        if field_id in self._page_by_field:
            return self._page_by_field[field_id]
        include_rate = _is_rate_field(field_id)
        selected = tuple(
            page
            for page in self._pages
            if include_rate or "费率表" not in str(page.get("document_name", ""))
        )
        self._built_fields.add(field_id)
        self._page_by_field[field_id] = selected
        return selected

    def context_for(self, field_ids: Sequence[str]) -> str:
        unique_ids = tuple(dict.fromkeys(field_ids))
        pages: list[str] = []
        for field_id in unique_ids:
            pages.extend(
                f"[pdf:{page.get('document_name')}#page={page.get('page_number')}] "
                f"{page.get('text', '')}"
                for page in self._pages_for(field_id)
            )
        if any(_is_rate_field(field_id) for field_id in unique_ids):
            table_text = build_table_context(select_table_pages(self._table_pages, unique_ids))
            if table_text:
                pages.append(table_text)
        return "\n".join(dict.fromkeys(pages))

    def context_with_receipt(
        self, field_ids: Sequence[str]
    ) -> tuple[str, Mapping[str, int | float]]:
        started = time.perf_counter()
        context = self.context_for(field_ids)
        page_count = context.count("[pdf:")
        duplicate_page_count = page_count - len(
            {
                line.split("]", 1)[0]
                for line in context.splitlines()
                if line.startswith("[pdf:")
            }
        )
        return context, {
            "characters": len(context),
            "page_count": page_count,
            "duplicate_page_count": duplicate_page_count,
            "candidate_build_count": self.candidate_build_count,
            "build_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def compare_field_value(
    baseline: M153ValueSnapshot,
    candidate: M153ValueSnapshot,
    *,
    required_facts: Sequence[str] = (),
    forbidden_facts: Sequence[str] = (),
    allowed_values: Sequence[str] = (),
) -> M153FieldDecision:
    candidate_text = str(candidate.value or "")
    if candidate.state == "unknown" and baseline.state == "present":
        return M153FieldDecision(decision="keep_baseline", reason="candidate became unknown")
    if any(fact and fact not in candidate_text for fact in required_facts):
        return M153FieldDecision(
            decision="regression", reason="candidate missing required facts"
        )
    if any(fact and fact in candidate_text for fact in forbidden_facts):
        return M153FieldDecision(
            decision="regression", reason="candidate contains forbidden facts"
        )
    if allowed_values and candidate_text not in allowed_values:
        return M153FieldDecision(decision="regression", reason="candidate outside allowed values")
    if baseline.state == "present" and candidate.evidence_quality < baseline.evidence_quality:
        return M153FieldDecision(decision="keep_baseline", reason="candidate Evidence is weaker")
    if baseline.state == candidate.state and baseline.value == candidate.value:
        return M153FieldDecision(decision="keep_baseline", reason="same normalized value")
    if baseline.state == "present" and candidate.state == "present":
        return M153FieldDecision(
            decision="needs_review", reason="candidate conflicts with baseline"
        )
    return M153FieldDecision(decision="accept_candidate", reason="candidate adds supported value")


def plan_bounded_batches(
    items: Sequence[str], *, batch_size: int, max_workers: int = 2
) -> tuple[tuple[str, ...], ...]:
    if batch_size < 1 or max_workers < 1 or max_workers > 2:
        raise ValueError("M153_BOUNDED_CONCURRENCY_INVALID")
    ordered = tuple(items)
    if len(set(ordered)) != len(ordered):
        raise ValueError("M153_BATCH_ITEMS_DUPLICATED")
    return tuple(
        ordered[index : index + batch_size] for index in range(0, len(ordered), batch_size)
    )


def execute_bounded_batches[T](
    batches: Sequence[tuple[str, ...]],
    *,
    worker: Callable[[tuple[int, tuple[str, ...]]], T],
    max_workers: int = 2,
) -> tuple[T, ...]:
    """Run independent batches concurrently and merge by stable batch index."""
    if max_workers < 1 or max_workers > 2:
        raise ValueError("M153_BOUNDED_CONCURRENCY_INVALID")
    indexed = tuple(enumerate(batches))
    results: dict[int, T] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, item): item[0] for item in indexed}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return tuple(results[index] for index, _batch in indexed)


__all__ = [
    "M153BusinessBaseline",
    "M153BusinessIssue",
    "M153ContextPolicy",
    "M153_CATALOG_SHA256",
    "M153_M152_RESULT_SHA256",
    "M153_WORKBOOK_SHA256",
    "M153FieldDecision",
    "M153IssueKind",
    "M153ValueSnapshot",
    "RunExtractionIndex",
    "TablePage",
    "TableExtractionDiagnostic",
    "build_table_context",
    "compare_field_value",
    "execute_bounded_batches",
    "extract_pdf_tables",
    "field_needs_table_context",
    "load_business_quality_baselines",
    "normalize_issue_types",
    "plan_bounded_batches",
    "policy_for_issue_types",
    "select_table_pages",
]
