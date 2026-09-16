# 123 · LLM-first candidate resolution

## Goal

让规则、模板和外部映射只负责提供可审计候选，所有业务字段候选统一经过 LLM
语义裁决，再进入现有确定性 Evidence/类型校验链。解决 fastpath 命中后直接终止
模型抽取、多个位置无法比较以及“有候选却静默 unknown”的问题。

## Scope

- 新增候选语义裁决器和版本化 prompt；
- 将 fastpath 候选接入裁决器；
- 保留候选来源、页码、引文和裁决 attempt；
- 增加 `candidate_unresolved` 的可审计状态；
- 保留现有 Source/Evidence/Candidate/Release 权限边界。

## Non-goals

- 不调用真实 Provider，不外发原始 PDF；
- 不修改 WeKnora Go 核心、数据库、前端或生产部署；
- 不实现未知领域 Schema Discovery；
- 不改变现有 Evidence 回验和 Active Release authority。

## Design

```text
规则/模板/外部映射
  -> 候选值 + 全部候选证据上下文
  -> LLM 语义裁决（选择/纠正/unknown）
  -> Evidence 与类型校验
  -> 现有 vote/gapfill/finalize
```

语义裁决只允许引用候选上下文中的原文；模型不能生成无 Evidence 的值。候选存在
但裁决失败时输出 `candidate_unresolved`，由后续补漏或人工流程处理。
