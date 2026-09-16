# 153 · Implementation And Validation

## Task 0 · Freeze And RED

- [x] Mission 153 approved with no-provider, no-persistent-cache boundaries.
- [x] Occupy OpenSpec 153 and freeze M153-R1 through M153-R8.
- [x] Freeze exact XLSX, Schema and M152 identities (the four workbook SHA values remain
  the M152-approved identity; catalog and M152 baseline identities are unchanged).
- [x] RED: business issue rows and embedded assets are not a closed typed contract.
- [x] RED: existing retrieval loses table coordinates and repeats candidate work.
- [x] RED: an inferior rerun proposal can reintroduce a previously fixed problem.

## Task 1 · Business Quality Baseline

- [x] Add the closed badcase contract and frozen four-product data.
- [x] Preserve unmapped/schema-gap/display-only records explicitly.
- [x] Add required/forbidden/allowed constraints without leaking them into extraction prompts.

## Task 2 · Table-Aware Retrieval And Performance

- [x] Add page-table structures and local extraction diagnostics.
- [x] Route rate-table rows only to related Schema fields.
- [x] Add per-run page/table/candidate index reuse and context deduplication.
- [x] Add deterministic bounded-concurrency planning and stable merge contract.

## Task 3 · Regression Protection And Offline Validation

- [x] Add field-type-aware deterministic regression decisions.
- [x] Validate the four workbooks and 47 mapped issue fields offline.
- [x] Record context size, duplicate work and timing receipt contract; 121-page synthetic
  benchmark retained 1/1 target hit and reduced 59,924 to 199 characters; no provider timing
  comparison is claimed.
- [x] Record Requirement and six-dimension delivery matrices.

## Requirement Matrix

| Requirement | Implementation | Test | Commit | Status |
|---|---|---|---|---|
| M153-R1/R2 | `m153_quality.py` typed workbook parser and issue normalization | `test_v5_m153_business_quality_performance.py` | NOT RUN | PASS |
| M153-R3/R4 | `TablePage`, M152 table load/routing, issue-aware plan | `test_v5_m153_business_quality_performance.py` | NOT RUN | PASS |
| M153-R5/R6 | `compare_field_value`, M152 context/candidate caches | `test_v5_m153_business_quality_performance.py` + M152 regression | NOT RUN | PASS |
| M153-R7/R8 | context receipt and `plan_bounded_batches` | `test_v5_m153_business_quality_performance.py` | NOT RUN | PASS |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | 9 M153 tests; 25 focused M148-M152 tests; all 49 V5 tests; Ruff, M152/M153 strict mypy, compileall |
| container health | NOT RUN | no container work authorized |
| provider probe | NOT RUN | provider calls explicitly excluded |
| provisioning | NOT RUN | production provisioning out of scope |
| local live | NOT RUN | 8091/5174 business result must remain M152 |
| GitHub live | NOT RUN | no commit/push/PR authorized |

`BUSINESS=NOT RUN`：本轮只建立本地质量与性能控制能力，不运行真实抽取。
