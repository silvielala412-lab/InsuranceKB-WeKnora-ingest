# 142 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 142 approval and exact external-call boundary.
- [x] Occupy OpenSpec 142.
- [x] Add failing tests for mixed-mode repair eligibility, semantic aliases, material support
  tri-state and support-conditioned rate.

## Task 1 · Candidate and repair recall

- [x] Include mixed `原文抽取 + LLM生成` fields in normal and targeted PDF extraction.
- [x] Expand semantic candidate aliases for audience, rate adjustment and product conversion.
- [x] Add field-specific LLM instructions that distinguish general rate adjustment from underwriting
  surcharge and distinguish conversion from ordinary renewal.

## Task 2 · Material support accounting

- [x] Add field-level `supported/ambiguous/unsupported` decisions with candidate locators.
- [x] Persist per-product support-conditioned numerator, denominator and rate in the trial artifact.
- [x] Keep unknown, unresolved Evidence and source-missing fields separately visible.

## Task 3 · Three-product validation and delivery

- [x] Run focused RED/GREEN and regression tests.
- [x] Run the approved 596/5003/1826 trial within the 12-call ceiling; do not overwrite M141.
- [x] Compare material-supported extraction rate and field deltas by product.
- [x] Update local 8091/5174 and record six delivery dimensions.

## Validation Evidence

- RED: `test_v5_material_support_m142.py` initially failed at collection because the material
  support module did not exist.
- Software: M142 tests 3 passed; M140/M141/M139 focused regressions 11 passed; Ruff passed.
- Provider: first run `v5-trial-53049f7103b8b10`, 6 calls; second variance run
  `v5-trial-788b9a30d902608b`, 6 calls; both 3/3 previews and no source drift.
- Local live: `GET /v5-preview-api/health`, `GET /v5-preview-api/provider-run` on 8091 and
  `GET /v5-preview` through 5174 returned HTTP 200; backend run id is the first M142 run.
- Frontend contract: the old exact product-key parser initially rejected M142 diagnostic fields;
  RED was reproduced, the parser was made backward-compatible, and the live page now renders
  all 3 previews with values.
- No production DB, Candidate, Release, Active or GitHub effects.
