# 156 · 七字段原子事实与完整性修复

## Goal

针对业务在六类产品中反复确认的保险责任、责任免除、缴费期限、缴费方式、
保单权益、等待期、疾病定义与认定标准七个字段，保留全材料候选，先抽原子事实，
再确定性归并和渲染最终字段。完整性与语义 Evidence 复核失败时只定向补抽相关
字段，不降低现有材料支持抽取率，也不覆盖 M155。

## Owner And Frozen Identity

- 唯一写 Owner：当前总控 Codex；执行模型：当前 Codex，`high` reasoning。
- 业务反馈：`产品知识抽取问题总结_20260910(1).xlsx`，SHA-256=
  `3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3`。
- 基线：`provider-run-m155-eight-products-concurrent.json`，run SHA=
  `dc5d3ecd2bc29a1409c1d581ffd202b03490c7a3cc8e1cda2ef0cf15092fd60b`。
- Catalog SHA：`f7fd485fda9995872e85949fdab34d5c02713de361ca1f47e669152e19258fec`。
- 产品：596、5003、1830、1814、1816、1828；20 份 PDF、390 页。
- M155 同六款材料支持基线：`133/143=93.01%`。
- Provider：百炼 OpenAI-compatible `qwen-plus`。首轮批准的 18 次调用已因
  M156 执行器字段拓扑接线缺陷全部失效；2026-09-11 用户追加批准修复后重新
  外发同六款 20 份 PDF，并最多追加 18 次调用。
- 一个本地 change set，预计 0 PR、一个开发和真实评测周期。

## Requirements

- **M156-R1**：七个目标字段必须先遍历产品全部解析页建立候选集合；最终 LLM 上下文
  可以有预算，但不能在候选构建前丢页。每字段保留候选覆盖回执和来源页序。
- **M156-R2**：保险责任、责任免除、疾病定义必须先形成带稳定顺序、条件、例外和
  item-level Evidence 的原子事实，再渲染现有 Schema 值；不得直接用单段摘要冒充完整事实。
- **M156-R3**：缴费期限与缴费方式分别建立允许值集合，区分正式产品选项、条款约定和
  演示/举例/费率表单个样例；多个正式值必须合并，不能选一个样例结束。
- **M156-R4**：等待期必须区分时长、适用责任、意外例外和等待期内后果；保单权益必须
  逐项判断 `present | absent_explicitly | unknown`，无支持证据不得生成权益。
- **M156-R5**：完整性复核必须检查候选章节覆盖、编号项覆盖、关键条件/例外和跨字段
  一致性。`unknown`、不全、错误、概括不全、概括错误、弱 Evidence 均可进入一次定向
  补抽；候选不足时扩大全材料上下文，而非重复同一片段。
- **M156-R6**：Evidence 复核除了 locator/quote 存在，还必须验证候选值的字段、主语、
  条件、否定和例外受该 Evidence 支持。语义不确定或新旧值冲突时保留基线并进入 review。
- **M156-R7**：把业务反馈 69 条记录/81 标签映射为回归问题池；只把明确文字事实作为
  required/forbidden 断言，截图占位和无 exact answer 的记录不得冒充 Golden。
- **M156-R8**：保留最多四路产品级并发和产品内批次串行；单个产品的解析、表格和候选
  索引在本次运行复用，不做持久化 PDF 缓存。
- **M156-R9**：首轮失败结果保留为
  `provider-run-m156-six-products-seven-field.json` 和配套 `.audit.json`；修复后重跑
  写入独立 `provider-run-m156-six-products-seven-field-rerun.json` 和配套
  `.audit.json`，追加最多 18 次 qwen-plus。材料支持口径不得低于 93.01%，端到端
  目标不超过 20 分钟，并报告七字段前后 diff、Evidence、问题闭合与残余 review。
- **M156-R10**：8091/5174 必须读取同一 exact M156 run。不得修改 Schema，不调用
  OCR/Embedding/DeepSeek，不写生产 DB/Release/Active，不 commit/push/PR。

## Stop Conditions

- 业务表、M155、Catalog 或六款材料 identity 漂移；
- 修复后重跑需要超过追加的 18 次调用、扩大产品范围或调用未授权 Provider；
- 持续 429/Provider 错误，或结果合同/digest/产品顺序无效；
- 六款材料支持抽取率低于 93.01%，或明确正确字段被新结果覆盖；
- 继续需要修改 Schema、生产状态、发布链或当前 Owner 路径之外的模块。

## Non-goals

- 不动态扩展 Schema，不把业务反馈答案注入生产 Prompt。
- 不追求整本 PDF 单次塞入模型，不建立持久化候选缓存。
- 不把本轮业务抽取结果描述为正式 Candidate、Active 或生产质量批准。
