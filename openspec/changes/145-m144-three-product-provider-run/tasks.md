# 145 · Validation Tasks

- [x] Mission 145 approved and exact product/provider boundary frozen.
- [x] Run three products with at most six qwen-plus calls. `COMPLETED`, run
  `v5-trial-38e10677cadec24d`, 6/6 calls, 3 products and 9 PDFs. The second
  596 repair response was rejected for `LLM_RESULT_NOT_COMPLETE` (finish
  reason `length`); the first result was preserved.
- [x] Compare content fields and fact-field preservation against M143. All
  three products have `product_summary` and `product_overview` present. The
  weighted material-supported rate is `66/77=85.71%`, versus `65/77=84.42%`
  for the same three products in M143.
- [x] Update local 8091/5174 only after the artifact was valid. Both live
  endpoints return the M144 run and three products.
- [x] Record provider, provisioning, local live, and GitHub live statuses:
  provider probe=`PASS`; local live=`PASS`; provisioning=`NOT RUN`;
  GitHub live=`NOT RUN`. No production DB, Candidate/Release/Active or GitHub
  writes were performed.
