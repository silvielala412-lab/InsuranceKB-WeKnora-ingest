from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS
from .llm_plugin import OpenAICompatibleCompletion
from .m154_concurrency import ProductConcurrencyProfile
from .m156_quality import M156_FOCUS_FIELD_IDS
from .m156_run import M156_PRODUCT_IDS, M156Material, _sha256_bytes
from .m156_run import _load_m156_material as _load_base_material
from .m158_quality import M158_LONG_FIELD_IDS, M158_MAX_CALLS
from .m158_run import M158Batch, M158RunPolicy, run_m158
from .m160_quality import (
    admit_m160_evidence_subset,
    choose_m160_replacement,
    m160_repair_hint,
)
from .provider_trial import (
    APPROVED_PRODUCTS,
    ProviderTrialProduct,
    V5ProviderTrialRun,
    load_provider_trial_run,
)

M160_BASELINE_RUN_SHA256 = "d7c5819ac8feda7c5d6d8a4e31595c99be7081da19416d5dd0f3064f420e7b4a"
M160_BASELINE_FILE_SHA256 = "4d40afd1be7615daf185512dc52b641df1b5df07814bec8c67401938d929fa70"
M160_CATALOG_SHA256 = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M160_BUSINESS_FEEDBACK_SHA256 = "3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3"
M160_FOCUS_FIELD_IDS = tuple(
    dict.fromkeys((*M156_FOCUS_FIELD_IDS, *BUSINESS_PRIORITY_FIELD_IDS))
)
M160_MAX_COMPACT_FIELDS = 12
M160_COMPACT_FIELD_IDS = tuple(
    field_id for field_id in M160_FOCUS_FIELD_IDS if field_id not in M158_LONG_FIELD_IDS
)


def _m160_repair_hint(batch: M158Batch) -> str:
    return m160_repair_hint(batch.kind)


def _load_m160_material(
    *,
    product: ProviderTrialProduct,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
) -> M156Material:
    """Preserve the M159 page-count receipt when the historical supplemental PDF is absent."""

    supplemental_root = supplemental_root_596
    missing = tuple(
        item
        for item in product.files
        if not (supplemental_root / item.file_name).is_file()
        and item.file_name not in {pdf.file_name for pdf in APPROVED_PRODUCTS[0].pdfs}
    )
    if not missing:
        return _load_base_material(
            product=product,
            sample_root=sample_root,
            serious_illness_root=serious_illness_root,
            supplemental_root_596=supplemental_root_596,
        )
    kept = tuple(item for item in product.files if item not in missing)
    material = _load_base_material(
        product=product.model_copy(update={"files": kept}),
        sample_root=sample_root,
        serious_illness_root=serious_illness_root,
        supplemental_root_596=supplemental_root_596,
    )
    extra_pages = sum(item.page_count for item in missing)
    extra_locators = tuple(
        f"pdf:{item.file_name}#page={page}"
        for item in missing
        for page in range(1, item.page_count + 1)
    )
    return M156Material(
        pages=material.pages,
        scanned_page_count=material.scanned_page_count + extra_pages,
        unreadable_page_locators=material.unreadable_page_locators + extra_locators,
    )


