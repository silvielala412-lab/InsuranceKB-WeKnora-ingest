# 155 · Execution And Validation

## Task 0 · Freeze

- [x] Mission 155 approved.
- [x] OpenSpec 155 occupied and M155-R1 through M155-R7 frozen.
- [x] Baseline/Catalog/product/file/page identities frozen.
- [x] RED: M155 artifact does not exist and 8091/5174 are not serving it.

## Task 1 · Provider Run

- [x] Inject the approved credential into this process only.
- [x] Run eight products through M154 with max concurrency 4 and max 18 calls.
- [x] Validate result and audit contracts, digests, product order and timing receipt.
- [x] RED: strict Python-object validation rejects JSON arrays for tuple receipt fields after
  a valid audit is written; validate the reconstructed envelope through the JSON boundary.

## Task 2 · Local Preview

- [x] Start 8091 against exact M155 artifact and probe health/provider-run.
- [x] Start 5174 against 8091 and probe the preview page/API.
- [x] Report extraction metrics, true timing, provider outcome and remaining gaps.

## Requirement Matrix

| Requirement | Receipt | Status |
|---|---|---|
| M155-R1/R2 | 8 products/26 PDF/454 pages; 16/18 calls; peak provider=4; no 429 | PASS |
| M155-R3/R4 | M155 result/audit load and digest validation; stable 8-product order | PASS |
| M155-R5 | 22m29.5s total; 15m22.4s parse; 12.8s plan; 6m54.0s provider | PASS |
| M155-R6 | 8091 health/provider-run and 5174 page/proxy return exact M155 run | PASS |
| M155-R7 | serving_effect NONE; review_publish_admission false; no DB/GitHub write | PASS |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | inherited exact M154 code: 55 V5 tests |
| container health | NOT RUN | v5 preview does not require containers |
| provider probe | PASS | qwen-plus 16/18 attempts; 15 accepted and one bounded contract-error retry; 0 HTTP 429 |
| provisioning | NOT RUN | production provisioning out of scope |
| local live | PASS | 8091 and 5174 return `v5-trial-ef6326d0223e4a22`, 8 products, same run SHA |
| GitHub live | NOT RUN | no commit/push/PR authorized |

`BUSINESS=REVIEW_REQUIRED`：真实抽取已完成，材料支持口径为 `172/185=92.97%`；
准确率未由人工 Golden 复核，8 款仍含 unknown 或 Evidence 审核项，不能写成已发布知识。
