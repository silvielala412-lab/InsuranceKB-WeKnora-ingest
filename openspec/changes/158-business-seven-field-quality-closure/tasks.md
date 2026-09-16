# Mission 158 Tasks

- [x] Freeze Mission Card, M157 baseline, Catalog, business feedback and source-set identities.
- [x] RED: verified Evidence subset can rescue a complete candidate while unique unsupported atoms fail.
- [x] RED: disease definitions and other long fields split and merge without provider truncation.
- [x] RED: payment pair, waiting-period components and product applicability checks catch known classes.
- [x] RED: all 30 feedback rows receive an explicit assessment state without entering extraction input.
- [x] Implement bounded M158 field extraction, merge, Evidence admission and feedback evaluator.
- [x] Run focused and full V5 regression, Ruff, mypy and compile checks.
- [x] Run six products within 32 qwen-plus calls and write independent artifacts (Mission 159
  authorized rerun used the corrected 32-call envelope and preserved the failed M158 attempt).
- [x] Compare M157/M159, verify present-rate non-regression, update 8091/5174 and record live probes.
- [x] RED: exact M159 的 32 次全局调用与单产品 9 次回执被前端历史上限拒绝。
- [x] 前端结果合同与 M158 的 32 次预算对齐，并保留第 33 次失败关闭。
- [x] 用 exact M159 API 响应和 `/v5-preview` 页面完成本地回归。

## Validation Matrix

| Requirement | Implementation | Test / receipt | Status |
|---|---|---|---|
| M158-R1 | `m158_quality.py`, `m158_run.py` | focused RED/GREEN and V5 regression | PASS |
| M158-R2 | `admit_verified_evidence_subset` | focused RED/GREEN and V5 regression | PASS |
| M158-R3 | coupled compact batch and audits | focused RED/GREEN and V5 regression | PASS |
| M158-R4 | feedback XLSX reader and independent evaluator | 30-row read-only probe and focused tests | PASS |
| M158-R5 software | M158 implementation | 79 V5 tests, Ruff, strict mypy, compileall | PASS |
| M158-R5 frontend contract | `v5ProviderTrialContract.ts` | 7 contract tests, 2 component tests, `vue-tsc`, Vite production build | PASS |
| M158-R5 provider | M158 runner; provider contract cap corrected to 32 | M159 run `v5-trial-b45293f71e3b0cd0`, 32/32 calls | PASS |
| M158-R5 local live | 8091 artifact load and 5174 parser/proxy | exact M159 run parses with 32 calls and attempts `6/3/3/3/8/9`; page/module HTTP 200 | PASS |
| M158-R5 business | 30-row feedback assessment | 5 resolved, 2 partial, 5 unresolved, 18 not scorable | BLOCKED |

## RED Receipt

With the project Python, disabled third-party pytest autoload and `PYTHONPATH=harness/src`, collection
failed because `insurance_harness.v5_preview.m158_quality` did not exist. The preceding helper Python
without pytest and xonsh console failure were environment errors and are not counted as RED.
