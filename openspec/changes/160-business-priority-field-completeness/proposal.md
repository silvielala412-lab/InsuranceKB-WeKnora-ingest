# Mission 160: Business Priority Field Completeness

## Goal

在 M159 六款产品、20 份 PDF 的本地复测上，优先修复业务强调字段的“抽到了但精简过度”问题。等待期必须保留时长之外的起算点、适用责任、意外例外、等待期内后果和特殊无等待期条件；缴费期限/频率、保单权益、保险责任、责任免除、疾病定义与认定标准必须保留材料支持的原子条件与适用范围，并通过逐条 Evidence 门禁。

唯一 Owner：当前 Codex 执行 lane。结果仅用于本地评测和预览，不形成 Candidate、Draft、Release 或 WeKnora Active 写入。

## Scope

- 冻结 M159 结果文件、M159 运行身份、当前五类材料根目录、业务反馈工作簿和 Schema catalog 身份。
- 改造等待期结构化提示、解析/审计与证据保留；增强重点字段的正式选项集、边界和当前产品作用域约束。
- 复跑相同六款产品和反馈集，最多 32 次官方 `qwen-plus` 调用，保留独立 M160 结果、audit、feedback assessment 与结论文档。
- 记录全可读页扫描、候选页、分片页、未读页和每个原子事实的 Evidence；维持 `REVIEW_REQUIRED`、`serving_effect=NONE`。

## Non-goals

- 不修改 OCR、WeKnora、候选匹配算法、Embedding、DeepSeek、生产数据库、权限、Candidate/Release/Active、GitHub 或部署。
- 不把规则生成的答案写进业务字段；规则只负责提示、结构校验和证据门禁。
- 不将 fixture、provider-zero、代码通过或本地服务状态写成真实业务效果。

## Requirements

### M160-R1 Waiting-period composite completeness

等待期候选值必须能够表达并逐项支持：`duration`、`start`、`applicability`、`accident_exception`、`within_wait_consequence`、`special_exceptions`。缺失或无 Evidence 的组成部分不得把候选升级为完整替换；不能只保留一个日期/天数。

### M160-R2 Full material coverage

每个产品仍须扫描全部可读页；字段上下文可以分片，但必须保留候选定位、选入分片、页数、分片数和未读页回执。不得以“候选命中”冒充全量召回。

### M160-R3 Priority-field atomicity

缴费期限和频率分别保留正式合同选项集合并排除利益演示示例；保单权益只收当前产品可证实权益并允许 `present/absent_explicitly/unknown`；责任、免责、疾病定义逐项保留条件、限制、例外、适用对象和直接 Evidence。

### M160-R4 Evidence-preserving replacement

只接受 `VERIFIED` 或 `NORMALIZED_MATCH` Evidence；冗余未解析引文可丢弃，唯一支撑缺失则 fail closed。基线值、提案值、最终值、动作、原因和审计结果必须同时留档。

### M160-R5 Bounded rerun and no serving effect

基线必须精确为 M159 结果及其 SHA；调用模型固定为 `qwen-plus`，总调用不超过 32，单产品不超过 12；material-supported extraction rate 不得低于 M159 的 93.01%，所有产品保持 `REVIEW_REQUIRED`，不产生 serving effect。

### M160-R6 Reviewable feedback assessment

反馈表 30 条保持同一输入身份；机器可读的必需/禁止词逐条评估，无法从备注确定标准的条目标记 `NOT_SCORABLE`，不得用它们冒充业务通过。

## STOP conditions

身份漂移、调用超过 32、Evidence 丢失、输出拓扑/契约错误、支持率低于基线、生产/数据库/发布写入或无法区分本地与真实 provider 时立即停止并保留部分回执。
