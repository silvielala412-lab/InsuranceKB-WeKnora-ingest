# 142 · 材料支持字段召回与语义补抽

## Goal

在不降低现有 Evidence、三态和值约束的前提下，修复 V5 抽取中材料已有但未进入
补抽的字段，并把“材料支持”与“材料缺失”分开记账。重点覆盖适用人群、保什么、
费率可调和险种转换等容易以语义表达出现的字段。

## Owner

- 唯一写 Owner：当前总控 Codex
- 执行模型：`gpt-5.6-sol high`
- Provider：百炼 `qwen-plus`，最多 12 次

## Scope

- 产品：596、5003、1826；固定 9 份 PDF、全部页面扫描；
- 仅在现有 V5 Schema 路径上增加语义候选、混合字段补抽和材料支持诊断；
- 输出独立的 `provider-run-m142-three-products.json`，保留 M141 及更早结果；
- 计算 `present ∧ material_supported / material_supported`，另列 ambiguous/unsupported；
- 更新本地 8091/5174 预览服务，不写生产 DB，不进入 Candidate/Release/Active。

## Requirements

- `M142-R1`：`原文抽取 + LLM生成` 的混合字段必须进入自动抽取和 targeted repair；只有
  纯外部映射和纯 `LLM生成` 字段不进入 PDF 自动抽取分母。
- `M142-R2`：候选扫描覆盖全部 PDF 页面；适用人群、费率调整、险种转换支持语义同义表达，
  不能只依赖字段同名标题或文件名。
- `M142-R3`：LLM 对候选负责语义选择和有限归纳；费率可调、险种转换等单选字段只有在
  原文明确支持时才给出值，证据不足保持 `unknown`，不以规则硬填。
- `M142-R4`：每个字段记录 `supported | ambiguous | unsupported` 材料判断及依据；
  `material_supported_extraction_rate` 只以 supported 字段为分母，不把外部映射或缺失材料
  误算为模型漏抽。
- `M142-R5`：Evidence 无法回验时保留已有值并标记待核验，继续遵守逐字引文、页码和来源
  身份校验；不得通过放宽审核删除或伪造证据。
- `M142-R6`：三款产品独立试跑，最多 12 次 qwen-plus；旧 artifact 不覆盖，运行无生产
  数据、Release/Active 或 GitHub 影响。

## Non-goals

- 不修改 v5 工作簿、11 类 Schema 拓扑、字段顺序或分类；
- 不实现无 Schema 发现、自动发布、生产部署或 GitHub 提交；
- 不把没有明确材料依据的字段强行补全为“是/否”。

## Stop Conditions

- 产品身份、PDF hash/页数、catalog hash 漂移；
- Provider 达到 12 次上限或结果无法通过本地合同；
- 任一产品材料支持字段抽取率相对基线明显回退；
- 需要新增外部数据源、数据库写入或生产权限。
