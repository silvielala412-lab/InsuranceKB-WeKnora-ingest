# 141 · v5 取值约束与输出归一化

## Goal

把 v5 工作簿中字段级“取值”说明编译成抽取时可理解、回包后可复用的约束，
减少单选/多选字段的自由文本漂移，同时保留有材料依据但暂时无法标准化的值。

## Owner

- 唯一写 Owner：当前总控 Codex
- 执行模型：`gpt-5.6-sol high`
- Provider：百炼 `qwen-plus`，最多 12 次

## Scope

- 复用当前 v5 catalog 与冻结工作簿，不改变 11 类 Schema 的字段数量、顺序或 hash；
- 解析 `value_guidance` 中的单选、多选、可为空、显式“其他”和“等”语义；
- 在 LLM 提示中发送结构化取值约束；
- 对 LLM 返回值做保守归一化，无法判定时保留原值，不因归一化失败降低召回；
- 使用产品 `596`、`5003`、`1826` 的既有 9 份 PDF 做独立 provider 试跑；
- 结果写入 `provider-run-m141-three-products.json`，不覆盖 M140。

## Requirements

- `M141-R1`：v5 catalog 的 `value_guidance` 必须能确定字段约束类型、允许值、是否多选和是否可为空；没有明确枚举的字段保持自由文本。
- `M141-R2`：schema prompt 必须携带结构化取值约束；模型不得仅因约束列表存在而虚构材料中的值。
- `M141-R3`：可唯一对应的模型值归一为工作簿标准值；多选去重并保持字段定义顺序；无法唯一对应的有证据值原样保留。
- `M141-R4`：已有 Evidence 和三态合同不变；归一化不得绕过逐字 Evidence 校验，也不得把 `unknown` 伪装成 `absent_explicitly`。
- `M141-R5`：三款产品 provider 结果独立落盘；不得覆盖 M140/M139，不写生产 DB，不进入 Release/Active，不提交或推送 GitHub。
- `M141-R6`：软件测试不得出现 v5 catalog 拓扑回退；三款产品的 `present` 数量不得低于 M140 基线。

## Non-goals

- 不修改工作簿、不改变 Schema 字段定义和产品分类；
- 不把所有自由文本强行截断成枚举，不新增无 Schema 发现流程；
- 不放宽 Evidence 的来源身份、逐字引用或安全校验；
- 不写生产数据库、不发布 Candidate/Release/Active、不提交或推送 GitHub。

## Stop Conditions

- 工作簿 SHA、catalog identity、产品身份、PDF hash 或页数漂移；
- Provider 达到 12 次上限；
- 任何产品 `present` 数量低于 M140 基线；
- 需要扩大到其它产品、数据库、生产环境或新增外部授权。
