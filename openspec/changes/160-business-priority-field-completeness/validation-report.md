# Mission 160 Validation Report

Date: 2026-09-15

## Identity

- Baseline: M159 result `provider-run-m159-six-products-business-quality.json`, file SHA-256 `4d40afd1be7615daf185512dc52b641df1b5df07814bec8c67401938d929fa70`, run SHA-256 `d7c5819ac8feda7c5d6d8a4e31595c99be7081da19416d5dd0f3064f420e7b4a`.
- Business feedback: `产品知识抽取问题总结_20260910(1).xlsx`, SHA-256 `3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3`.
- Catalog: `f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec`.

## Requirement Matrix

| Requirement | Implementation | Test / receipt | Status |
|---|---|---|---|
| M160-R1 | `m160_quality.py` composite parser and fail-closed Evidence audit | 2 focused tests; M159 preflight identifies 596 missing `start`, 1828 missing `within_wait_consequence` | PASS |
| M160-R2 | Existing full-page scan and long-field shard receipts reused by `m160_run.py`; missing historical 596 one-pager remains explicit unreadable | Local material preflight: 390 scanned, 388 readable, 2 unreadable; plan 28 primary calls | PASS |
| M160-R3 | M160 repair hint requires labelled waiting components and formal payment sets; long fields retain atomic item rules | M158 regression suite 9/9 | PASS |
| M160-R4 | Verified/normalized Evidence subset and waiting component support gate | Focused fail-closed test; compileall | PASS |
| M160-R5 | Independent M160 runner, M159 baseline identity, max 32 qwen-plus contract | `provider-run-m160-six-products-business-priority.json`; run `v5-trial-d145de09d8cbefea`; 30 calls; one 1828-1 long-field item remained incomplete after one retry and was fail-closed | PASS |
| M160-R6 | Existing machine-readable feedback evaluator reused | `provider-run-m160-six-products-business-priority.feedback.json`: 6 RESOLVED / 3 PARTIAL / 3 UNRESOLVED / 18 NOT_SCORABLE | PASS |

## Delivery Dimensions

| Dimension | Status | Evidence |
|---|---|---|
| software | PASS | Full V5 suite 82 passed (2 warnings); M160 focused 2/2, M158 regression 9/9, strict mypy, Ruff, compileall |
| container health | NOT RUN | No exact container probe in this mission |
| provider probe | PASS | BaLian compatible endpoint, `qwen-plus`; 30 bounded calls total, 28 accepted and 2 incomplete attempts for the same long-field item, which failed closed after retry |
| provisioning | NOT RUN | No migration/config/provider provisioning authorized |
| local live | PASS | 8091 loads M160 run `v5-trial-d145de09d8cbefea`; 5174 `/v5-preview` returns HTTP 200 |
| GitHub live | NOT RUN | No CI, push, deployment or merge |

## Business Preflight Finding

The new gate is stricter than M159 for the exact business issue: the M159 596 waiting value has duration, applicability, accident exception and consequence but no explicit start component; the M159 1828 value has duration, start, applicability and accident exception but no explicit within-wait consequence. In the M160 rerun, 596 expands from 45 to 255 characters and 1828 from 112 to 123 characters, with labelled composite waiting components and two Evidence items each. 1816 also retains both the special-disease and major-disease waiting consequences. 5003, 1830 and 1814 remain `unknown` because the bounded material/context did not yield a verified waiting-period fact; the runner does not invent a default waiting period. Feedback assessment is 6 RESOLVED / 3 PARTIAL / 3 UNRESOLVED / 18 NOT_SCORABLE; overall material-supported extraction remains 133/143 (93.01%), so this run proves targeted completeness gains rather than a global recall increase.

No Candidate, Draft, Release, Active or serving effect was created.