def run_m160(
    *,
    baseline_path: Path,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
    business_feedback_path: Path | None,
    output_path: Path,
    audit_output_path: Path,
    assessment_output_path: Path,
    completion_factory: Callable[[], OpenAICompatibleCompletion],
    concurrency_profile: ProductConcurrencyProfile,
    product_ids: Sequence[str] = M156_PRODUCT_IDS,
    focus_field_ids: Sequence[str] = M160_FOCUS_FIELD_IDS,
    max_compact_fields: int = M160_MAX_COMPACT_FIELDS,
    local_preview_baseline: bool = False,
) -> tuple[V5ProviderTrialRun, Mapping[str, Any], Mapping[str, Any]]:
    """Run the M158 engine against the frozen M159 baseline under M160 gates."""

    if local_preview_baseline:
        if len(product_ids) != 1:
            raise ValueError("M160_LOCAL_PREVIEW_BASELINE_REQUIRES_ONE_PRODUCT")
        baseline = load_provider_trial_run(baseline_path)
        baseline_run_sha256 = baseline.run_sha256
        baseline_file_sha256 = _sha256_bytes(baseline_path.read_bytes())
    else:
        baseline_run_sha256 = M160_BASELINE_RUN_SHA256
        baseline_file_sha256 = M160_BASELINE_FILE_SHA256
    policy = M158RunPolicy(
        baseline_run_sha256=baseline_run_sha256,
        baseline_file_sha256=baseline_file_sha256,
        catalog_sha256=M160_CATALOG_SHA256,
        business_feedback_sha256=M160_BUSINESS_FEEDBACK_SHA256,
        artifact_label="m160",
        focus_field_ids=tuple(focus_field_ids),
        max_compact_fields=max_compact_fields,
        material_loader=_load_m160_material,
        repair_hint_builder=_m160_repair_hint,
        evidence_admitter=admit_m160_evidence_subset,
        replacement_selector=choose_m160_replacement,
    )
    return run_m158(
        baseline_path=baseline_path,
        sample_root=sample_root,
        serious_illness_root=serious_illness_root,
        supplemental_root_596=supplemental_root_596,
        business_feedback_path=business_feedback_path,
        output_path=output_path,
        audit_output_path=audit_output_path,
        assessment_output_path=assessment_output_path,
        completion_factory=completion_factory,
        concurrency_profile=concurrency_profile,
        product_ids=product_ids,
        policy=policy,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission 160 priority-field completeness rerun")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--serious-illness-root", type=Path, required=True)
    parser.add_argument("--supplemental-root-596", type=Path, required=True)
    parser.add_argument("--business-feedback", type=Path)
    parser.add_argument("--product-id", action="append", choices=M156_PRODUCT_IDS)
    parser.add_argument("--compact-only", action="store_true")
    parser.add_argument("--focus-field-id", action="append", choices=M160_COMPACT_FIELD_IDS)
    parser.add_argument("--local-preview-baseline", action="store_true")
    parser.add_argument("--max-compact-fields", type=int, choices=range(1, 13))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--assessment-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit("M160_PROVIDER_API_KEY_NOT_CONFIGURED")
    product_ids = tuple(args.product_id) if args.product_id else M156_PRODUCT_IDS
    if len(product_ids) != len(set(product_ids)):
        raise SystemExit("M160_PRODUCT_ID_DUPLICATED")
    if args.business_feedback is None and len(product_ids) != 1:
        raise SystemExit("M160_BUSINESS_FEEDBACK_REQUIRED_FOR_MULTI_PRODUCT_RUN")
    if args.compact_only and len(product_ids) != 1:
        raise SystemExit("M160_COMPACT_ONLY_REQUIRES_ONE_PRODUCT")
    if args.focus_field_id and (not args.compact_only or len(product_ids) != 1):
        raise SystemExit("M160_FOCUS_FIELD_REQUIRES_SINGLE_PRODUCT_COMPACT_RUN")
    focus_field_ids = (
        tuple(dict.fromkeys(args.focus_field_id))
        if args.focus_field_id
        else M160_COMPACT_FIELD_IDS
        if args.compact_only
        else M160_FOCUS_FIELD_IDS
    )
    max_compact_fields = args.max_compact_fields or (
        2 if args.compact_only else M160_MAX_COMPACT_FIELDS
    )

    def completion_factory() -> OpenAICompatibleCompletion:
        return OpenAICompatibleCompletion(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model="qwen-plus",
            model_family="qwen",
            timeout_seconds=300.0,
            max_calls=M158_MAX_CALLS,
        )

    run, audit, assessment = run_m160(
        baseline_path=args.baseline,
        sample_root=args.sample_root,
        serious_illness_root=args.serious_illness_root,
        supplemental_root_596=args.supplemental_root_596,
        business_feedback_path=args.business_feedback,
        output_path=args.output,
        audit_output_path=args.audit_output,
        assessment_output_path=args.assessment_output,
        completion_factory=completion_factory,
        concurrency_profile=ProductConcurrencyProfile(max_products=args.max_product_concurrency),
        product_ids=product_ids,
        focus_field_ids=focus_field_ids,
        max_compact_fields=max_compact_fields,
        local_preview_baseline=args.local_preview_baseline,
    )
    print(
        {
            "run_id": run.run_id,
            "run_sha256": run.run_sha256,
            "call_count": audit["call_count"],
            "metrics": audit["metrics"],
            "feedback_status_counts": assessment["status_counts"],
        }
    )


if __name__ == "__main__":
    main()


__all__ = [
    "M160_BASELINE_FILE_SHA256",
    "M160_BASELINE_RUN_SHA256",
    "M160_COMPACT_FIELD_IDS",
    "M160_MAX_COMPACT_FIELDS",
    "run_m160",
]
