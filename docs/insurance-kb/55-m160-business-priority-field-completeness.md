# M160 业务重点字段完整性优化

## 结论

M160 已完成真实百炼 `qwen-plus` 复测，结果文件为 `provider-run-m160-six-products-business-priority.json`，run=`v5-trial-d145de09d8cbefea`，共 30 次有界调用、6 款产品；8091/5174 已切到该结果。一次 1828-1 长字段在重试后仍返回不完整，按 fail-closed 保留为未完成，不作为成功抽取。

本地完整 V5 测试套件 82 项通过（仅有 2 个既有环境/依赖 warning），严格 mypy、Ruff 和 compileall 也通过。

## 做了什么

- 新增等待期复合字段门禁，要求分别保留等待期时长、起算点、适用责任、意外例外、等待期内后果和材料明确的特殊例外；每个组成部分必须有可回验 Evidence。
- M160 provider 入口复用现有全量页扫描、字段分片、并发和 32 次全局预算，但使用更明确的字段提示：等待期按标签输出，缴费期限/频率分离并保留正式选项，权益和责任限定当前产品作用域。
- M158 默认入口未改变；M160 产物契约独立为 `insurance-v5-m160-*`。

## 当前效果判断

本轮实际效果：596 等待期从 45 字扩展到 255 字，补齐时长、起算点、适用责任、意外例外、等待期内后果和 60 日/指定产品特殊例外；1816 保留特定疾病与重大疾病两段等待期后果；1828 保留 90 日、复效起算、轻/中/重症适用、意外例外和退费终止后果。5003、1830、1814 仍为 `unknown`，因为未形成可验证的等待期事实，避免把“等待期一般都有”误填为事实。机器可读反馈为 `6 RESOLVED / 3 PARTIAL / 3 UNRESOLVED / 18 NOT_SCORABLE`；材料支持总体仍为 `133/143=93.01%`，因此这是重点字段的定向完整性提升，不是整体召回率已被证明提升。

## 输入限制

M159 共 390 页；本地恢复了 596 的 60 页服务手册，当前仍缺历史记录中的 2 页“安医保一页纸”，所以预检记录为 390 scanned / 388 readable / 2 unreadable。缺页不被伪造为可读材料。

本次运行是本地只读预览，`serving_effect: NONE`，没有 Candidate、Draft、Release、Active 或正式 serving 变更。详细 Requirement、Delivery 和回执见 [`openspec/changes/160-business-priority-field-completeness/validation-report.md`](../../openspec/changes/160-business-priority-field-completeness/validation-report.md)。
