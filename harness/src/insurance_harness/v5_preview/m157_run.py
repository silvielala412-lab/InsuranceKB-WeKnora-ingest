from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter

from .llm_plugin import OpenAICompatibleCompletion
from .m154_concurrency import ProductConcurrencyProfile
from .m156_quality import M156_FOCUS_FIELD_IDS
from .m156_run import M156_PRODUCT_IDS, run_m156
from .m157_quality import (
    M157_EXPECTED_PRIMARY_CALLS,
    M157_MAX_CALLS,
    build_m157_field_context,
    choose_m157_replacement,
    classify_m157_evidence,
    plan_m157_batches,
)
from .provider_trial import V5ProviderTrialRun

M157_BASELINE_RUN_SHA256 = "cee87b1772333d263e4ffff9424daeafd303ea26189ab4aab7d627aed92e3360"
M157_BASELINE_FILE_SHA256 = "f7da53d153b05f965bb4357bd7302c91b65351f3f39874ba0c0e0128fc709e86"
M157_CATALOG_SHA256 = "f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec"
M157_BUSINESS_FEEDBACK_SHA256 = "3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3"


def run_m157(
    *,
    baseline_path: Path,
    sample_root: Path,
    serious_illness_root: Path,
    supplemental_root_596: Path,
    business_feedback_path: Path,
    output_path: Path,
    audit_output_path: Path,
    completion_factory: Callable[[], OpenAICompatibleCompletion],
    concurrency_profile: ProductConcurrencyProfile,
) -> tuple[V5ProviderTrialRun, Mapping[str, object]]:
    return run_m156(
        baseline_path=baseline_path,
        sample_root=sample_root,
        serious_illness_root=serious_illness_root,
        supplemental_root_596=supplemental_root_596,
        business_feedback_path=business_feedback_path,
        output_path=output_path,
        audit_output_path=audit_output_path,
        completion_factory=completion_factory,
        concurrency_profile=concurrency_profile,
        run_code="M157",
        product_ids=M156_PRODUCT_IDS,
        baseline_run_sha256=M157_BASELINE_RUN_SHA256,
        baseline_file_sha256=M157_BASELINE_FILE_SHA256,
        expected_catalog_sha256=M157_CATALOG_SHA256,
        business_feedback_sha256=M157_BUSINESS_FEEDBACK_SHA256,
        max_calls=M157_MAX_CALLS,
        expected_primary_calls=M157_EXPECTED_PRIMARY_CALLS,
        audit_contract="insurance-v5-m157-section-applicability-evidence-audit.v1",
        focus_field_ids=M156_FOCUS_FIELD_IDS,
        batch_planner=plan_m157_batches,
        context_builder=build_m157_field_context,
        replacement_chooser=choose_m157_replacement,
        evidence_classifier=classify_m157_evidence,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission 157 six-product quality rerun")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--serious-illness-root", type=Path, required=True)
    parser.add_argument("--supplemental-root-596", type=Path, required=True)
    parser.add_argument("--business-feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="HARNESS_DASHSCOPE_API_KEY")
    parser.add_argument("--max-product-concurrency", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit("M157_PROVIDER_API_KEY_NOT_CONFIGURED")

    def completion_factory() -> OpenAICompatibleCompletion:
        return OpenAICompatibleCompletion(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model="qwen-plus",
            model_family="qwen",
            timeout_seconds=300.0,
            max_calls=M157_MAX_CALLS,
        )

    started = perf_counter()
    run, audit = run_m157(
        baseline_path=args.baseline,
        sample_root=args.sample_root,
        serious_illness_root=args.serious_illness_root,
        supplemental_root_596=args.supplemental_root_596,
        business_feedback_path=args.business_feedback,
        output_path=args.output,
        audit_output_path=args.audit_output,
        completion_factory=completion_factory,
        concurrency_profile=ProductConcurrencyProfile(
            max_products=args.max_product_concurrency
        ),
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_sha256": run.run_sha256,
                "call_count": audit["call_count"],
                "metrics": audit["metrics"],
                "elapsed_seconds": round(perf_counter() - started, 3),
                "output": str(args.output.resolve()),
                "audit_output": str(args.audit_output.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "M157_BASELINE_FILE_SHA256",
    "M157_BASELINE_RUN_SHA256",
    "run_m157",
]
