"""Sealing, persistence, and validation for V5 trial artifacts."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .catalog import catalog_sha256, load_v5_catalog
from .ingest import PreviewCompilationError, validate_preview_digest
from .material_loader import _canonical_digest
from .ocr import BAILIAN_OCR_MODEL, OcrPageReceipt
from .trial_contracts import (
    ProviderIdentity,
    ProviderTrialError,
    ProviderTrialProduct,
    V5ProviderTrialRun,
)


def _run_digest(payload: dict[str, object]) -> str:
    return _canonical_digest("insurance-v5-provider-trial-run.v2", payload)


def seal_provider_trial_run(
    *,
    provider: ProviderIdentity,
    products: tuple[ProviderTrialProduct, ...],
    started_at: str,
    finished_at: str,
) -> V5ProviderTrialRun:
    """Create the immutable run envelope without granting serving authority."""

    catalog = load_v5_catalog()
    preview_count = sum(product.preview is not None for product in products)
    status: Literal["COMPLETED", "PARTIAL", "FAILED"] = (
        "COMPLETED" if preview_count == len(products) else "PARTIAL" if preview_count else "FAILED"
    )
    run_id_seed = _canonical_digest(
        "v5-provider-trial-run-id.v1",
        {
            "started_at": started_at,
            "source_manifests": [product.source_manifest_sha256 for product in products],
            "provider": provider.model_dump(mode="json"),
        },
    )
    payload: dict[str, object] = {
        "contract": "insurance-v5-provider-trial-run.v2",
        "run_id": f"v5-trial-{run_id_seed[:16]}",
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog_sha256(catalog),
        "status": status,
        "provider": provider.model_dump(mode="json"),
        "call_count": sum(len(product.attempts) for product in products),
        "started_at": started_at,
        "finished_at": finished_at,
        "serving_effect": "NONE",
        "review_publish_admission": False,
        "products": [product.model_dump(mode="json") for product in products],
    }
    return V5ProviderTrialRun.model_validate(
        {
            **payload,
            "provider": provider,
            "products": products,
            "run_sha256": _run_digest(payload),
        }
    )


def write_provider_trial_run(path: Path, run: V5ProviderTrialRun) -> None:
    """Write a sealed run atomically so readers never observe partial JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            run.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_ocr_receipt_artifact(
    path: Path,
    receipts: Sequence[OcrPageReceipt],
) -> None:
    """Write the OCR receipt sidecar with its own content digest."""

    payload = {
        "contract": "insurance-v5-ocr-receipts.v1",
        "provider": "bailian",
        "model": BAILIAN_OCR_MODEL,
        "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
    }
    sealed = {
        **payload,
        "artifact_sha256": _canonical_digest("insurance-v5-ocr-receipts.v1", payload),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            sealed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_provider_trial_run(path: Path) -> V5ProviderTrialRun:
    """Load and validate a sealed run, including catalog and preview digests."""

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ProviderTrialError("V5_PROVIDER_RUN_INVALID")
        claimed = raw_payload.get("run_sha256")
        payload = dict(raw_payload)
        payload.pop("run_sha256", None)
        if _run_digest(payload) != claimed:
            raise ProviderTrialError("V5_PROVIDER_RUN_DIGEST_INVALID")
        run = V5ProviderTrialRun.model_validate_json(path.read_text(encoding="utf-8"))
        if run.catalog_sha256 != catalog_sha256(load_v5_catalog()):
            raise ProviderTrialError("V5_PROVIDER_RUN_CATALOG_DRIFT")
        for product in run.products:
            if product.preview is not None:
                validate_preview_digest(product.preview)
        return run
    except (OSError, UnicodeDecodeError, ValidationError, PreviewCompilationError) as exc:
        raise ProviderTrialError("V5_PROVIDER_RUN_INVALID") from exc
    except ProviderTrialError as exc:
        raise ProviderTrialError("V5_PROVIDER_RUN_INVALID") from exc


__all__ = [
    "load_provider_trial_run",
    "seal_provider_trial_run",
    "write_ocr_receipt_artifact",
    "write_provider_trial_run",
]
