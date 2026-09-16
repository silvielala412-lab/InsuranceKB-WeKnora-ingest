# 152 · 八产品动态补抽与问题字段复核

## Goal

以 `provider-run-m150-eight-types.json` 的八款 Preview 为不可变基线，使用 Mission 151
的字段全材料候选召回，只补抽 `unknown`，并对业务表标记为抽取不全、未识别、概括
不全、概括错误或抽取错误的已有字段生成复核建议。结果写入独立本地 artifact，更新
8091/5174 预览，不覆盖 M150。

## Owner And Boundary

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- 一个本地 change set；预计一个执行周期；不创建 PR，不提交或推送 GitHub。
- 允许外发当前八款产品的冻结材料，最多调用 18 次百炼 `qwen-plus`。
- 允许读取 `E:\wiki badcase ly`，写当前 worktree 的独立结果并更新本地 8091/5174。
- 不写生产数据库，不生成正式 CandidateRelease，不发布或激活 Active Release。

## Requirements

- **M152-R1**：冻结 M150 八产品 artifact、Schema Catalog、产品材料 SHA/page count、
  业务问题表和 provider identity；输入漂移必须停止，不能静默换样本。
- **M152-R2**：八款产品均进入任务计划。有业务问题表的 596/5003/1830/1814 优先
  覆盖问题字段；1826/1816/1828/L2332 只选择 `unknown` 且 Retriever 有候选的字段。
- **M152-R3**：字段按每批最多 8 个拆分，使用 M151 Retriever 构建有页码与字符边界的
  候选上下文。总 provider 调用不得超过 18；预算不足时必须输出明确未运行项。
- **M152-R4**：`gapfill` 只能把基线 `unknown` 更新为有 Evidence 的值。已有字段的
  `review` 只生成 before/proposed/diff；同值可补证，异值不得自动覆盖基线。
- **M152-R5**：每个字段记录任务类型、候选页、provider attempt、before/proposed/after、
  Evidence 状态和结果原因；provider 错误不得清空基线值。
- **M152-R6**：独立 artifact 名固定为
  `provider-run-m152-eight-products-gapfill.json`，必须保留完整 M150 基线 identity，
  并通过闭合 Pydantic/JSON 合同或等价确定性验证。
- **M152-R7**：报告候选命中率、unknown 补抽成功率、问题字段复核覆盖率、Evidence
  通过率和冲突数。候选命中不能冒充抽取成功，模型建议不能冒充人工准确率。
- **M152-R8**：8091/5174 只能展示 M152 本地候选结果；`serving_effect=NONE`、
  `review_publish_admission=false`，不得写生产 DB/Release/Active。

## Non-goals

- 不重跑八款产品的全部 Schema 字段。
- 不自动覆盖业务标记为错误或不完整的已有字段。
- 不修改 Schema、不处理无 Schema 发现，也不提交或推送 GitHub。
- 不把本地预览描述为正式发布或人工验收完成。

## Stop Conditions

- 任一输入材料、M150 基线或 Schema identity 漂移；
- 需要超过 18 次 provider 调用；
- provider 凭据不可用、持续返回不完整合同，或必须降低 Evidence 校验才能继续；
- 需要生产数据库、Release/Active、GitHub 或范围外服务写入。
