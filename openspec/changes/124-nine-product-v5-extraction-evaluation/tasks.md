# 124 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 139 approval and exact external-call boundary.
- [x] Occupy OpenSpec 124.
- [x] Record failing backend and frontend checks for the old 3-product/12-call bounds.

  RED evidence:

  - `pytest -q harness/tests/test_v5_nine_product_trial_m139.py` failed with
    `len(APPROVED_PRODUCTS) == 3` and `MAX_PROVIDER_CALLS == 12`.
  - the focused TypeScript test rejected the 9-product/18-call fixture with
    `V5_PROVIDER_TRIAL_CONTRACT_INVALID`.
  - the same broad Node command also hit the unchanged `.vue` loader limitation; that
    environment error is not counted as RED.
  - the first exact 27-PDF manifest preparation stopped before provider use with
    `V5_SOURCE_TEXT_TOO_LARGE` on the 68-page annuity rate table. The bounded fix must
    still scan every page before applying provider context limits.

## Task 1 · Frozen nine-product manifest

- [x] Add six immutable product manifests with PDF hashes, page counts and Schema classes.
- [x] Replace the three-product topology assertion with exact nine-product/schema assertions.
- [x] Keep file/hash/page/product-version drift fail closed.

## Task 2 · Bounded run and UI contract

- [x] Admit at most 9 products and 18 standard provider attempts.
- [x] Keep each product at at most two standard attempts for M139.
- [x] Update the frontend closed contract and tests for 9 products/18 calls.

## Task 3 · Validation and provider run

- [x] Run focused backend/frontend tests and compile checks.
- [x] Verify M137/M138 hashes before and after M139.
- [x] Run the frozen 9-product corpus and write only the M139 artifact.
- [x] Produce per-product/per-class metrics and a bounded next-step decision.
- [x] Switch local 8091 to M139 and smoke-test 5174.

  Validation evidence:

  - M139 run: `v5-trial-5d2422bb890ff637`, 9 products, 27 PDFs, 399 pages,
    9 recorded calls, `COMPLETED`.
  - Run digest:
    `711ec746ac4af15ff54f19f43514346ce57c152e8044a28ae98912948098ef60`.
  - M137 file SHA-256 remains
    `7F08F11610B1CA3A3665D0DECE9BF40B82337ED9522695250E1A573D26C2050E`.
  - M138 file SHA-256 remains
    `4AF90F103A688B3A03DEC35B7C813EEC0976A91D9515111F9B8368B980AB9A91`.
  - 8091 returned the exact M139 run and 9 product versions; 5174 returned 200 and
    browser verification showed `9/9 款已有数据` with cross-schema switching.
  - Report: `docs/insurance-kb/32-m139-nine-product-extraction.md`.

## Delivery dimensions

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | focused backend/frontend tests, compileall, contract checks |
| container health | NOT RUN | M139 uses local Python/Vite processes, not an exact container image |
| provider probe | PASS | exact qwen-plus M139 run above; no semantic quality claim |
| provisioning | NOT RUN | no migration, DB, key ring, backfill or production config |
| local live | PASS | exact M139 on 8091 and nine-product UI on 5174 |
| GitHub live | NOT RUN | no commit, push, PR or remote CI |

Business status remains `NOT RUN`: no Candidate, Golden approval, ReviewDecision,
Release, publish or activation was performed.
