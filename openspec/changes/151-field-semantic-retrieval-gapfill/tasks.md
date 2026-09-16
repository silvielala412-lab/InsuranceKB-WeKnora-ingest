# 151 · Implementation And Validation

## Task 0 · Governance And RED

- [x] Mission 151 approved; local-only and provider-zero boundaries frozen.
- [x] Occupy OpenSpec 151 and freeze M151-R1 through M151-R8.
- [x] RED: old locator failed the four frozen cases for synonym-only recall, fee-table noise,
  long-page middle content and Retriever injection.
- [x] GREEN: six M151 cases now cover those failures plus answer-shaped ranking and the optional
  semantic scoring port.

## Task 1 · Candidate Retrieval

- [x] Add the `FieldCandidateRetriever` protocol and a deterministic all-page default retriever.
- [x] Build field query terms from the full Schema definition plus bounded domain synonym groups.
- [x] Rank paragraph/table windows, apply weak-document penalties and preserve candidate reasons.
- [x] Keep the current public locator helpers compatible while routing them through the retriever.

## Task 2 · Dynamic Gapfill

- [x] Reuse the Retriever for matched and adjacent scopes.
- [x] Replace equal page-head truncation with ordered head/middle/tail windows for all-material
  fallback, while candidate pages use their matched character span.
- [x] Preserve the M148 request, merge and serving-effect contracts.

## Task 3 · Validation

- [x] Run focused RED/GREEN tests, all nine V5 test files, Ruff, strict Mypy and compileall.
- [x] Audit all 11 direct `未抽取` rows against the frozen source PDFs. Supporting passages are
  present in Top 5 for 11/11 fields; this is candidate recall, not completed value extraction.
- [x] Record Requirement and six-dimension delivery matrices.

## Requirement Matrix

| Requirement | Implementation | Test | Commit | Status |
|---|---|---|---|---|
| M151-R1/R6 | `dynamic_ingest.py` Retriever protocol/default, offsets and reason receipts | M151 injection + semantic-port cases | NOT RUN | PASS |
| M151-R2/R3 | Schema query terms, answer-shape rank and weak-table cap | M151 synonym, answer-shape and noise cases | NOT RUN | PASS |
| M151-R4/R5 | `dynamic_gapfill.py` shared Retriever and distributed fallback; M148 merge unchanged | M151 dynamic injection/middle-page + M148 suite | NOT RUN | PASS |
| M151-R7/R8 | 11-row local source audit and delivery ledger | 37 V5 tests; Ruff; strict Mypy; compileall | NOT RUN | PASS |

## Delivery Matrix

| Dimension | Status | Receipt |
|---|---|---|
| software | PASS | 37 V5 tests; Ruff; strict Mypy; compileall; badcase Top-5=11/11 |
| container health | NOT RUN | out of scope |
| provider probe | NOT RUN | provider-zero mission |
| provisioning | NOT RUN | out of scope |
| local live | NOT RUN | no service update authorized |
| GitHub live | NOT RUN | no commit/push/PR authorized |

`BUSINESS=NOT RUN`：本轮没有执行真实模型抽取。`11/11` 只表示正确支持段落进入
Top 5，不能写成字段已经填充，也不能据此宣称抽取率或准确率已经提高。
