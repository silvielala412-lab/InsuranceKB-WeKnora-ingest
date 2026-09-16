# 149 · 六险种本地抽取预览

## Goal

在不重跑、不覆盖 Mission 146 原三款结果的前提下，使用当前本地抽取代码补跑
年金险、意外险和失能收入损失保险各一款，并在 5174 提供六款、六险种的统一预览。

## Owner And Budget

- 唯一写 Owner：当前总控 Codex；执行 effort：`high`。
- 新增产品：1830、1814、1816；共 9 份 PDF。
- Provider：百炼 `qwen-plus`，最多 6 次调用，每款最多 2 次。
- 本地一个 change set；不创建 PR，不提交或推送 GitHub。

## Frozen Inputs

- 基线 artifact：`provider-run-m146-three-products-supplemental.json`，文件 SHA-256
  `e0fbf7f6484a1355738e45d08906945306754a1e3e082e6ec1f126b2de90ff66`，run
  `v5-trial-62ef515559bba588`，run SHA-256
  `79f0caa6900f91e44d078b8c9c1d3f265668c7a2a3da7a1b1561d4430772ec95`。
- 新增产品严格使用 `APPROVED_PRODUCTS` 中冻结的产品身份、文件名、SHA-256 和页数：
  年金险 1830、意外险 1814、失能收入损失保险 1816。
- 当前 RED：8091 仅返回 3 款，险种集合仅为医疗险、终身寿险、两全保险。

## Requirements

- `M149-R1`：Provider 调用前必须严格验证新增 3 款 9 份 PDF 的冻结身份；漂移时零调用。
- `M149-R2`：仅调用新增 3 款，最多 6 次 `qwen-plus`；每次调用保留 request/response
  摘要回执，任一产品失败不得伪装成功。
- `M149-R3`：新增结果写入独立 `provider-run-m149-extra-three-types.json`，不得覆盖
  M146 或其它历史 artifact。
- `M149-R4`：六险种展示 artifact 必须保留 M146 三款 product payload 的 exact
  canonical bytes，并追加 M149 三款；总产品数为 6、险种去重数为 6。
- `M149-R5`：组合 artifact 必须重新计算 run identity/digest，通过现有
  `V5ProviderTrialRun` loader 校验，并保留两个源 artifact 以供回验。
- `M149-R6`：只有组合 artifact 完整且有效后才允许更新本地 8091；5174 必须显示
  六款并可切换到三个新增险种。
- `M149-R7`：`serving_effect=NONE`、`review_publish_admission=false`；不写生产 DB，
  不形成 Candidate、Release 或 Active，不执行 GitHub 写入。

## Stop Conditions

- 任一冻结样本身份漂移；
- 6 次调用用尽仍有产品没有 Preview；
- 组合过程改变 M146 三款 payload，或现有合同无法诚实表达组合结果；
- 需要修改抽取代码、生产数据或发布链。
