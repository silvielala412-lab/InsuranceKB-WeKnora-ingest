from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib.resources import files
from typing import Final

from .contracts import V5Catalog

V5_SOURCE_SHA256: Final = "8feb33a1e7dc55fad1719a151737822e62bfac815f4b0969441e38744f0204ec"
_EXPECTED_COUNTS: Final = (67, 70, 62, 67, 66, 75, 79, 82, 74, 83, 76)
_EXPECTED_CLASSES: Final = (
    "医疗险",
    "意外医疗",
    "意外险",
    "重疾险",
    "定期寿险",
    "终身寿险",
    "两全保险",
    "年金险",
    "护理保险",
    "补充养老保险",
    "失能收入损失保险",
)
_EXPECTED_CATEGORIES: Final = tuple(f"{value:02d}" for value in range(2, 12))


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def catalog_sha256(catalog: V5Catalog) -> str:
    return _canonical_sha256(catalog.model_dump(mode="json"))


def _validate_topology(catalog: V5Catalog) -> None:
    if catalog.source_sha256 != V5_SOURCE_SHA256:
        raise ValueError("V5_CATALOG_SOURCE_IDENTITY_DRIFT")
    if tuple(schema.insurance_class for schema in catalog.schemas) != _EXPECTED_CLASSES:
        raise ValueError("V5_CATALOG_CLASS_TOPOLOGY_DRIFT")
    if tuple(len(schema.fields) for schema in catalog.schemas) != _EXPECTED_COUNTS:
        raise ValueError("V5_CATALOG_FIELD_COUNT_DRIFT")
    if tuple(category.category_id for category in catalog.categories) != _EXPECTED_CATEGORIES:
        raise ValueError("V5_CATALOG_CATEGORY_TOPOLOGY_DRIFT")
    if sum(len(schema.fields) for schema in catalog.schemas) != 801:
        raise ValueError("V5_CATALOG_TOTAL_FIELD_COUNT_DRIFT")
    if len({field.field_id for schema in catalog.schemas for field in schema.fields}) != 154:
        raise ValueError("V5_CATALOG_UNIQUE_FIELD_COUNT_DRIFT")
    if len(catalog.import_diagnostics) != 37:
        raise ValueError("V5_CATALOG_IMPORT_DIAGNOSTIC_DRIFT")

    category_names = {
        category.category_id: category.display_name for category in catalog.categories
    }
    for schema_ordinal, schema in enumerate(catalog.schemas):
        if schema.ordinal != schema_ordinal:
            raise ValueError("V5_CATALOG_SCHEMA_ORDER_DRIFT")
        if schema.schema_id != f"{catalog.catalog_id}:{schema.insurance_class}":
            raise ValueError("V5_CATALOG_SCHEMA_IDENTITY_DRIFT")
        if len({field.field_id for field in schema.fields}) != len(schema.fields):
            raise ValueError("V5_CATALOG_DUPLICATE_FIELD_ID")
        for field_ordinal, field in enumerate(schema.fields):
            if field.ordinal != field_ordinal:
                raise ValueError("V5_CATALOG_FIELD_ORDER_DRIFT")
            if category_names.get(field.category_id) != field.category_display_name:
                raise ValueError("V5_CATALOG_CATEGORY_IDENTITY_DRIFT")


@lru_cache(maxsize=1)
def load_v5_catalog() -> V5Catalog:
    resource = files("insurance_harness.v5_preview.data").joinpath("v5_schema_catalog.json")
    catalog = V5Catalog.model_validate_json(resource.read_text(encoding="utf-8"))
    _validate_topology(catalog)
    return catalog


__all__ = ["V5_SOURCE_SHA256", "catalog_sha256", "load_v5_catalog"]
