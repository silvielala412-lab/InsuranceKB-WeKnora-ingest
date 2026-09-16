# 141 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 141 approval and exact external-call boundary.
- [x] Occupy OpenSpec 141.
- [x] Add failing tests for value-guidance parsing, prompt contract, and conservative normalization.

## Task 1 · Value constraint compiler

- [x] Parse v5 `value_guidance` into single-choice, multi-choice, nullable and open-ended constraints.
- [x] Keep the compiler independent of product file names and external metadata.

## Task 2 · LLM contract and merge

- [x] Include the structured constraint in the field prompt.
- [x] Normalize only unambiguous values; preserve supported raw values when normalization is inconclusive.
- [x] Keep tri-state and Evidence validation unchanged.

## Task 3 · Three-product validation and delivery

- [x] Run focused backend tests and the existing v5 regression tests.
- [x] Run the approved three-product qwen-plus trial with 6 calls (within the 12-call ceiling).
- [x] Compare `present` counts against M140 and write an independent result artifact.
- [x] Update local 8091/5174 only after the artifact is complete; record live probe receipts.

## Validation Evidence

- RED: before implementation, `harness/tests/test_v5_value_constraints_m141.py` failed
  because `value_constraints` did not exist.
- Software: 11 focused v5 tests passed; Ruff passed on all touched Python files.
- Catalog: 11 schemas / 801 fields; catalog SHA and source workbook SHA unchanged.
- Provider: run `v5-trial-fb9647297bf99d1b`, 6 `qwen-plus` calls, 3/3 previews; all three
  remain `REVIEW_REQUIRED` because Evidence still needs review.
- Local live: 8091 and 5174 proxy return the M141 run with HTTP 200; no DB, Release,
  Active, GitHub or production effects.
