# 143 · 三字段全材料语义抽取

## Goal

在现有 V5 抽取链上补齐 `宽限期`、`险种转换`、`费率可调` 的字段级语义判定。
规则扫描只负责召回候选和提供上下文；最终由 LLM 在全材料范围内判断
`present / absent_explicitly / unknown`，并绑定可回验的原文 Evidence。

## Owner

- 唯一写 Owner：当前总控 Codex
- 执行模型：`gpt-5.6-sol high`
- Provider：百炼 `qwen-plus`，最多 15 次

## Scope

- 复用当前 V5 catalog、三态和 Evidence 合同，不修改工作簿、字段顺序或分类；
- 五款产品：596、5003、1826、594、1818，共 15 份 PDF，扫描每份 PDF 的全部页面；
- 仅优化 `premium_grace_period`、`product_conversion_rules`、`premium_adjustment_rules`；
- 对候选缺失字段执行全材料字段级补抽，保留原先较强结果，不覆盖 M142；
- 输出 `provider-run-m143-five-products.json`，服务只指向本地测试结果。

## Requirements

- `M143-R1`：三个目标字段必须在其适用 Schema 中进入 LLM 抽取；候选扫描无命中不能直接跳过。
- `M143-R2`：目标字段的补抽上下文必须覆盖该产品全部 PDF 页面，或在超过预算时保留每页的
  有序摘要/片段并记录扫描覆盖，不得依赖文件名或同名标题。
- `M143-R3`：`宽限期`只接受正式条款中的保费宽限语义；重新投保窗口、等待期、保险期间届满
  不得替代。`险种转换`只接受明确转换/转保关系。`费率可调`只接受产品层面的调费/重新定价
  规则；家庭费率因子、职业加费和告知义务导致的加费不算。
- `M143-R4`：明确原文支持时抽取值并绑定逐字 Evidence；材料没有明确正/负命题时保留
  `unknown`，不得因规则未命中填“否”。
- `M143-R5`：抽取率按 `present 且 material_supported / material_supported` 计算；
  `ambiguous`、`unsupported`、`not_applicable` 单独列出。
- `M143-R6`：五款产品独立运行，最多 15 次 qwen-plus；产物不覆盖 M142/M141，不写生产 DB，
  不进入 Candidate/Release/Active，不提交或推送 GitHub。

## Non-goals

- 不修改 Schema v5 工作簿或新增无 Schema 字段；
- 不放宽 Evidence 来源身份、逐字引用和页码校验；
- 不把没有明确依据的空值强行改成“是”或“否”；
- 不运行生产部署、迁移、发布或 GitHub 操作。

## Stop Conditions

- 产品身份、PDF SHA/页数或 catalog SHA 漂移；
- Provider 达到 15 次上限，或结果无法通过本地合同；
- 需要修改其它字段、扩大到其它产品或写入外部系统；
- 任何产品的材料支持抽取率相对本轮基线明显回退。
