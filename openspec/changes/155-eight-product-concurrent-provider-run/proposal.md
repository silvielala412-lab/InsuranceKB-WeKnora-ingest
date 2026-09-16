# 155 · 八款产品四路真实抽取

## Goal

使用 Mission 154 已验证的四路产品级并发入口，重跑当前八款冻结产品；生成不覆盖
历史结果的 M155 artifact 与 audit，并让本地 8091/5174 展示本轮结果。真实记录完整
耗时、调用预算、429 降级、材料支持抽取率和产品终态。

## Frozen Identity

- 基线文件：`provider-run-m150-eight-types.json`
- 基线文件 SHA：`87d6faf3e578daf75010d75c388116d9f9c6316d8b370ba3abeb74654f5557a8`
- 基线 run SHA：`dd759dbc02548d0951bf255d5aa27d756764f4794fd7382758eb10c3fdda2b69`
- Catalog SHA：`f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec`
- 范围：8 款、26 份 PDF、454 页；包含 596 已冻结的两份服务补充材料。
- Provider：百炼 OpenAI-compatible endpoint，`qwen-plus`，最多 18 次调用。
- 并发：最多 4 款产品；每款内部批次串行；429 自动降至 2/1。

## Requirements

- **M155-R1**：运行前必须通过 M152 的基线、Catalog、业务问题表和全部产品材料
  identity 校验；任何漂移立即停止，不能跳过产品或换分母。
- **M155-R2**：只使用 M154 入口和默认四路容量；同产品批次串行，全局调用次数不
  超过 18，429/失败同样计入预算。
- **M155-R3**：输出写入 `provider-run-m155-eight-products-concurrent.json` 和
  `provider-run-m155-eight-products-concurrent.audit.json`，历史 M150/M152 不得覆盖。
- **M155-R4**：结果必须包含 8 款稳定顺序产品、每款终态、字段 Preview、Evidence、
  材料支持指标及 M154 `performance` 回执；合同或 digest 无效立即停止。
- **M155-R5**：报告真实总耗时和四阶段耗时、峰值产品/Provider 并发、调用次数、429
  降级事件以及按约定口径的材料支持抽取率；不得用 fixture 推导真实结果。
- **M155-R6**：8091 必须读取 exact M155 artifact，5174 必须代理同一 run；health、
  provider-run 和页面三项 live probe 分别记录。
- **M155-R7**：不修改 Schema、Prompt、Evidence、审核和回归规则；不写生产 DB，
  不形成 CandidateRelease/Release/Active，不提交或推送 GitHub。

## Stop Conditions

- frozen identity 漂移或任一产品材料缺失；
- 百炼凭据/endpoint 不可用，持续 429 或 Provider 错误使预算不足；
- 输出合同、digest、产品数或顺序校验失败；
- 继续需要修改抽取语义、扩大调用预算或写生产状态。
