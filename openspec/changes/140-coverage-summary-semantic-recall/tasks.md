# 140 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 140 approval and exact external-call boundary.
- [x] Occupy OpenSpec 140.
- [x] Add failing tests for semantic responsibility anchors, cross-document merge, and
  filename-independent candidate selection.

## Task 1 · Candidate recall

- [x] Add a dedicated `coverage_summary` semantic candidate selection path.
- [x] Preserve full-page scan receipt and field-centered snippets under the provider budget.
- [x] Include neighboring responsibility pages when a semantic anchor is found.

## Task 2 · LLM extraction and merge

- [x] Add field-specific instructions for coverage synthesis and evidence-per-item output.
- [x] Keep existing tri-state, value, and Evidence contracts; do not lower hallucination checks.
- [x] Ensure a supported value is not discarded only because Evidence needs review.

## Task 3 · Three-product run and delivery

- [x] Support an exact three-product M140 run without changing M139 artifact.
- [x] Run bounded backend/frontend tests and the approved qwen-plus trial.
- [x] Produce per-product coverage and non-regression metrics.
- [x] Update local 8091/5174 and record six delivery dimensions.

## Validation Evidence

- RED: before implementation, `build_coverage_summary_source_text` was missing and
  `tests/test_v5_coverage_summary_m140.py` failed during collection.
- Software: 128 focused backend/schema tests passed; Ruff passed; frontend build/type
  check recorded separately in the M140 report.
- Provider: first run `v5-trial-d6856ee4b4a70453`, 6 qwen-plus calls, 3/3 previews;
  second comparison run `v5-trial-9803e4ff2e327d93`, 6 calls, retained separately.
- Local live: 8091 returns the first M140 run and 5174 returns HTTP 200; no DB,
  Candidate, Release, Active or GitHub effects.

## Deferred follow-up: material-supported extraction recall

The no-schema discovery flow is intentionally deferred. Keep the current V5
Schema path as the regression baseline while the following recall work is
prepared under a new Mission/OpenSpec:

- [ ] Add field-level diagnostics: `material_unavailable`,
  `candidate_not_found`, `candidate_found_not_extracted`, and
  `evidence_unresolved`.
- [ ] Re-run all `unknown` fields against the full parsed page set, not only
  the first ranked pages; retain page locators and short snippets in the
  diagnostic artifact.
- [ ] Add a semantic synthesis path for fields whose schema description allows
  a bounded summary, especially `target_customer_profile` ("适用人群").
  A same-name heading is not required when age, eligibility, product purpose,
  or audience language jointly support the value.
- [ ] Add a field-level second pass for `candidate_found_not_extracted`, with
  the first candidate preserved when the second pass is weaker.
- [ ] Do not count external-master-data fields or absent source document types
  as model misses; keep them in the denominator only when the metric explicitly
  says so.
- [ ] After the recall pass, compare `present / material_supported` by product
  and by insurance class. Do not claim accuracy without a human Golden set.

### Initial material audit for the three M140 products

The following high-confidence finding is recorded for the next task:

| Product | Field | Source evidence found | M140 state | Diagnosis |
|---|---|---|---|---|
| 596 | 适用人群 | 产品说明书 p1; 保险条款 p2, p24: medical purpose, age 0-70, conditional 71-100, eligible family members | `unknown` | `candidate_found_not_extracted`; the field is synthesizable from eligibility and audience signals |
| 5003 | 适用人群 | 产品说明书 p1; 保险条款 p1-p2: family protection, parent/child dual-insured design, age 0-71, one/two insured persons | `unknown` | `candidate_found_not_extracted`; no literal audience heading, but material supports a bounded profile |
| 1826 | 适用人群 | 产品说明书 p1, p5: adult/child age segmentation, family-life purpose, age 0-52 and term selection | `unknown` | `candidate_found_not_extracted`; product-purpose and eligibility text jointly support a bounded profile |

Other likely material-supported misses are `health_declaration_requirements`,
`underwriting_method`, `premium_payment_term`/`premium_payment_frequency`,
`sum_assured_range`, and selected `additional_benefit_rules` or derived risk
flags. They must be confirmed with field-specific page evidence before changing
the metric. Fields that require an absent poster, sales PPT, service list, or
master-data XLSX remain `material_unavailable` until those source types arrive.
