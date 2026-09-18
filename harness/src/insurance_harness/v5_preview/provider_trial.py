"""Provider trial contracts, frozen source manifests, and local run orchestration."""

from __future__ import annotations

from .contracts import V5CandidatePreview
from .material_loader import (
    PreparedProduct,
    build_source_text,
    load_frozen_pdf_pages,
    resolve_evidence_locator,
)
from .source_evidence import SourcePage, classify_evidence
from .source_manifest import (
    APPROVED_PRODUCTS,
    M140_PRODUCT_IDS,
    M146_SUPPLEMENTAL_PDFS,
    ApprovedPdf,
    ApprovedProduct,
)
from .trial_artifacts import (
    load_provider_trial_run,
    seal_provider_trial_run,
    write_ocr_receipt_artifact,
    write_provider_trial_run,
)
from .trial_contracts import (
    MAX_MICROBATCH_PRODUCT_ATTEMPTS,
    MAX_MICROBATCH_PROVIDER_CALLS,
    ProviderAttemptReceipt,
    ProviderIdentity,
    ProviderTrialError,
    ProviderTrialProduct,
    SourceFileReceipt,
    V5ProviderTrialRun,
)
from .trial_policy import (
    M143_SEMANTIC_TARGET_FIELD_IDS,
    M144_CONTENT_SYNTHESIS_FIELD_IDS,
    _attempt_from_completion,
    _compiler,
    _content_synthesis_context,
    _content_synthesis_targets,
    _controlled_repair_hint,
    _controlled_repair_targets,
    _error_code,
    _request_for_product,
    _review_error_code,
)
from .trial_preparation import (
    M146_SERVICE_FIELD_IDS,
    _material_support_for_product,
    build_m146_repair_source_text,
    prepare_approved_product,
    prepare_approved_products,
)
from .trial_runner import (
    BAILIAN_BASE_URL,
    BAILIAN_MODEL,
    MAX_PRODUCT_ATTEMPTS,
    MAX_PROVIDER_CALLS,
    run_provider_trial,
)


def _preview_counts(preview: V5CandidatePreview | None) -> dict[str, int]:
    if preview is None:
        return {
            "fields": 0,
            "present": 0,
            "absent_explicitly": 0,
            "unknown": 0,
            "evidence_total": 0,
            "verified": 0,
            "normalized": 0,
            "unresolved": 0,
            "ambiguous": 0,
        }
    evidence = [item for field in preview.fields for item in field.evidence]
    return {
        "fields": len(preview.fields),
        "present": sum(field.state == "present" for field in preview.fields),
        "absent_explicitly": sum(
            field.state == "absent_explicitly" for field in preview.fields
        ),
        "unknown": sum(field.state == "unknown" for field in preview.fields),
        "evidence_total": len(evidence),
        "verified": sum(item.verification_status == "VERIFIED" for item in evidence),
        "normalized": sum(
            item.verification_status == "NORMALIZED_MATCH" for item in evidence
        ),
        "unresolved": sum(
            item.verification_status == "UNRESOLVED" for item in evidence
        ),
        "ambiguous": sum(
            item.verification_status == "AMBIGUOUS" for item in evidence
        ),
    }


def compare_provider_trials(
    baseline: V5ProviderTrialRun,
    adaptive: V5ProviderTrialRun,
) -> tuple[dict[str, object], ...]:
    """Compare exact product versions without treating either run as approval."""
    baseline_by_version = {product.product_version_id: product for product in baseline.products}
    adaptive_by_version = {product.product_version_id: product for product in adaptive.products}
    if set(baseline_by_version) != set(adaptive_by_version):
        raise ProviderTrialError("M126_COMPARISON_PRODUCT_SET_DRIFT")
    comparison: list[dict[str, object]] = []
    for version in sorted(baseline_by_version):
        before = _preview_counts(baseline_by_version[version].preview)
        after = _preview_counts(adaptive_by_version[version].preview)
        comparison.append(
            {
                "product_version_id": version,
                "baseline_status": baseline_by_version[version].status,
                "adaptive_status": adaptive_by_version[version].status,
                "baseline": before,
                "adaptive": after,
                "delta": {
                    key: after[key] - before[key]
                    for key in before
                },
                "baseline_run_sha256": baseline.run_sha256,
                "adaptive_run_sha256": adaptive.run_sha256,
                "serving_effect": "NONE",
                "review_publish_admission": False,
            }
        )
    return tuple(comparison)


def provider_trial_main() -> None:
    """Compatibility wrapper for the CLI moved to :mod:`trial_cli`."""

    from .trial_cli import provider_trial_main as _provider_trial_main

    _provider_trial_main()


if __name__ == "__main__":
    provider_trial_main()


__all__ = [
    "APPROVED_PRODUCTS",
    "BAILIAN_BASE_URL",
    "BAILIAN_MODEL",
    "M140_PRODUCT_IDS",
    "MAX_MICROBATCH_PRODUCT_ATTEMPTS",
    "MAX_MICROBATCH_PROVIDER_CALLS",
    "MAX_PRODUCT_ATTEMPTS",
    "MAX_PROVIDER_CALLS",
    "M144_CONTENT_SYNTHESIS_FIELD_IDS",
    "M146_SERVICE_FIELD_IDS",
    "M146_SUPPLEMENTAL_PDFS",
    "_content_synthesis_context",
    "_content_synthesis_targets",
    "_attempt_from_completion",
    "_compiler",
    "_controlled_repair_hint",
    "_controlled_repair_targets",
    "_error_code",
    "_material_support_for_product",
    "_request_for_product",
    "_review_error_code",
    "M143_SEMANTIC_TARGET_FIELD_IDS",
    "ApprovedPdf",
    "ApprovedProduct",
    "PreparedProduct",
    "ProviderAttemptReceipt",
    "ProviderIdentity",
    "ProviderTrialError",
    "ProviderTrialProduct",
    "SourceFileReceipt",
    "SourcePage",
    "V5ProviderTrialRun",
    "build_source_text",
    "build_m146_repair_source_text",
    "classify_evidence",
    "compare_provider_trials",
    "load_frozen_pdf_pages",
    "load_provider_trial_run",
    "prepare_approved_product",
    "prepare_approved_products",
    "provider_trial_main",
    "resolve_evidence_locator",
    "run_provider_trial",
    "seal_provider_trial_run",
    "write_provider_trial_run",
    "write_ocr_receipt_artifact",
]
