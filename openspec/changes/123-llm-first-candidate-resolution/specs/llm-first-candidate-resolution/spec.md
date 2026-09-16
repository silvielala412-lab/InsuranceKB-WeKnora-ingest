# LLM-first candidate resolution

## ADDED Requirements

### Requirement: LFC1 deterministic candidates must pass semantic resolution

规则、模板、外部映射或其它确定性路径生成的业务字段候选 SHALL 在进入最终合并前
经过一次 LLM 语义裁决。候选不得因为 fastpath 命中而直接成为最终字段值。

#### Scenario: fastpath candidate is present

- **WHEN** 模板或规则生成一个带 Evidence 的候选值
- **THEN** 管道调用语义裁决器，并将模型返回的值作为独立候选进入校验链

#### Scenario: no deterministic candidate

- **WHEN** 字段没有规则/模板候选
- **THEN** 保持现有通用抽取流程，不额外创建空裁决调用

### Requirement: LFC2 semantic resolution sees competing evidence

语义裁决请求 SHALL 包含字段定义、候选值、来源文档、页码、引文以及候选页上下文。
模型 SHALL 可以选择候选、纠正候选或返回 unknown，但 present/absent 值必须携带
可回验 Evidence。

#### Scenario: two locations contain different values

- **WHEN** 同一字段存在多个候选位置
- **THEN** 裁决器把候选全部交给 LLM，保留被选择和被放弃候选的审计信息

### Requirement: LFC3 unresolved candidates are explicit

候选存在但语义裁决调用失败、输出不可解析或返回无证据值时 SHALL 输出
`candidate_unresolved` 记录，不得静默覆盖为普通 unknown 或直接丢弃候选。

#### Scenario: resolver returns unverifiable value

- **WHEN** LLM 返回的值无法通过 Evidence 回验
- **THEN** 不产生可发布 present 值，并保留候选值与失败原因

### Requirement: LFC4 existing safety gates remain authoritative

语义裁决结果 SHALL 继续经过现有 quote、占位值、字段兼容性、类型和三态校验；本变更
不得放宽 Source、Candidate、Review、Release 或 Active 权限边界。

#### Scenario: evidence verification fails

- **WHEN** 语义裁决的引文不在对应页原文
- **THEN** 结果不能进入最终 pred，且既有失败原因可审计

### Requirement: LFC5 local-only validation

本变更 SHALL 仅在当前自有 worktree 进行软件和离线桩测试验证；真实 Provider、原始
PDF 外发、数据库写入和生产部署均为 NOT RUN。
