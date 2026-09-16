# 153 · 业务问题纠偏、表格感知与单次运行提速

## Goal

把四份业务问题表中的抽取不全、抽取错误、未抽取、未识别、LLM 概括不全和
LLM 概括错误整理为可执行的字段级质量基线。下一次真实重跑应按问题类型构建
候选、比较新旧结果并阻止已确认字段回退。同时保留全页扫描，但减少同次运行中
重复解析、重复候选计算和无关费率表上下文。

## Owner And Boundary

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- 一个本地 change set；不创建 PR，不提交或推送 GitHub。
- 允许只读四份 `E:\wiki badcase ly\*.xlsx` 及其嵌入图片，写当前 worktree。
- 不外发材料，不调用外部模型，不写生产数据库，不形成 CandidateRelease、Release
  或 Active，不更新 8091/5174 的业务结果。

## Requirements

- **M153-R1**：冻结四份业务 XLSX 的 SHA、产品映射、行号、字段名、问题类型、文字
  备注及嵌入图片 SHA。47 个可映射问题字段必须有稳定 `field_id`；无 Schema 字段和
  无问题类型记录必须显式保留，不能静默丢弃。
- **M153-R2**：问题类型必须归一为 `missing | incomplete | wrong | summary_incomplete |
  summary_wrong | display_only | schema_gap`，允许一行对应多个类型。每条记录可携带
  `required_facts`、`forbidden_facts`、`allowed_values` 和业务参考资产，但不得把业务
  标准答案注入生产抽取 Prompt。
- **M153-R3**：表格页必须形成带文档、页码、表序号、表头、行和单元格位置的只读
  结构；表格失败仍保留页面文本并输出诊断。费率表只对 Schema 来源指导或字段语义
  需要费率/金额/缴费/领取表格的字段加权，不能因文件长而进入所有字段上下文。
- **M153-R4**：问题类型决定上下文策略。`incomplete` 需要合并所有候选事实；`wrong`
  和 `summary_wrong` 必须带禁含事实检查；摘要字段先输出原子事实再形成展示值；
  `display_only` 不触发重抽。
- **M153-R5**：新增确定性回归比较器。已确认基线在新结果为 unknown、Evidence 更差、
  缺少必含事实、出现禁含事实或不满足允许值时不得被覆盖；输出 `keep_baseline |
  accept_candidate | needs_review | regression` 及原因。
- **M153-R6**：同一次运行内按 `source_manifest_sha256` 建立页面/表格/字段候选索引并
  复用；不写磁盘、不跨运行复用。相同产品同一字段集合的候选计算只能执行一次。
- **M153-R7**：上下文构建必须去重，保留每个目标字段的 Top 候选、必要相邻页和表格
  行；无关长费率表不能占用请求主体。离线基准要报告旧/新字符量、重复页数、候选
  覆盖和构建耗时，不能以缩短上下文冒充召回提升。
- **M153-R8**：并发只提供有界执行计划，默认最多 2 路，并按稳定 batch index 合并；
  本 Mission 不调用 provider，只用可控 fixture 验证乱序完成不会改变结果。

## Non-goals

- 不做持久化 PDF 页面缓存或字段候选缓存。
- 不修改四份业务 XLSX，不把截图 OCR 文本直接当作已经人工批准的 Golden。
- 不运行真实模型，不宣称真实抽取率、准确率或速度已经提升。
- 不自动覆盖 M152 已有值，不修改 Schema，不处理动态 Schema。
- 不写生产 DB/Release/Active，不部署，不提交或推送 GitHub。

## Stop Conditions

- 业务表、M152 基线或 Schema identity 漂移；
- 需要外部 OCR、外部模型、生产数据或持久化缓存才能继续；
- 表格结构无法从当前 PDF 本地解析且必须引入新生产依赖；
- 需要修改批准路径之外的发布、数据库或 WeKnora serving 代码。
