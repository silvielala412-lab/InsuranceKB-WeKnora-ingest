# Change 158: 业务七字段质量闭环

## Goal

在 M157 六款冻结结果上，闭合业务反馈集中指出的保险责任、责任免除、缴费期限、
缴费方式、保单权益、等待期、疾病定义与认定标准问题。验收同时检查字段是否有值、
原子事实是否完整、适用对象是否正确以及 Evidence 是否可回验，不能用材料支持字段
有值率替代业务准确性。

唯一 Owner 是当前总控 Codex，执行模型为 `gpt-5.6-sol high`。实现和真实运行都在
当前本地 worktree 内完成，不提交或推送 GitHub。

## Frozen Inputs

- HEAD（仅记录起点，不表示 clean tree）：`d2ce44cb2107575f7624b3735c653078ae2a98b6`。
- M157 result SHA-256：
  `5f136ece85ca6626ae691f0290b625c0f86caf7e17d127b32164a23cc4934ec4`。
- M157 audit SHA-256：
  `caed22c9961d55272cb4152a1d88f72df4356d848613becc945c4c8e8f7f7695`。
- V5 Catalog 文件 SHA-256：
  `6ca2c401081dad1cab575a8f3db3db91ff952e6dfae1182461e3bb279cb68d56`。
- 业务反馈工作簿 SHA-256：
  `3f174f18aba72821db9d5d545f6b79b05bcfafb020815cc718bdb95bfd8359b3`。
- 产品与材料：596、5003、1830、1814、1816、1828 六款，沿用 M157 的 20 份
  PDF 与文件级 SHA-256 manifest。

## Requirements

### M158-R1 长字段分片与确定性合并

保险责任、责任免除和疾病定义先扫描当前产品全部可解析页面，再在字段内部按章节和
页窗口分片。每片限制输出规模，模型返回原子项；后端按规范化原子身份稳定去重、保序
合并，并保留每个原子项自己的 Evidence。不得依靠提高 32768 token 上限解决截断。

### M158-R2 Evidence 有效子集准入

合并前逐条重定位 Evidence。未定位且不支撑任何唯一原子项的冗余 Evidence 可以从
候选中删除；删除后必须重新证明每个原子项仍至少有一条 VERIFIED 或
NORMALIZED_MATCH Evidence。不能再因一条冗余未定位 Evidence 拒绝整个完整字段，
也不能放宽到未支持原子项通过。

### M158-R3 短字段联合语义校验

缴费期限与缴费方式联合抽取并校验完整选项集合、正式约定与示例的区别；等待期检查
期限、意外例外和等待期内后果；保单权益检查当前产品、主险和附加险适用范围。只从
当前产品冻结材料得出结果，不把业务答案或产品 ID 写入生产 Prompt/规则。

### M158-R4 业务反馈独立验收

业务工作簿只在抽取完成后用于独立评分。对其中七字段 30 条记录输出逐条
`RESOLVED | PARTIAL | UNRESOLVED | NOT_SCORABLE`，记录 M157 before、M158 after、
对应 Evidence 和判断原因。文本明确答案可做确定性断言；只有截图占位的答案不得由
代码臆造，保留人工复核状态。

### M158-R5 回归、Provider 与本地预览

先记录旧实现可复现 RED，再运行焦点与全部 V5 回归。真实运行限同六款 20 份 PDF、
最多 32 次百炼 `qwen-plus`，写独立 M158 result/audit/feedback assessment。材料支持
口径不得低于 M157 的 `133/143=93.01%`，既有正确字段不得回退。结果合同有效后才
允许更新 8091/5174，并记录 exact run live probe。5174 的前端结果解析合同必须与该
32 次全局预算一致；单产品回执数只能受同一全局预算约束，不得继续使用历史四次上限
拒绝合法的字段微批次结果。第 33 次调用仍须失败关闭。

## Write Domains

- `openspec/changes/158-business-seven-field-quality-closure/**`
- `harness/src/insurance_harness/v5_preview/m158_*.py`
- 为接线所需的最小 `harness/src/insurance_harness/v5_preview/` 既有模块改动
- `harness/tests/test_v5_m158_*.py`
- `frontend/src/views/knowledge/schema-wiki/v5-preview/v5ProviderTrialContract.ts`
- `frontend/src/views/knowledge/schema-wiki/v5-preview/v5ProviderTrialContract.test.ts`
- M158 独立 result/audit/assessment 和 `docs/insurance-kb/` 运行记录
- `HANDOFF.md`、`docs/insurance-kb/29-goal-cards-830.md`、OpenSpec 注册表

## Non-goals

- 不修改 V5 Schema，不把业务标准答案写入模型 Prompt 或产品特例规则。
- 不建立持久化 PDF 候选缓存，不调用 OCR、Embedding 或 DeepSeek。
- 不写生产数据库，不形成 CandidateRelease、Release 或 Active。
- 不提交或推送 GitHub，不覆盖 M157 及更早结果。

## STOP

冻结输入 identity 漂移、连续 Provider 错误导致 32 次预算无法覆盖计划、材料支持口径
回退、已确认正确字段被覆盖、字段原子项失去可回验证据或结果合同无效时立即停止，
不得更新本地服务指针或宣称业务问题已经闭合。
