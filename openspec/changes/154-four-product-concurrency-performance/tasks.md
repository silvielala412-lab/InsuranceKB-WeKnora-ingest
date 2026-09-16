# 154 · Implementation And Validation

## Task 0 · Freeze And RED

- [x] Mission 154 approved with no-provider/no-DB/no-GitHub boundaries.
- [x] Occupy OpenSpec 154 and freeze M154-R1 through M154-R8.
- [x] RED: current Provider loop cannot run separate products concurrently.
- [x] RED: current call counter is not a cross-client atomic global budget.
- [x] RED: current runner has no 429 concurrency downgrade or complete stage timing.

## Task 1 · Scheduling Contracts

- [x] Add closed capacity, global budget, adaptive gate and timing receipt contracts.
- [x] Add product-level executor with stable input-order result merge.
- [x] Keep product worker batches serial and bind every attempt to a unique global call number.

## Task 2 · Runner Integration

- [x] Give each concurrent product its own Provider client through a factory.
- [x] Connect shared budget and 429 downgrade without changing extraction/merge semantics.
- [x] Start total timing before material parsing and write stage/product/batch receipts.

## Task 3 · Offline Validation

- [x] Fake-provider tests prove peak four products and one active batch per product.
- [x] Budget contention, stable merge and 4→2→1 downgrade tests pass.
- [x] Serial/four-way fixture outputs are identical outside scheduling receipts.
- [x] Run focused V5 regressions, Ruff, strict mypy and compileall.
- [x] Record Requirement and six-dimension delivery matrices.

## Requirement Matrix

| Requirement | Implementation | Test | Commit | Status |
|---|---|---|---|---|
| M154-R1/R2 | `m154_concurrency.py` profile/gate/product executor | `test_v5_m154_product_concurrency.py` | NOT RUN | PASS |
| M154-R3/R4 | global budget, attempt wrapper, 429 downgrade | `test_v5_m154_product_concurrency.py` | NOT RUN | PASS |
| M154-R5/R6 | ordered executor, timing receipts, `m152_gapfill.py` audit integration | M154 stable merge/timing tests + M152/M153 regression | NOT RUN | PASS |
| M154-R7/R8 | frozen extraction path; fake Provider only | all 55 V5 tests, Ruff, compileall, M154 strict mypy | NOT RUN | PASS |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | 6 M154 tests; 18 M152-M154 focused tests; all 55 V5 tests; Ruff, M154 strict mypy, compileall; local equal-delay scheduler benchmark 1.217s→0.307s |
| container health | NOT RUN | no container work authorized |
| provider probe | NOT RUN | external model calls explicitly excluded |
| provisioning | NOT RUN | production provisioning out of scope |
| local live | NOT RUN | 8091/5174 result must remain unchanged |
| GitHub live | NOT RUN | no commit/push/PR authorized |

`BUSINESS=NOT RUN`：本轮只实现和验证调度能力，不运行真实产品抽取。

已知环境限制：Windows 全仓 pytest 收集被仓库既有 `fcntl` 依赖阻断；M152 全依赖
strict mypy 仍暴露 `ocr.py`、`value_constraints.py` 的 3 个既有类型错误，均不在本
Mission 写域内，且 M154 新模块 strict mypy 为 PASS。
