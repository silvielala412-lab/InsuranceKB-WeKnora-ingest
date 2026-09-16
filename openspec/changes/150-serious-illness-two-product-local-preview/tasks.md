# 150 · Execution And Validation

- [x] Mission 150 approved; two serious-illness products, six PDFs, provider and local-service boundaries frozen.
- [x] RED: current registry rejected product IDs 1828 and L2332.
- [x] Add both frozen products to the local trial registry and add the Schema 67 class count.
- [x] Re-run the bounded registry/preflight tests. PASS: targeted Mission 150 and M139 compatibility tests pass; 1828/L2332 preflight loads 98 pages and 6 files with frozen identities.
- [x] Run 1828 and L2332 with at most 6 qwen-plus calls; PASS: first 2 calls exposed and fixed a failure-state contract bug, final rerun used 4 calls; Mission total 6, both products produced valid Preview receipts.
- [x] Write and validate `provider-run-m150-serious-illness.json`. PASS: run `v5-trial-701cb35731058b68`, digest-validated.
- [x] Build `provider-run-m150-eight-types.json`, preserving M149 product payloads exactly. PASS: 8 products, 7 classes, baseline payload equality.
- [x] Update local 8091 and verify 5174 exposes 8 products and 7 classes. PASS: both API endpoints and `/v5-preview` live probe.
- [x] Record material-supported extraction metrics and six delivery dimensions. PASS: see `docs/insurance-kb/41-m150-two-serious-illness-products.md`.
