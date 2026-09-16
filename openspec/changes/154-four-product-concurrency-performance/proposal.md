# 154 · 四路产品级并发与运行耗时

## Goal

把八款产品运行中完全串行的 Provider 阶段改为最多四款产品并行，同时保持每款
产品内部批次原顺序串行。并发运行必须共享一个不会超额的调用预算，输出仍按输入
产品顺序稳定合并；遇到 Provider 429 后降低后续调用并发，并留下可复算的阶段耗时。

## Owner And Boundary

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- 一个本地 change set；不创建 PR，不提交或推送 GitHub。
- 允许修改当前 worktree 的 V5 本地运行器、测试、OpenSpec、说明和 HANDOFF。
- 不外发材料，不调用外部模型，不写生产数据库，不形成 CandidateRelease、Release
  或 Active，不更新 8091/5174 的业务结果。

## Requirements

- **M154-R1**：产品并发由闭合的 `CapacityProfile` 控制，合法值为 1 至 4，默认最多
  4 路；该值是运行容量，不是产品数、文件数或批次数硬上限。
- **M154-R2**：不同产品可并发执行；同一产品任一时刻最多一个批次在调用 Provider，
  且批次必须按原 batch index 串行完成。
- **M154-R3**：所有产品共享线程安全的全局调用预算。每次 Provider 尝试在发起前
  原子占用一个序号，成功、429 和其它失败均计入；并发竞争不能超额或复用序号。
- **M154-R4**：识别 exact HTTP 429 后，并发门从 4 路降到 2 路、再次出现则降到
  1 路。降级只约束后续调用；已完成产品或批次不得重跑，同一失败批次最多沿用既有
  重试上限，不产生无界重试风暴。
- **M154-R5**：无论线程完成顺序如何，产品输出按基线产品 ordinal 合并，产品内结果
  按 batch index 合并。相同 fixture 在串行和四路配置下，业务 Preview 和字段审核
  结果必须一致；仅调度与耗时回执可不同。
- **M154-R6**：运行时间从材料解析前开始，分别记录 `materials_parse`、`planning`、
  `provider`、`merge_write` 与 `total`；同时记录每产品/批次 Provider 等待时间、峰值
  并发和 429 降级事件。耗时只作观测，不能冒充业务质量证明。
- **M154-R7**：Schema identity、Prompt 构建、候选/Evidence 校验、M153 回归比较与
  merge 决策保持不变。并发层只调度既有产品工作，不修改抽取语义。
- **M154-R8**：本 Mission 只用延迟、失败和 429 可控的 fake Provider 验证并发、
  串行性、预算、稳定合并和耗时合同；真实 Provider 效果与耗时均为 `NOT RUN`。

## Non-goals

- 不做持久化 PDF 页面或候选缓存，不改变 PDF 全页候选召回。
- 不改 Schema、Prompt、字段取值、Evidence、审核阈值或业务回归规则。
- 不运行百炼，不宣称真实八款产品已缩短到某一时长。
- 不写生产 DB/Release/Active，不部署，不提交或推送 GitHub。

## Stop Conditions

- 并发接入要求共享非线程安全 Provider client 且无法做到每产品隔离；
- 全局预算无法在 Provider 尝试前确定性占用，或测试出现预算超额；
- 串行与四路 fixture 的业务输出出现漂移；
- 需要改 Prompt、Evidence、Schema、业务审核或扩大到生产部署才能继续。
