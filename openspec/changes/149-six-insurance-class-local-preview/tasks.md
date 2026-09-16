# 149 · Execution And Validation

- [x] Mission 149 approved; product, egress, provider and local-service boundaries frozen.
- [x] RED captured: current 8091 returns 3 products and 3 insurance classes.
- [x] Validate the 3 new products and 9 PDF identities before provider access. PASS:
  3 products, 9 PDFs and 177 pages; no provider call was made during validation.
- [x] Run products 1830, 1814 and 1816 with at most 6 qwen-plus calls. PASS:
  exactly 6 calls; all three products produced review-required previews.
- [x] Write and validate `provider-run-m149-extra-three-types.json`. PASS: run
  `v5-trial-fe63969e2c3e89d7`, run SHA-256
  `4fa080b976d9c1b009eae59e21ef438a6a53c855956187bc9c206f22bcccee5f`.
- [x] Build a six-class display artifact without changing the canonical M146 product payloads.
  PASS: `provider-run-m149-six-types.json` contains 6 products and 6 unique classes;
  the first three canonical product payloads are byte-for-byte equal to M146.
- [x] Point local 8091 to the validated display artifact and verify 8091/5174. PASS:
  both endpoints return run `v5-trial-3b724d6b6a9f380e` and six products.
- [x] Record extraction counts, material-supported rates and six delivery dimensions.
  PASS: see `docs/insurance-kb/40-m149-six-insurance-class-preview.md`.
