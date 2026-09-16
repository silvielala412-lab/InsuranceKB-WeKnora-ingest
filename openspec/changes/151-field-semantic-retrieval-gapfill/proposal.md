# 151 · 字段全材料语义召回与动态补抽升级

## Goal

让每个 Schema 字段先在产品版本的全部已解析页面中完成可度量的候选检索，再把
有边界、可定位的段落交给抽取器。重点修复业务 badcase 中“原文存在但候选为空”
和“候选页过多、正确段落被噪声淹没”两类问题，并让人工触发的动态补抽复用同一套
后端检索能力。

## Owner And Boundary

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- 一个本地 change set；预计 1–2 个工作日；不创建 PR，不提交或推送 GitHub。
- 允许读取 `E:\wiki badcase ly` 作为离线验收输入；不修改该目录。
- 本轮只修改当前 worktree、运行 bounded tests；不外发 PDF，不调用外部模型。
- 不写生产数据库，不生成 CandidateRelease，不发布或激活 Active Release。

## Requirements

- **M151-R1**：字段候选检索必须通过可插拔 `FieldCandidateRetriever` 边界执行；默认
  实现必须扫描产品版本全部已解析页面，Embedding/其他语义实现可以后接，但本轮不得
  形成外部模型依赖。
- **M151-R2**：默认检索必须同时消费字段名、字段说明、来源说明、取值说明和受控同义
  表达；年金领取、缴费与减保等字段在原文不出现字段同名标题时仍能召回相关段落。
- **M151-R3**：候选上下文以段落/表格附近窗口为基本单元，保留文档、页码和字符位置；
  高频费率表页面不得仅凭弱词命中占满一个字段的 Top 5 候选。
- **M151-R4**：普通抽取和动态补抽必须复用同一 Retriever。动态补抽仍按
  `matched_snippets -> adjacent_pages -> all_material` 扩大范围，但最后一级必须使用
  连续覆盖窗口，不得把每页平均裁成只有页首的片段。
- **M151-R5**：`gapfill` 只修改 `unknown`；已存在值只能通过显式 `review` 复核。
  新召回、Evidence 或模型失败不得使现有 Candidate 回退。
- **M151-R6**：每个目标字段保留 `scanned_page_count`、候选页、入选页和候选原因，
  区分“没有候选”“有候选但未抽出”“Evidence 待核验”。
- **M151-R7**：离线 RED/GREEN 至少覆盖同义表达、页面中段、晚页、高频噪声和可插拔
  Retriever；业务“未抽取”样本的正确支持页 Top-5 目标为 10/11。缺少可冻结页码答案的
  条目必须记为 `BLOCKED`，不得猜测成 PASS。
- **M151-R8**：本轮只证明软件与离线候选质量；provider、业务抽取率、容器、本地 live、
  provisioning 和 GitHub live 未执行时只能记 `NOT RUN`。

## Non-goals

- 不把每个字段和整份 PDF 全文重复发送给 LLM。
- 不放宽 Evidence 逐字/归一化校验，不用多次调用强行把 `unknown` 改成有值。
- 不处理无 Schema 自动生成、内容摘要完整性、生产 Job 编排或发布审核。
- 不重跑三款或八款产品，不更新 8091/5174 结果。

## Stop Conditions

- 需要外发原始材料、调用外部模型或引入在线 Embedding 才能完成 bounded tests；
- 需要修改生产数据库、Release/Active、WeKnora serving authority 或 GitHub 状态；
- 无法在不覆盖已有 Candidate 的前提下接入新 Retriever；
- 业务 badcase 没有可核验的页码/原文，导致 Top-5 指标无法建立冻结分母。
