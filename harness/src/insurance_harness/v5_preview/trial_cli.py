"""Command-line adapter for the local V5 provider trial."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .provider_trial import (
    MAX_PRODUCT_ATTEMPTS,
    MAX_PROVIDER_CALLS,
    run_provider_trial,
)


def provider_trial_main() -> None:
    """Parse CLI arguments and run one bounded provider trial."""

    parser = argparse.ArgumentParser(description="Run the bounded V5 three-product trial")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/v5-provider-trial/provider-run.json"),
    )
    parser.add_argument("--max-calls", type=int, default=MAX_PROVIDER_CALLS)
    parser.add_argument("--max-product-attempts", type=int, default=MAX_PRODUCT_ATTEMPTS)
    parser.add_argument("--no-adaptive", action="store_true")
    parser.add_argument("--controlled-dynamic", action="store_true")
    parser.add_argument(
        "--product-ids",
        help="Comma-separated approved product IDs; defaults to all frozen products",
    )
    parser.add_argument(
        "--supplemental-root-596",
        type=Path,
        help="Exact Mission 146 service-material directory for product 596",
    )
    parser.add_argument(
        "--ocr-output",
        type=Path,
        help="Independent qwen-vl-ocr receipt artifact required with supplemental input",
    )
    args = parser.parse_args()
    api_key = os.environ.get("HARNESS_DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("HARNESS_DASHSCOPE_API_KEY_REQUIRED")
    run = run_provider_trial(
        source_root=args.source_root,
        output_path=args.output,
        api_key=api_key,
        progress=lambda message: print(message, flush=True),
        max_provider_calls=args.max_calls,
        max_product_attempts=args.max_product_attempts,
        adaptive=not args.no_adaptive,
        controlled_dynamic=args.controlled_dynamic,
        product_ids=(
            tuple(item.strip() for item in args.product_ids.split(",") if item.strip())
            if args.product_ids
            else None
        ),
        supplemental_root_596=args.supplemental_root_596,
        ocr_output_path=args.ocr_output,
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "status": run.status,
                "call_count": run.call_count,
                "data_products": sum(product.preview is not None for product in run.products),
                "review_required_products": sum(
                    product.status == "REVIEW_REQUIRED" for product in run.products
                ),
                "run_sha256": run.run_sha256,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    if run.status != "COMPLETED":
        raise SystemExit(2)


__all__ = ["provider_trial_main"]


if __name__ == "__main__":
    provider_trial_main()
