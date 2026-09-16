# 144 · Implementation Tasks

## Task 0 · Governance and RED

- [x] Record Mission 144 approval and exact code-only boundary.
- [x] Occupy OpenSpec 144.
- [x] Add failing tests for content target scheduling, all-page context, prompt constraints,
  and preservation of existing facts.

## Task 1 · Content synthesis target and context

- [x] Include unknown pure LLM content fields in the bounded repair target selection.
- [x] Reuse ordered all-page context for content fields without changing material-support metrics.

## Task 2 · LLM prompt and merge

- [x] Add field-specific instructions for product summary and overview.
- [x] Pass verified prior facts as synthesis context and keep Evidence mandatory.
- [x] Preserve stronger existing values when content synthesis returns unknown or weaker output.

## Task 3 · Local validation

- [x] Run RED/GREEN and relevant regression tests.
- [x] Verify no provider calls, DB writes, Release/Active effects, or GitHub operations.
- [x] Record the next provider-run command separately for user approval.

## Validation Evidence

- RED: the new test module initially failed during collection because
  `M144_CONTENT_SYNTHESIS_FIELD_IDS` and `_content_synthesis_targets` did not exist.
- Software: `PASS` — 23 V5/Python regression tests, 9 frontend contract tests, ruff,
  compileall, and `git diff --check` passed.
- Provider probe: `NOT RUN` — no external model calls in Mission 144.
- Provisioning/local live: `NOT RUN` — no service or artifact switch was needed; M143 remains
  the serving preview result.
- GitHub live: `NOT RUN` — no commit, push, CI, Release, Candidate, or Active operation.
