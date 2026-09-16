# 123 · Implementation Tasks

## Task 0 · Governance

- [x] Record Mission 136 local-only exception in the 830 goal card.
- [x] Occupy OpenSpec 123 in the registry.
- [x] Record RED before implementation.

  RED evidence: before the resolver existed, collection of
  `test_semantic_resolution_136.py` failed because
  `SEMANTIC_RESOLUTION_PROMPT_VERSION` and `semantic_resolution` were absent.

## Task 1 · Semantic resolver

- [x] Add a versioned semantic-resolution prompt and typed resolver result.
- [x] Preserve candidate values, Evidence, source page context and attempt identity.
- [x] Return explicit `candidate_unresolved` on parse/transport/Evidence failure.

## Task 2 · Pipeline wiring

- [x] Route deterministic candidates through the resolver before final merge.
- [x] Keep existing generic extraction, vote, gapfill and Evidence gates intact.
- [x] Ensure resolver failures do not create unverified present values.

## Task 3 · Verification

- [x] Add RED/GREEN tests for fastpath candidate LLM invocation.
- [x] Add tests for competing candidates and unverifiable resolver output.
- [x] Run focused compiler tests and `git diff --check`.
- [x] Record provider/live as `NOT RUN` and list remaining work.

Verification receipt:

- `pytest -q harness/tests/test_semantic_resolution_136.py harness/tests/test_compiler_extract.py` → `12 passed`.
- `ruff check` on changed Python files → `All checks passed`.
- `python -m compileall -q harness/src/insurance_harness/compiler` → pass.
- `git diff --check` → pass.
- Full template pipeline test is `NOT RUN` on this Windows host: the unchanged
  baseline uses POSIX-only `fcntl`/`O_DIRECTORY`/`O_NONBLOCK` run/source locking.
- Real provider, PDF transfer, database, Candidate/Release/Active and live
  deployment are `NOT RUN` by Mission 136 scope.
