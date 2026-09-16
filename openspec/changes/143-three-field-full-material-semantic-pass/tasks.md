# 143 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 143 approval and exact sample/provider boundary.
- [x] Occupy OpenSpec 143.
- [x] Add failing tests for candidate-free full-material context, forced target repair, and
  semantic distinctions among grace period, conversion, and rate adjustment.

## Task 1 · Full-material target context

- [x] Add a bounded, ordered all-page context builder for the three target fields.
- [x] Record per-field scanned/selected page coverage without changing ordinary field batching.

## Task 2 · Semantic extraction and merge

- [x] Force target fields into the first/repair LLM pass when they are applicable and unknown.
- [x] Add field-specific prompt rules and conservative value normalization for explicit negative
  statements.
- [x] Preserve stronger prior values and all valid Evidence during merge.

## Task 3 · Five-product validation and delivery

- [x] Run focused RED/GREEN and regression tests.
- [x] Run the approved five-product qwen-plus trial within 15 calls.
- [x] Calculate material-supported extraction rate and field-level deltas against M142.
- [x] Update local 8091/5174 only after the new artifact is complete; record live probes.

## Validation Evidence

- RED: `test_v5_three_field_semantic_m143.py` initially failed with
  `ImportError` for the not-yet-implemented full-material context builder; after the patch
  the same focused suite passed.
- Software: `PASS` — 17 Python tests, ruff checks, and 9 TypeScript contract tests passed.
- Provider probe: `PASS` — run `v5-trial-d51edcaae8aa3e36`, `qwen-plus`, 10 calls/15 maximum,
  5 products/15 PDFs, output `provider-run-m143-five-products.json`.
- Provisioning: `NOT RUN` — no migration, backfill, production configuration, or database write.
- Local live: `PASS` — 8091 health/provider-run and 5174 page/proxy returned HTTP 200;
  both provider endpoints returned the exact M143 run id.
- GitHub live: `NOT RUN` — no commit, push, CI, Release, Candidate, or Active operation.
