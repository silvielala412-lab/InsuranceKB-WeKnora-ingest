# 152 · Implementation And Validation

## Task 0 · Freeze And RED

- [x] Mission 152 approved with eight-product, 18-call and local-live boundaries.
- [x] Occupy OpenSpec 152 and freeze M152-R1 through M152-R8.
- [x] Freeze exact baseline/material/business-label identities and target manifest.
- [x] RED: existing runner cannot produce bounded gapfill/review batches from an existing artifact.
- [x] RED: conflicting review suggestions could be mistaken for automatic replacements.

## Task 1 · Runner And Contract

- [x] Add a closed local result contract and bounded target planner.
- [x] Reuse M151 Retriever and existing provider/Evidence adapters.
- [x] Preserve unknown-only gapfill and before/proposed/after review semantics.
- [x] Enforce the 18-call hard budget and independent output path.

## Task 2 · Provider And Evaluation

- [x] Run all eight products; preserve the final 15 provider receipts in the main artifact.
- [x] Validate the main output contract and calculate fill/material-support/Evidence metrics.
- [x] Stop at the approved 18-call Mission ceiling and record the missing review sidecar as BLOCKED.

## Task 3 · Local Preview

- [x] Point 8091 to the M152 artifact and verify JSON response identity.
- [x] Start/verify 5174 and verify the browser route returns the M152 data.
- [x] Record Requirement and six-dimension delivery matrices.

## Requirement Matrix

| Requirement | Implementation | Test | Commit | Status |
|---|---|---|---|---|
| M152-R1/R2 | frozen input constants, target planner | M152 identity/planner tests | NOT RUN | PASS |
| M152-R3/R4 | bounded batches, Retriever context, protected merge, absence safeguard | M152 batch/merge/absence tests | NOT RUN | PASS |
| M152-R5/R6 | main artifact complete; audit constructor fixed after run | main artifact validation PASS; full audit reload NOT RUN | NOT RUN | BLOCKED |
| M152-R7/R8 | material/fill/Evidence metrics and local preview | HTTP identity probes PASS; review metrics unavailable | NOT RUN | BLOCKED |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | 16 focused M152/M151/M148 tests; Ruff; compileall |
| container health | NOT RUN | no container deployment authorized |
| provider probe | PASS | qwen-plus; 3 prior attempts plus 15 final accepted batches = 18/18 |
| provisioning | NOT RUN | production provisioning out of scope |
| local live | PASS | 8091 and 5174 return run `v5-trial-7a6372c9c5d8818e`, 8 products |
| GitHub live | NOT RUN | no commit/push/PR authorized |

`BUSINESS=BLOCKED`：本地缺失字段补抽已完成（新增 22 个字段；材料支持口径
`172/185=92.97%`），但现有错误/不完整字段的 review sidecar 在主结果写入后校验失败，
未保留完整 before/proposed/diff；也没有人工 Golden 准确率结论。详见
`docs/insurance-kb/47-m152-eight-product-dynamic-gapfill.md`。
