"""Mission 160 evaluation runner built on the reusable M158 engine."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from .catalog import load_v5_catalog
from .field_profiles import BUSINESS_PRIORITY_FIELD_IDS
from .full_schema_quality import (
    admit_full_schema_evidence_subset,
    build_full_schema_field_context,
    choose_full_schema_replacement,
)
from .llm_plugin import OpenAICompatibleCompletion
from .m154_concurrency import BatchConcurrencyProfile, ProductConcurrencyProfile
from .m156_quality import M156_FOCUS_FIELD_IDS
from .m156_run import M156_PRODUCT_IDS, M156Material, _sha256_bytes
from .m156_run import _load_m156_material as _load_base_material
from .m157_quality import build_m157_field_context, classify_m157_evidence
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
from .source_evidence import classify_evidence

M160_BASELINE_RUN_SHA256: Final = "d7c5819ac8feda7c5d6d8a4e31595c99be7081da19416d5dd0f3064f420e7b4a"
M160_BASELINE_FILE_SHA256: Final = (
    "4d40afd1be7615daf185512dc52b641df1b5df07814bec8c67401938d929fa70"
)
M160_CATALOG_SHA256: Final = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M160_BUSINESS_FEEDBACK_SHA256: Final = (
    "3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3"
)
M160_FOCUS_FIELD_IDS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys((*M156_FOCUS_FIELD_IDS, *BUSINESS_PRIORITY_FIELD_IDS))
)
# Keep detail-heavy business fields in small batches. Large coupled responses
# encouraged otherwise valid models to compress rights, claim and drug rules.
M160_MAX_COMPACT_FIELDS: Final = 4
M160_COMPACT_FIELD_IDS: Final[tuple[str, ...]] = tuple(
    field_id for field_id in M160_FOCUS_FIELD_IDS if field_id not in M158_LONG_FIELD_IDS
)


def _m160_repair_hint(batch: M158Batch) -> str:
    return m160_repair_hint(batch.kind)


def _material_repair_hint(batch: M158Batch) -> str:
    return _m160_repair_hint(batch) + (
        " Read every target field against its description, not just its title. "
        "Candidate pages are search hints, not proof that a fact exists. "
        "For source facts preserve the original wording and split separate rules into "
        "separate array items, each supported by a short verbatim same-page quote. "
        "If only part of a field is stated, return that supported part without inventing "
        "missing conditions. Do not turn absent detail into a negative fact. "
        "For fields requiring a specific method, threshold or script, generic contract "
        "wording does not establish that method, threshold or script."
        " 对普通原文抽取字段，value使用原文完整规则句的字符串数组，每项直接复制对应"
        "evidence.quote中的完整句子。不要改写主语或省略条件；保留原句中的您、我们、"
        "本合同和脚注数字。每项是一个独立且条件完整的规则。结构化选项字段仍按schema格式。"
    )


def material_backed_policy(policy: M158RunPolicy) -> M158RunPolicy:
    """Shared quality policy for e生保 and newly prepared product materials."""
    return replace(
        policy, repair_hint_builder=_material_repair_hint,
        evidence_admitter=admit_full_schema_evidence_subset,
        replacement_selector=choose_full_schema_replacement,
        source_fields_only=True, field_context_builder=build_full_schema_field_context,
        evidence_classifier=classify_evidence,
    )


def _load_m160_material(
    *,
    product: ProviderTrialProduct,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
) -> M156Material:
    """Preserve the M159 page-count receipt when the historical supplemental PDF is absent."""

    missing = tuple(
        item
        for item in product.files
        if not (supplemental_root_596 / item.file_name).is_file()
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
    batch_concurrency_profile: BatchConcurrencyProfile | None = None,
    material_backed: bool = False,
    material_backed_field_ids: Sequence[str] | None = None,
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
    effective_focus_field_ids = tuple(focus_field_ids)
    if material_backed:
        catalog = load_v5_catalog()
        effective_focus_field_ids = tuple(
            dict.fromkeys(
                material_backed_field_ids
                if material_backed_field_ids is not None
                else (
                    field.field_id
                    for schema in catalog.schemas
                    for field in schema.fields
                )
            )
        )
    policy = M158RunPolicy(
        baseline_run_sha256=baseline_run_sha256,
        baseline_file_sha256=baseline_file_sha256,
        catalog_sha256=M160_CATALOG_SHA256,
        business_feedback_sha256=M160_BUSINESS_FEEDBACK_SHA256,
        artifact_label="m160",
        focus_field_ids=effective_focus_field_ids,
        max_compact_fields=max_compact_fields,
        material_loader=_load_m160_material,
        repair_hint_builder=_m160_repair_hint,
        evidence_admitter=admit_m160_evidence_subset,
        replacement_selector=choose_m160_replacement,
        field_context_builder=build_m157_field_context,
        evidence_classifier=classify_m157_evidence,
    )
    if material_backed:
        policy = material_backed_policy(policy)
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
        batch_concurrency_profile=batch_concurrency_profile,
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
    parser.add_argument("--material-backed", action="store_true")
    parser.add_argument("--material-backed-field-id", action="append")
    parser.add_argument("--max-compact-fields", type=int, choices=range(1, 13))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--assessment-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--max-batch-concurrency", type=int, choices=range(1, 9), default=1)
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
    if args.material_backed_field_id and not args.material_backed:
        raise SystemExit("M160_MATERIAL_FIELDS_REQUIRE_MATERIAL_BACKED")
    focus_field_ids = (
        tuple(dict.fromkeys(args.focus_field_id))
        if args.focus_field_id
        else M160_COMPACT_FIELD_IDS
        if args.compact_only
        else M160_FOCUS_FIELD_IDS
    )
    max_compact_fields = args.max_compact_fields or (
        2 if args.compact_only else 8 if args.material_backed else M160_MAX_COMPACT_FIELDS
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
        batch_concurrency_profile=BatchConcurrencyProfile(max_batches=args.max_batch_concurrency),
        material_backed=args.material_backed,
        material_backed_field_ids=args.material_backed_field_id,
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
