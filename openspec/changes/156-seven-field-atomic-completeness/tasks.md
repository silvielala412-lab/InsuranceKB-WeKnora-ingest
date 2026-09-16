# 156 · Implementation And Validation

## Task 0 · Freeze And RED

- [x] Mission 156 approved and OpenSpec 156 occupied.
- [x] Six products, 20 PDFs, 390 pages, M155/Catalog/business workbook identities frozen.
- [x] RED: seven focus fields do not all receive an all-page candidate plan.
- [x] RED: long legal fields do not preserve item-level atomic facts and completeness receipts.
- [x] RED: payment examples, waiting-period exceptions and unsupported policy rights can survive.

RED receipt: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` with `PYTHONPATH=harness/src`, then
`python -m pytest -q harness/tests/test_v5_m156_seven_field_atomic_completeness.py`.
Collection failed on the old tree with
`ModuleNotFoundError: insurance_harness.v5_preview.m156_quality`. The earlier
missing `uv` and unrelated auto-loaded `xonsh` console failure are environment
errors and are not counted as RED.

## Task 1 · Atomic Extraction And Field Contracts

- [x] Add focus-field strategy contracts without changing the public Schema.
- [x] Add all-page candidate coverage receipts and atomic fact intermediate results.
- [x] Add payment, waiting-period and policy-rights typed reducers.

## Task 2 · Completeness And Semantic Review

- [x] Add section/item coverage, condition/exception and cross-field checks.
- [x] Route missing, incomplete, wrong and weak-Evidence fields to one bounded repair.
- [x] Preserve stronger baseline values and emit explicit review receipts for conflicts.

## Task 3 · Real Run And Local Preview

- [x] Run focused and bounded V5 tests, Ruff, mypy and compileall.
- [x] Run six frozen products with max 4 product workers and max 18 qwen-plus calls.
- [x] Validate result/audit identities, rate, timing and seven-field diff.
- [x] Point 8091/5174 at exact M156 artifact and probe both APIs/page.

First provider run receipt (failed, retained for audit): run
`v5-trial-389055027af97ceb`, run SHA
`20b5e326265d2a9062297cb0acc056a4ab548e6d0dbba7fb93007a97c594adf2`.
It parsed all 20 PDFs / 390 pages (388 readable) and consumed the approved 18/18
qwen-plus calls. All calls were rejected as
`M156_PROVIDER_FIELD_TOPOLOGY_DRIFT`, so the protected baseline was preserved:
`changed_field_count=0`, `133/143=93.01%`. The failure was an executor integration
defect: `SchemaGuidedLlmPlugin` returns the complete Schema topology while M156
compared that result directly with the bounded batch topology. The executor now
projects the full result to the requested ordered field IDs before validating and
merging. A regression test reproduces this contract and passes. A new real run was
authorized on 2026-09-11 for the same six products / 20 PDFs with at most 18
additional qwen-plus calls. It must write new `-rerun` result and audit files; the
failed output is not eligible for local preview or business comparison.

Corrected rerun receipt: run `v5-trial-b11a5d5e589ea20d`, run SHA
`cee87b1772333d263e4ffff9424daeafd303ea26189ab4aab7d627aed92e3360`.
It used 18/18 additional qwen-plus calls: 15 accepted provider contracts and 3
typed contract failures, with no 429. Six field records changed: four value changes
and two Evidence-only repairs. Material-supported extraction stayed
`133/143=93.01%`. Total time was 1457.3 seconds, so the <=20 minute target failed.
The exact business workbook has 30 focus-field issue rows but several expected
answers remain screenshot placeholders; an exact accuracy denominator is not
available. Known source-backed gains and residuals are recorded in
`docs/insurance-kb/51-m156-six-product-seven-field-rerun.md`.

## Requirement Matrix

| Requirement | Implementation | Test/Receipt | Status |
|---|---|---|---|
| M156-R1/R2 | `m156_quality.py`, `dynamic_ingest.py` | 31 focused/regression tests | PASS |
| M156-R3/R4 | `m156_quality.py`, `llm_plugin.py` | atomic/payment/waiting/rights tests | PASS |
| M156-R5/R6 | `m156_run.py` | replacement, 12-batch and full-Schema projection checks | PASS |
| M156-R7 | workbook identity/counts frozen; expected-answer injection prohibited | 30 focus rows reviewed; screenshot placeholders prevent exact automatic accuracy | BLOCKED |
| M156-R8 | four-product runner, per-product serial batches | peak product/provider concurrency 4; no persistent cache | PASS |
| M156-R9 | corrected rerun and independent audit | 18/18 calls, 6 accepted changes, 93.01%; 1457.3 seconds exceeds target | BLOCKED |
| M156-R10 | local preview API and Vite proxy | backend/proxy same run and 6 products; page HTTP 200 | PASS |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | 27 bounded regression tests (including 9 focused M156 tests), Ruff, mypy and compileall pass |
| container health | NOT RUN | no container work planned |
| provider probe | PASS | corrected rerun used 18/18 calls; 15 accepted contracts, 3 typed failures, no 429 |
| provisioning | NOT RUN | production provisioning out of scope |
| local live | PASS | 8091 and 5174 proxy return rerun `v5-trial-b11a5d5e589ea20d`, 6 products; page HTTP 200 |
| GitHub live | NOT RUN | commit/push/PR prohibited |

`BUSINESS=BLOCKED`: the corrected run improves four values and two Evidence sets
without reducing material-supported extraction, but retains known business
conflicts and incomplete long fields. The business workbook is not a complete
machine-readable Golden, so no formal accuracy claim is made.
