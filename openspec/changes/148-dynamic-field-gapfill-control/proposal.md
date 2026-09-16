# 148 · 字段级动态补抽与复核

## Goal

在现有 V5 预览与 Ingest 抽取链上增加一个人工可控的半动态入口。用户在前端选择字段
后发起“补抽”或“复核”，前端只传产品版本、当前预览 identity、动作和字段集合；材料
定位、上下文扩展、模型调用、Evidence 校验、候选合并与差异计算全部由后端完成。

## Owner And Boundary

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- 一个本地 change set，不创建 PR，不提交或推送 GitHub。
- 本轮只做代码与 bounded tests；不重跑三款产品，不调用真实 Provider，不外发 PDF。
- 不写生产数据库，不生成 Release，不修改 Active，不改变 830 B0/G1 状态。

## Requirements

- `M148-R1`：前端只提交 `product_version_id`、`preview_sha256`、动作和有界字段集合；
  不上传材料正文，不在浏览器实现候选定位或抽取。
- `M148-R2`：`gapfill` 只允许当前为 `unknown` 的字段；当前已有值或明示无的字段只能
  走用户显式 `review`，两类动作不得混用。
- `M148-R3`：后端按 `matched_snippets -> adjacent_pages -> all_material` 顺序扩大
  上下文；每层先扫描该产品版本全部材料页面，再施加上下文预算。得到已核验结果后提前停止，
  无候选时不得把“未找到”改成“否”。
- `M148-R4`：一次操作最多 8 个字段、最多 3 个模型阶段。每阶段记录范围、扫描页数、
  入选页数和上下文 digest；重试次数不能无上限增长。
- `M148-R5`：补抽产生的新值即使 Evidence 尚待核验也保留为 Candidate 并标记待复核；
  不得因 Evidence 状态直接丢值。复核发现冲突时保留原值，同时返回冲突候选与 Evidence。
- `M148-R6`：响应必须包含逐字段 before/proposed/after、状态、使用范围、阶段记录和完整
  Candidate Preview；`serving_effect=NONE`、`review_publish_admission=false`。
- `M148-R7`：请求必须绑定当前 `preview_sha256`、产品版本、来源版本和 Schema；任一
  identity 漂移必须在模型执行前拒绝。
- `M148-R8`：前端针对 `unknown` 显示“补抽”，针对已有结果显示“复核”；收到响应后只
  更新本地 Candidate 预览并展示本次状态，不显示为已发布知识。

## Non-goals

- 不做自动循环 N 次直到强行有值；材料不足时仍允许 `unknown`。
- 不把前端变成抽取执行器，不从浏览器上传整份 PDF 文本。
- 不自动复核全部已有字段，不直接覆盖冲突值。
- 不实现无 Schema 领域、自生成 Schema、生产 Job Store、审核发布或 Active 写入。

## Stop Conditions

- 必须绕过当前产品/来源/Schema identity 才能执行；
- 必须由浏览器传递原材料正文，或必须直接修改 Active 才能展示结果；
- bounded tests 需要真实 Provider、真实 PDF 外发或生产数据库；
- 实现需要跨入无 Schema 领域设计或生产任务编排。
