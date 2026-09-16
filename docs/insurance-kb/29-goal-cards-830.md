# 29 · 830 Goal Cards（统一知识库与真实验收版）

> 修订日期：2026-08-31
> 当前授权：`B0_ONLY + MISSION_136_LOCAL_WORKTREE + MISSION_139_LOCAL_PROVIDER_RUN + MISSION_148_LOCAL_DYNAMIC_GAPFILL + MISSION_149_LOCAL_SIX_CLASS_PREVIEW + MISSION_150_LOCAL_SERIOUS_ILLNESS_PREVIEW + MISSION_151_LOCAL_FIELD_RETRIEVAL + MISSION_152_LOCAL_EIGHT_PRODUCT_GAPFILL + MISSION_153_LOCAL_QUALITY_PERFORMANCE + MISSION_154_LOCAL_PRODUCT_CONCURRENCY + MISSION_155_LOCAL_PROVIDER_RUN + MISSION_156_LOCAL_FIELD_QUALITY`
> 当前产品状态：`830_PRODUCT_GOAL=B0_EVIDENCE_FROZEN_PENDING_CONTROLLER_REVIEW`
> Schema Catalog：`11_PRODUCT_PACKS_SOURCE_VERIFIED_NOT_REGISTERED`
> 执行 WIP 上限：`WIP_LIMIT=1`

本文件是 830 唯一 Goal 队列和逐卡验收权威。用户当前只授权 B0 的证据冻结、资产
裁决和必要 authority/Handoff 指针；它不启动产品代码、Provider、运行环境、迁移或
真实写入。B0 Evidence Pack 已冻结并等待总控复核；只有总控裁决 B0 为 PASS 后，
下一张卡才可另行获授权进入 WIP。G1 及后续 Goal 当前均为 `LOCKED`。

### Mission 136 本地例外

用户已明确批准 Mission 136，仅允许在自有 `InsuranceKB-WeKnora-ingest` worktree
内进行抽取代码、测试和维护文档的二次开发。该例外不改变 830 的生产治理：不推送
PA-ALG 原项目、不提交远端、不调用真实 Provider、不外发原始 PDF、不启动生产服务，
也不产生 Candidate、Release、Active 或数据库写入。Mission 136 的 OpenSpec 为
`123-llm-first-candidate-resolution`，WIP 仅限本地软件验证。

### Mission 139 九产品本地评测例外

用户已明确批准 Mission 139：允许在同一自有 worktree 扩展 V5 预览运行器和前端
合同，外发冻结的 9 款产品 27 份 PDF，最多调用 18 次百炼 `qwen-plus`，结果只写入
`provider-run-m139-nine-products.json` 并更新本地 8091/5174 预览。M137/M138 必须
保留；不得提交或推送 GitHub，不得写生产数据库，不得形成 Candidate、Release 或
Active。适用 OpenSpec 为 `124-nine-product-v5-extraction-evaluation`。

Mission 139 已完成本地评测：九款 27 份 PDF 共 399 页，最终 artifact 记录 9 次调用，
8091/5174 已按 exact run 验证。自动字段有值 237/458，材料支持条件下 237/324，
候选页条件下 237/285。结果仅为本地 `REVIEW_REQUIRED` 预览，业务发布状态仍为
`NOT RUN`；详细记录见 `docs/insurance-kb/32-m139-nine-product-extraction.md`。

### Mission 148 字段级动态补抽例外

用户已明确批准 Mission 148：在自有 worktree 内实现由前端人工触发、后端执行的
字段级动态补抽与复核。补抽只面向 `unknown`，已抽取字段由用户显式发起“复核”；
后端按候选片段、相邻页、产品版本全材料逐层扩大上下文，提前得到可信结果即停止。
结果必须保留 Candidate、Evidence、字段差异和执行状态，不写 Active。本轮不重跑
三款产品、不调用真实 Provider、不写生产数据库、不提交或推送 GitHub。适用 OpenSpec
为 `148-dynamic-field-gapfill-control`，仅允许本地软件验证，不改变 830 B0/G1 状态。

### Mission 149 六险种本地预览例外

用户已明确批准 Mission 149：保留 Mission 146 的医疗险、终身寿险、两全保险三款
结果，仅补跑年金险 1830、意外险 1814、失能收入损失保险 1816，共外发 9 份冻结
PDF，最多调用 6 次百炼 `qwen-plus`。新增结果与六险种组合预览使用独立本地
artifact，历史结果不得覆盖；只允许更新本地 8091/5174，不写生产数据库，不形成
Candidate、Release 或 Active，不提交或推送 GitHub。适用 OpenSpec 为
`149-six-insurance-class-local-preview`，不改变 830 B0/G1 状态。

### Mission 150 两款重疾险本地预览例外

用户已明确批准 Mission 150：在 M149 六款本地结果基础上，新增重疾险 1828 和
L2332 两款，共 6 份 PDF，最多调用 6 次百炼 `qwen-plus`。新结果写入独立 artifact，
并生成保留 M149 原 payload 的八款合并预览；不覆盖历史结果、不写生产数据库、不创建
Candidate/Release/Active，也不提交或推送 GitHub。适用 OpenSpec 为
`150-serious-illness-two-product-local-preview`。

### Mission 151 字段全材料语义召回例外

用户已明确批准 Mission 151：在当前自有 worktree 内升级字段候选召回和动态补抽
上下文。允许读取 `E:\wiki badcase ly` 做离线验收；不允许外发材料、调用外部模型、
写生产数据库、形成 CandidateRelease/Release/Active，也不提交或推送 GitHub。
适用 OpenSpec 为 `151-field-semantic-retrieval-gapfill`；本轮只允许软件和离线候选
质量验证，不能据此宣称真实抽取率或准确率提高。

### Mission 152 八产品补抽与复核例外

用户已明确批准 Mission 152：以当前八款本地 Preview 为基线，允许外发其冻结材料、
最多调用 18 次百炼 `qwen-plus`，执行 unknown 补抽和业务问题字段复核。结果写入独立
本地 artifact 并更新 8091/5174；不得覆盖历史 artifact，不写生产数据库，不形成正式
CandidateRelease/Release/Active，也不提交或推送 GitHub。适用 OpenSpec 为
`152-eight-product-dynamic-gapfill-review`。

执行结果：八款 unknown 补抽已写入独立 M152 artifact，Mission 调用预算 18/18；已有值
复核审计侧车未成功落盘，故该部分记为 `BLOCKED`，不得描述为已修复。详细数据见
`docs/insurance-kb/47-m152-eight-product-dynamic-gapfill.md`。

### Mission 153 业务纠偏与单次运行提速例外

用户已明确批准 Mission 153：允许在当前 worktree 内只读四份业务 XLSX，实施问题
字段结构化、表格感知抽取、已确认结果防回退、单次运行页面/表格/候选复用、上下文
降重与最多 2 路的确定性并发计划。不做持久化 PDF 候选缓存；不外发材料、不调用
外部模型、不写生产数据库、不形成 CandidateRelease/Release/Active，也不提交或推送
GitHub。适用 OpenSpec 为 `153-business-badcase-regression-table-aware-performance`。

### Mission 154 四路产品级并发例外

用户已明确批准 Mission 154：在当前自有 worktree 内接入最多四路产品级并发，
每款产品内部批次继续串行；增加跨产品共享的原子调用预算、按输入产品顺序稳定
合并、Provider 429 时从 4 路逐级降为 2/1 路，以及材料解析、计划构建、Provider、
合并写盘的分阶段耗时记录。四路并发必须来自容量配置，不得成为产品数量硬上限。
本 Mission 冻结 Schema、Prompt、Evidence 和 M153 回归审核规则；不调用外部模型，
不写生产数据库，不形成 CandidateRelease/Release/Active，也不提交或推送 GitHub。
适用 OpenSpec 为 `154-four-product-concurrency-performance`。

### Mission 155 八款四路真实抽取例外

用户已明确批准 Mission 155：使用 M154 最新代码重跑当前冻结八款产品，允许外发
26 份 PDF、454 页材料，最多调用 18 次百炼 `qwen-plus`。唯一写 Owner 为当前总控
Codex，执行模型为 `gpt-5.6-sol high`；预计一个本地运行结果和一份 audit，不创建 PR。
结果必须写入独立 `provider-run-m155-eight-products-concurrent.json` 及配套 audit，
不得覆盖 M150/M152；完成后允许重启 8091/5174 指向新结果。验收要求为八款均有
终态、调用不超预算、产品内批次串行、峰值不超四路、结果顺序稳定、耗时回执完整且
前后端 live probe 通过。明确非目标为修改 Schema/Prompt/Evidence/审核规则、写生产
数据库、形成 CandidateRelease/Release/Active 或提交/推送 GitHub。输入 identity
漂移、凭据不可用、调用预算不足、持续 429/Provider 错误或结果合同无效均为停止条件。
适用 OpenSpec 为 `155-eight-product-concurrent-provider-run`。

### Mission 156 七字段原子事实与完整性例外

用户已明确批准 Mission 156：允许当前总控 Codex 作为唯一写 Owner，在自有
`InsuranceKB-WeKnora-ingest` worktree 内优化保险责任、责任免除、缴费期限、
缴费方式、保单权益、等待期、疾病定义与认定标准。范围固定为 596、5003、1830、
1814、1816、1828 六款，沿用 M155 的 20 份 PDF、390 页冻结材料；允许外发百炼并
最多调用 18 次 `qwen-plus`。输出必须写入独立 M156 result/audit，不覆盖 M155；完成
后可让本地 8091/5174 指向 M156。

本轮只允许字段全材料候选、原子事实抽取、结构化归并、完整性/反混淆/Evidence
语义复核、定向补抽、测试与本地评测。六款材料支持口径不得低于 M155 同六款
`133/143=93.01%`；端到端目标不超过 20 分钟。明确非目标为修改 Schema、持久化 PDF
缓存、OCR/Embedding/DeepSeek 调用、生产 DB、CandidateRelease/Release/Active、
Git commit/push/PR。材料或 Catalog identity 漂移、18 次预算不足、持续 Provider 错误、
整体抽取率回退或结果合同无效即停止。适用 OpenSpec 为
`156-seven-field-atomic-completeness`。

2026-09-11 追加授权：首轮 18 次 qwen-plus 返回因 M156 执行器字段拓扑接线
缺陷在合并前全部被拒绝。用户批准使用已修复代码重新外发同六款 20 份 PDF，
最多追加 18 次 qwen-plus，结果写入独立
`provider-run-m156-six-products-seven-field-rerun.json` 与配套 audit，成功后更新
本地 8091/5174。其余范围、停止条件、非目标及生产隔离边界不变。

### Mission 157 七字段章节化抽取与适用范围纠偏例外

用户已明确批准 Mission 157：当前总控 Codex 是唯一写 Owner，执行模型为
`gpt-5.6-sol high`。本轮复用 M156 冻结的 596、5003、1830、1814、1816、1828
六款产品和 20 份 PDF，在当前 worktree 内修复七个重点字段的抽取不全、概括不全和
适用范围误判。允许外发这些材料并最多调用 24 次百炼 `qwen-plus`，结果必须写入
独立 `provider-run-m157-six-products-quality.json` 及配套 audit；成功后允许更新本地
8091/5174，不覆盖 M156。

实施范围固定为：长字段单字段/章节窗口抽取；每条原子事实逐项审核；同一段长原文可
支撑多个原子项但每个原子项必须被语义命中；区分当前产品、主险与附加险的适用范围；
exact/normalized 失败后只允许唯一高置信 Evidence 重定位；保留四路产品并发、产品内
串行和稳定合并。验收要求为 20 次主调用加最多 4 次受控修复/重试、六款均有终态、
材料支持口径不低于 M156 的 `133/143=93.01%`，既有正确字段不得回退，并记录逐字段
before/proposed/after、审核理由、页面覆盖和耗时。

明确非目标为修改 Schema、根据业务答案硬编码字段值、持久化 PDF 候选缓存、调用
OCR/Embedding/DeepSeek、写生产数据库、形成 CandidateRelease/Release/Active，或执行
Git commit/push/PR。冻结材料、Catalog、M156 baseline 或业务反馈 identity 漂移，24 次
预算无法覆盖主调用，持续 Provider 错误，整体抽取率回退或结果合同无效均为停止条件。
适用 OpenSpec 为 `157-seven-field-section-applicability-evidence`。

### Mission 158 业务七字段质量闭环例外

用户已明确批准 Mission 158：当前总控 Codex 是唯一写 Owner，执行模型为
`gpt-5.6-sol high`。本轮复用 M157 冻结的 596、5003、1830、1814、1816、1828
六款产品和 20 份 PDF，针对保险责任、责任免除、缴费期限、缴费方式、保单权益、
等待期、疾病定义与认定标准进行业务问题闭环。允许修改当前 worktree、外发上述材料、
最多调用 32 次百炼 `qwen-plus`，写入独立 M158 result/audit/feedback assessment，
结果合同有效后更新本地 8091/5174。

实施范围固定为：长字段章节/页窗口分片和原子项确定性合并；丢弃不承担唯一支持作用的
未定位 Evidence 后重新执行逐原子支持校验；缴费期限/方式联合语义校验；等待期的期限、
意外例外和后果完整性；当前产品与主附险适用范围；业务反馈 30 条逐项独立验收。业务
答案不得进入生产 Prompt 或产品特例规则。验收要求材料支持口径不低于 M157 的
`133/143=93.01%`，既有正确字段不回退，长字段不再依赖 32768 token 单次输出，且
逐项报告 `RESOLVED/PARTIAL/UNRESOLVED/NOT_SCORABLE`。

明确非目标为修改 Schema、持久化 PDF 候选缓存、调用 OCR/Embedding/DeepSeek、写
生产数据库、形成 CandidateRelease/Release/Active，或执行 Git commit/push/PR。冻结
输入 identity 漂移、连续 Provider 错误、调用预算不足、整体抽取率回退、正确字段被覆盖
或结果合同无效均为停止条件。适用 OpenSpec 为
`158-business-seven-field-quality-closure`。

### Mission 159 前端结果契约纠偏扩展

用户已于 2026-09-14 批准 M159 前端契约补丁。业务目标是让 5174 正确展示已经由
8091 返回的 exact M159 六款结果，不重新抽取、不改结果内容。当前总控 Codex 是唯一
写 Owner，执行模型为 `gpt-5.6-sol high`；预计 0 个 PR、30 分钟内完成，依赖现有
M159 result `v5-trial-b45293f71e3b0cd0` 和正在运行的 8091/5174。

验收固定为：前端契约接受全局最多 32 次调用以及单产品在同一全局预算内的调用回执，
仍拒绝第 33 次调用；exact M159 数据通过解析并在 `/v5-preview` 展示六款产品。非目标为
改 Schema、Prompt、Evidence、抽取结果、调用外部模型、写生产数据库、形成 Release/
Active 或提交/推送 GitHub。若放宽两处上限后 exact M159 仍因其它合同不一致失败，立即
停止并报告新的错误指纹。适用 OpenSpec 继续为
`158-business-seven-field-quality-closure` 的 M158-R5。

```text
B0 -> G1 -> G2 -> G3 -> G4 -> G5 -> G6A -> G6B -> G6C -> G6D -> Q0 -> G7
```

不得并行、跳卡、把 Q0 前移，或创建 successor/条件卡续命。文档冻结期间产品
WIP=0；开始执行后 WIP=1。任何测试 GREEN、fixture replay、代码量、提交数或
receipt 数量都不能代替本文件要求的真实物理结果。

## 1. 全局不变量与证据口径

1. 只有一个统一 KnowledgeBase、一个 WeKnora Wiki、一个审核入口和一个 Active
   Head。Harness 只做领域编译、实体解析、Evidence、Candidate/ChangeSet、概念
   准入与 evaluator；不得拥有第二 Wiki、第二审核、第二 Active 或在线读取副本。
2. 产品、权益、服务、理赔、核保只是版本化分类与导航视图，不是独立 Wiki。
   `KnowledgeEntity` 的稳定 ID 不随标题、分类或主导航路径变化。
3. 医疗险 67 个字段及其 7 节点实例只属于医疗险的版本化 SchemaPack/Profile。其余
   10 类产品 pack 只借鉴其布局方法，各自按实际定义 6、7、8 或其它节点数的 Profile；
   权益和服务使用自己的 SchemaPack/Profile。不得把 Schema67、7 节点数量或医疗险节点
   名称写成全局本体。
4. 实体页、section、`FieldAssertion`、`ConceptDefinition` 与动态聚合均读取同一份
   Claim/Evidence/Active Release。Markdown 是投影，不是第二份事实权威。
5. 页面显示短标题，内部 identity、索引与调用使用稳定、完整、带命名空间的长 ID。
   从实体或 section 点击字段时，默认进入该实体自己的 FieldAssertion 页面；共享
   ConceptDefinition 只能由 FieldAssertion 再链接。
6. 每卡开工前把本卡的 source revisions、corpus、SchemaPack、模型/配置、expected
   outcomes、分母、阈值和前卡 release/evidence identity 冻结并计算 digest。执行中
   换样本、降分母、跳过失败项或人工补齐冒充模型成功，均为 FAIL。
7. `REAL_PASS_EVIDENCE` 必须来自真实解析、Candidate、页面、审核、Release、查询和
   source click。mock、fixture、截图单独存在、接口 200 或手写 receipt 只能作测试证据。
8. 每个 Evidence Pack 至少记录 Goal ID、run ID、代码与 runtime identity、冻结输入
   digest、开始/结束时间、操作者、真实输出、断言结果、失败项、页面/Release identity、
   source locator 回点结果、测试与 `git diff/status`。秘密不得进入包内。
9. 同一真实阻断只允许一次有证据、有界、单变量纠偏；第二次仍失败即停止并请求用户
   裁决。出现第二层前置、新服务、新表、通用平台或第二套系统时立即停止。
10. 11 类 SchemaPack “完成注册”“完成真实 FLOW”“完成领域质量准入”是三个不同状态。
    未经 pack-scoped Q0 的 pack 只能是 `REGISTERED_NOT_QUALITY_ADMITTED`；其知识内容
    无论审核策略都不得进入生产 Active，也不得用医疗险结果外推其质量。

## 2. B0 · 815 证据基线与资产裁决

- **CURRENT_RED**：`BASELINE_815_NOT_FROZEN_FOR_830`。
- **NEXT_PHYSICAL_RESULT**：一份可重算的 815 FLOW PASS baseline manifest、干净
  830 execution base、有限候选集的 `KEEP / REWIRE / FREEZE / SUPERSEDE` 台账，以及
  当前验证/镜像 change-impact baseline 和 branch/worktree manifest。
- **目标**：固定已经跑通的 815 upload/parse→Candidate→Preview/Review→Active→
  current/pinned→source click 物理证据；只裁决 830 如何继承，不重跑、不重造主链。
- **冻结输入**：integration head `9fcf3386833d822a31f2de13fdf76c3eb6b13795`、tree
  `7314d1c9bc82dc7efb114affb6f2450d0dbd36ae`、receipt
  `/private/tmp/weknora-815-final-9fcf3386/receipts/c7-ui-visible-terminal.json`、contract
  `weknora.815.c7-ui-visible-terminal.v1`、server/UI `GO`，执行时精确的 `origin/main`
  和 upstream identity，以及 11 类 Schema 工作簿
  `【汇总】11类保险产品知识Schema_全局一致性校验更新版_20260812-v5.xlsx`、
  SHA-256=`8feb33a1e7dc55fad1719a151737822e62bfac815f4b0969441e38744f0204ec`。
- **有限候选集**：只包含拟被 830/G1 消费的资产、明确关联旧执行口径的资产，以及当前
  830 worktree/集成差异；只有该集合需要四态深审。
- **Baseline manifest**：仅从已有日志、receipt 或 CI history 重算当前验证入口耗时，冻结
  样本窗口、样本量、D0–D3 适用层和 p50/p95；样本不足记 `NOT_MEASURED + reason`，不阻断
  B0，待首次获授权的 D2/D3 实测补齐，不为测量启动环境。另建立 service→相关 source
  subset、Dockerfile/context、lockfiles、base digest、build args、platform 的镜像
  change-impact 映射，并冻结可复用 artifact identity 规则；禁止只用 Git SHA 判断复用。
- **Branch/worktree manifest**：全历史 branch/worktree 只机械登记 base、head、owner、
  last activity 与所属 Goal 或 PR；未命中有限候选集的项目标记 `INDEX_ONLY/OUT_OF_SCOPE`，
  不做四态深审。有限候选项另记相对正式 base 未集成提交、四态与计划物理处置。B0 裁决完成
  且用户授权物理处置前只登记、不删除；worktree 不得充当归档。
- **允许写域**：baseline/asset/validation/image-impact/branch-worktree manifest、Evidence
  Pack、Handoff 状态与为 830 新建的 clean worktree/branch identity；产品代码和运行数据只读。
- **明确非目标**：不调用 Provider，不启动或重跑 815 真实环境，不构建 Docker 镜像，
  不重抽 Schema67，不恢复 815 Goal，不整包合并或删除历史分支/worktree，不把 815 FLOW
  PASS 写成 Schema67 QUALITY PASS；不把 CI 改造、路径过滤或缓存优化变成 B0 前置。
- **Day 2 物理结果**：receipt 与代码/runtime identity 已重算一致；clean base 的
  `git status` 为空；有限候选集内所有资产恰好归入 KEEP、REWIRE、FREEZE 或 SUPERSEDE，
  四类互斥且穷尽，每项有理由；可复用项还必须注明目标消费卡。当前验证入口的 p50/p95 或
  `NOT_MEASURED + reason`、D0–D3 适用层、镜像影响映射和 artifact 复用 identity 均可从
  manifest 重算。
- **真实 DoD / 验收证据**：815 的 7 section、67 field、17 citation、PDF page/quote、
  current/pinned 证据均绑定同一已知 release/runtime；830 base 可由 manifest 复现；
  与 origin/main 的差异逐项可解释；四类处置互斥且覆盖有限候选集，该集合未分类资产=0，
  脏文件=0；冲突旧执行语义必须为 SUPERSEDE，不能伪装成 FREEZE。每个当前验证入口均
  明确 D0–D3 适用性，`DOCKER_ACTION` 默认 `SKIP`，日常 `build-all`、
  `start-all --no-pull` 被明确禁止；B0 PASS/STOP 的 830 worktree 关闭证明包含 clean
  status、相对正式 base 未集成提交清单、四态与物理处置，移除后仍可审计。
- **时间盒**：1–2 个工作日。
- **停止条件**：任一 815 identity/hash 不一致、receipt 无法打开、clean base 需要
  产品修复、资产必须整包合并才可用，或有人要求重跑 Provider/815 真实环境、Docker
  全构建或先改 CI，立即停止并报告。
- **Evidence Pack**：baseline manifest、hash 重算输出、receipt 副本、runtime/UI
  证据索引、origin/main 差异摘要、验证耗时与镜像影响 baseline、artifact identity 规则、
  branch/worktree manifest、有限候选集四态处置表及穷尽性/互斥性检查、worktree 关闭证明
  和独立复核结论；工作簿复制到可持续审计位置后的 exact hash/size，不允许后续执行依赖
  Downloads 临时路径。

## 3. G1 · 实体页图与独立 FieldAssertion

- **CURRENT_RED**：`LOCKED_BY_B0`；B0 PASS 后转为
  `NO_ENTITY_SCOPED_INDEPENDENT_FIELD_PAGES`。
- **NEXT_PHYSICAL_RESULT**：一个真实医疗险实体的 overview、7 个 section、67 个
  独立 FieldAssertion 页面和空 `free_wiki` 分组进入同一原子 Release。
- **目标**：把 815 连续页能力 REWIRE 成实体页图；字段仍由 SchemaPack 保底，但每个
  FieldAssertion 成为可独立访问、可回点、可链接共享概念的实体作用域页面。
- **冻结输入**：B0 release/evidence identity、一个真实实体及稳定 `entity_id`、11 类
  Catalog 中的医疗险 SchemaPack version/hash、ordered67、9 个业务 schema categories
  到当前 7 个 presentation sections 的映射、三态、标题/route/long-ID 规则和 locator 合同。
- **允许写域**：Harness 的 entity/page compiler 与 payload contract；WeKnora 通用
  Wiki route、页面模板、导航和原子 Release 接口；对应测试与 Evidence Pack。
- **明确非目标**：不建图数据库、第二 Wiki、通用本体或新发布器；不在 G1 生成共享
  概念正文；不把 67 字段固定给非医疗实体；不复制 Markdown 作为新权威。
- **Day 2 物理结果**：真实 Candidate Preview 中可见同一实体 overview、至少 1 个
  section、至少 3 个独立 FieldAssertion 与空 free_wiki；字段点击落到自身稳定 URL，
  标题短而页面 payload 保留完整长 ID。
- **真实 DoD / 验收证据**：1 overview + 7 section + 67 FieldAssertion + 1 空
  free_wiki 分组全部真实存在；67/67 均有 present/absent/unknown，UNKNOWN 保留页面和
  typed reason；改短标题或分类后 URL/ID 不变；字段默认点击自身页；known Evidence
  与页面读取同一 Claim/Evidence；整实体只出现一个 release_id，激活前后无混版。
- **时间盒**：3–5 个工作日。
- **停止条件**：需要按页分别激活、依赖第二事实存储、URL 必须使用可变标题、任一字段
  只能落到共享概念页，或 48 小时仍无真实 FieldAssertion 页面，立即停止。
- **Evidence Pack**：entity/page manifest、67 页清单及 hash、route 稳定性结果、
  source-click 样本、release 原子性读证据、UI 录屏/截图、测试和 diff/status。

## 4. G2 · 共享 ConceptDefinition 与 free_wiki 准入

- **CURRENT_RED**：`LOCKED_BY_G1`；G1 PASS 后转为
  `NO_SHARED_CONCEPT_OR_VALUE_ADMISSION`。
- **NEXT_PHYSICAL_RESULT**：首批共享 ConceptDefinition 由实体 FieldAssertion 链接并
  动态聚合；实体独立 `free_wiki` 分组同时承载首批通过价值准入的模型发现页面。两条
  链共用同一 Candidate/Review/Release，但不互相冒充。
- **目标**：把专家维护的稳定概念定义和由当前 Active 数据计算的实体/字段聚合彻底
  分开；允许模型发现 schema 外知识，但只有有价值且有 Evidence 的概念可以晋级。
- **冻结输入**：G1 entity release、ConceptDefinition/alias/link identity 规则、概念
  准入策略，以及由具名专家批准并带 digest 的 24 项小 Golden；Golden 同时含应晋级
  项和重复、广告词、OCR 噪声、无证据碎片等垃圾项。
- **允许写域**：Harness concept candidate、去重/准入、Evidence 与 aggregation query；
  WeKnora 通用 concept/free_wiki 页面和 FieldAssertion→ConceptDefinition 链接；测试与证据。
- **明确非目标**：不建全局本体平台、Graph DB、自动研究或通用 Prompt 平台；动态聚合
  不得回写专家定义；free_wiki 不得绕过 Candidate/Review/Release。
- **Day 2 物理结果**：至少一个专家定义页与两个真实 FieldAssertion 链接；定义正文在
  Active 实体数量变化时 hash 不变，聚合列表随 Active 数据变化；至少一个垃圾候选被拒。
- **真实 DoD / 验收证据**：24/24 attempted；所有晋级概念 Evidence 语义支持与精确
  回点率=100%；垃圾晋级=0；promotion precision≥90%；expected promotion recall≥80%；
  零分母不得通过；专家定义、动态聚合和实体断言的 provenance/hash 可分别重算；拒绝项
  不出现在 Active concept、free_wiki、导航或默认检索结果。
- **时间盒**：4–6 个工作日。
- **停止条件**：需要复制定义到每个实体、聚合结果成为可编辑权威、垃圾晋级大于 0、
  Evidence 低于 100%，或必须引入新概念平台，立即停止。
- **Evidence Pack**：24 项 Golden/hash、逐项预测和裁决、precision/recall 分母、垃圾
  拒绝清单、定义/聚合独立 hash、链接与 source click 录屏、Release/test/diff 证据。

## 5. G3 · 11 类 SchemaPack Catalog、展示 Profile、统一分类与批量实体识别

- **CURRENT_RED**：`LOCKED_BY_G2`；G2 PASS 后转为
  `NO_REAL_BATCH_ENTITY_RESOLUTION`。
- **NEXT_PHYSICAL_RESULT**：11/11 产品 SchemaPack 形成可重算 Catalog manifest；
  10–15 份真实材料形成可审计的实体解析批次，并通过同一 KB 的版本化分类和相应
  SchemaPack 进入安全 Candidate/页面链。
- **目标**：把工作簿导入为数据驱动的版本化 Catalog，而不是 11 份硬编码；证明系统能
  匹配既有实体、创建新实体、拆分多实体材料并对歧义 fail closed。产品/权益只是分类，
  各产品只使用自己的 SchemaPack，非医疗内容不被强塞 Schema67。11 个产品 pack 复用
  医疗险已验证的分组布局方法，但各自根据业务实际形成 6、7、8 或其它节点数的版本化
  PresentationProfile；共用一个可变节点 renderer，不开发 11 套 UI。
- **冻结输入**：10–15 份真实材料及 exact SourceRevision，覆盖至少 2 个既有实体、
  1 个新实体、相似名称、版本差异、1 份多实体材料，并覆盖至少 4 个具有代表性差异的
  产品 pack：医疗险、重疾险、寿险/储蓄型之一、意外/护理/失能之一；同时冻结 v5 工作簿
  exact hash、11 个 pack 的字段数与业务分类数、154 个去重字段、47 个全产品共用字段；
  同时冻结“有序 section 集合 + 字段映射”的可变节点 renderer 合同、每个 pack 的预期
  section count/keys/显示名和 category→section 映射；冻结专家标注的预期 entity identity、分类、SchemaPack 和
  处置结果，以及相互独立的
  identity/classification threshold、policy hash、自动流转条件与人工队列条件。
- **允许写域**：Harness SchemaPack registry、entity resolver、classification Candidate
  与 Evidence；WeKnora 统一导航/标签投影；测试和 Evidence Pack。
- **明确非目标**：不按产品/权益另建 KB，不让分类决定来源权威，不因改分类重抽字段，
  不自动合并歧义实体，不建设低代码 Schema/分类平台。
- **Day 2 物理结果**：11/11 pack 已生成 manifest，字段数严格为
  `67/70/62/67/66/75/79/82/74/83/76`，154 个去重字段和 47 个全产品共用字段可重算；
  11/11 pack 从工作簿业务分类和医疗险既有布局批量生成各自的 PresentationProfile
  Candidate，并完成一次整包确认；各 pack 节点数按业务实际可不同，所有字段恰好映射到
  一个主节点，正式 Profile 空节点=0，不要求专家逐字段手工配置；
  冻结 corpus 全量预检完成，至少 3 份真实材料分别产生 MATCH、CREATE 和
  NEEDS_CONFIRM/MULTI 的可打开 Candidate；每个决定带 Evidence 和置信原因。
- **真实 DoD / 验收证据**：Catalog 11/11 注册成功，每个 pack 绑定 catalog/pack
  version/hash；所有英文名非空，单 pack 重复字段名/英文名=0；字段的业务分类、说明、
  取值来源指导、知识形成方式、知识角色、公共标记和频次均可重放。工作簿的 9–10 个
  `schema_category` 与每个 pack 自己的 `presentation_section` 使用版本化映射，
  11 个 profile 共用一个可变节点渲染器；Profile 是 field→section 及顺序的唯一权威，
  FieldDefinition 不独立存储可写的 `presentation_section`；字段映射 orphan=0、
  duplicate primary mapping=0，不以
  分类编号硬编码目录。
  10–15/10–15 真实材料 attempted；`MATCH / CREATE / MULTI /
  NEEDS_CONFIRM / QUARANTINE` 五种结果各有真实用例；专家 adjudication 下错合并=0；
  达到 classification threshold 的明确分类自动形成可审计决定；满足 exact identity key、
  关键身份 Evidence、identity threshold 且无别名/版本冲突的新实体自动创建幂等
  `EntityCandidate`（不是 Active）；低置信、同名多版本、身份冲突和混合材料必须进入
  具名人工队列，不得用“全部人工”冒充自动化验收；
  MULTI 的每个实体有独立 Evidence；歧义项不进 Active；所有未完成 pack-scoped Q0 的
  内容 Candidate/页面链只能进入隔离 `NOT_FOR_PRODUCTION` Release，不得进入生产 Active；
  每个实体使用自己的 SchemaPack，非医疗产品无 Schema67 填充；对每个已选 SchemaPack，FieldDefinition 数量必须与该
  实体的独立 FieldAssertion 页面数量完全相等，所有字段均 attempted，不能用组合表格
  或锚点替代；修改分类后 entity ID、Evidence、历史和字段 hash 不变，仅版本化标签/
  主导航路径变化。
- **时间盒**：5–7 个工作日。
- **停止条件**：出现一次错合并、歧义被静默 MATCH、冻结阈值被临场修改、高置信样本
  全被推给人工、低置信样本被自动流转、分类改变 identity/Evidence、非医疗内容依赖
  Schema67、节点数量被写死为 7、Catalog 数量/字段数与 v5 不一致、schema category 被当成固定 UI 目录、公共
  字段仅凭同名静默合并，或统一 KB 必须被拆分，立即停止。
- **Evidence Pack**：corpus/revision manifest、专家 expected labels、逐材料 disposition、
  Catalog/11 pack manifests、字段计数与去重检查、11 个 PresentationProfile
  identity/hash、section count、category→section mapping、entity
  merge/split graph、分类前后 hash、SchemaPack 选择证据、Active/隔离清单和 UI 录屏。

## 6. G4 · 增量更新、冲突、双时态与 R2

- **CURRENT_RED**：`LOCKED_BY_G3`；G3 PASS 后转为
  `NO_INCREMENTAL_R2_OR_CONFLICT_SAFETY`。
- **NEXT_PHYSICAL_RESULT**：冻结第二批真实材料从 R1 生成原子 R2，并可证明冲突隔离、
  无关字段不变、双时态、pinned read 与 release-level rollback。
- **目标**：只重算受影响闭包，以七种冻结语义表达增量；模型永远不能覆盖专家已确认
  事实，未决冲突永远不能改变 current。
- **冻结输入**：G3 的 exact R1、第二批 SourceRevision、受影响实体/字段和 expected
  change matrix、专家锁定项、权威序、有效时间/获知时间、R2 与 rollback 查询脚本。
- **允许写域**：Harness ChangeSet、merge/conflict、affected closure 与 temporal model；
  WeKnora 唯一 Release/current/pinned/revert 通用接口；测试和 Evidence Pack。
- **明确非目标**：不做全量重编替代增量，不物理删除历史，不建第二 current pointer，
  不实现任意双时态查询语言，不允许单页 cherry-pick 冒充整版 rollback。
- **Day 2 物理结果**：第二批真实输入已产生可重算 ChangeSet；至少可观察 SAME、ENRICH、
  CONFLICT 和 UNCHANGED，冲突字段 current 仍等于 R1，无关 FieldAssertion hash 不变。
- **七种语义**：`SAME`=incoming 与既有规范化事实、作用域、有效期相同且无新增信息，
  只记观察；`ENRICH`=事实不变但新增/更强 Evidence、限定条件或元数据；
  `SUPERSEDE`=同一作用域/重叠有效期内新权威事实取代旧事实且旧值留历史；
  `COEXIST`=值不同但版本、地域、渠道、人群或有效期不重叠；`CONFLICT`=同一作用域、
  重叠有效期内矛盾且规则不能裁决；`RETRACT`=来源撤回、证据失效或专家撤销形成候选
  撤回而非删除；`UNCHANGED`=本次输入对字段/实体无语义影响且无 ClaimRevision/page delta。
- **真实 DoD / 验收证据**：冻结 matrix 中七语义全部 exact；R1→R2 一次原子激活，
  无半新半旧；CONFLICT 不改 current；全部无关字段 content hash 相同；至少一个迟到材料
  同时显示 `effective_from/effective_to` 与可信 `known_at`，current/as_of_date/release_id
  结果正确；专家锁定值面对模型新值仍保留并产生 pending conflict；R2 pinned 不漂移；
  rollback 后 current 回 R1、历史 R2 可 pinned 且两者均可 source click。
- **时间盒**：5–7 个工作日。
- **停止条件**：冲突污染 current、模型覆盖专家、无关字段 hash 漂移、需要全量重编或
  第二 Active、时间由模型猜测、rollback 混版，立即停止。
- **Evidence Pack**：R1/R2/activation identities、七语义逐项 ledger、affected closure、
  前后 field/page hashes、冲突 UI、双时态查询、pinned/rollback/source-click 录屏与并发读证据。

## 7. G5 · 专家编辑、审核策略与审计

- **CURRENT_RED**：`LOCKED_BY_G4`；G4 PASS 后转为
  `NO_EXPERT_EDIT_POLICY_OR_AUDIT_FLOW`。
- **NEXT_PHYSICAL_RESULT**：专家在 WeKnora 内完成一次真实编辑、Diff、History、发布或
  pending、再 Revert；全过程只产生同一 Candidate/Review/Release/Active 链。
- **目标**：复用 WeKnora 现有 edit/diff/history/revert，给专家最小负担的业务编辑面；
  审计自动记录，专家决定优先于后续模型建议。
- **冻结输入**：G4 后 exact Active Release、角色/ACL、字段风险、专家锁定规则、独立
  `EditProvenance` 合同、可选 `reason`/`new_source_evidence` 合同，以及三类
  ReviewPolicy 的准入条件和策略 hash。
- **允许写域**：Harness 专家变更语义、precedence 与 ReviewPolicy；WeKnora 现有页面
  编辑、diff、history、revert、ACL 和唯一 Release wiring；测试和 Evidence Pack。
- **明确非目标**：不建第二编辑器、审计库、审核队列或 Active；不要求专家填写冗长
  表单；不允许原地改 Active payload；不让模型自动解除专家锁定；不把
  EditProvenance 或旧 SourceEvidence 包装成支持专家新值的 SourceEvidence。
- **Day 2 物理结果**：一个发布者编辑显示 before/after Diff，并在隔离环境形成新 immutable
  `NOT_FOR_PRODUCTION` Release/current；一个非发布者编辑形成 pending 且 current 不变；
  reason/new evidence 可留空但审计完整。
- **三类审核策略**：`AUTO_ACTIVE` 仅限低风险、无冲突且 identity/Evidence/quality 硬门
  全过，仍走 Candidate→可审计决定→Release→CAS；`ONE_CLICK_BATCH` 用于中风险或批量
  新实体，具名审核人看到摘要、Diff、Evidence 后整批批准/拒绝；`MANDATORY_REVIEW`
  用于高风险、CONFLICT、专家锁定冲突、低置信或 Evidence 异常，必须具名人工决定。
- **Q0 前边界**：G5 可以在隔离环境真实验证三策略和 Release/CAS，但未通过 pack-scoped
  Q0 的知识内容无论采用哪种策略，都必须标记 `NOT_FOR_PRODUCTION`，不得进入生产 Active。
  pack Q0 PASS 后才开放生产人工审核；质量门和策略均获批准后，才允许低风险内容生产
  AUTO_ACTIVE。
- **真实 DoD / 验收证据**：三策略各有真实决定记录；其中 Q0 前三策略都只计隔离
  流程能力，不计生产质量放行。有发布权限者在隔离环境保存后直接形成新 immutable
  Release/current（不是原地修改），无发布权限者只能 pending；拒绝不改 current；actor、role、
  time、before/after hash、policy、decision、可选 reason/new source evidence 进入独立
  EditProvenance；无新来源时 `supporting_source_evidence_ids=∅` 并明确显示“专家修改
  （无新增来源证据）”，旧来源只能作为 `prior_source_evidence_ids` 显示且不得计入新值的
  Evidence/质量门；history/diff 可打开；revert 形成新的不可变 Release；后续模型冲突
  只进 pending，专家值不变。
- **时间盒**：3–5 个工作日。
- **停止条件**：任何角色可绕过服务端授权、编辑原地改 Active、审核记录依赖手填日志、
  EditProvenance 被当成 SourceEvidence、旧来源继续支持已被专家改写的新值、Revert 删除
  历史、模型覆盖专家，或需要另建审核系统，立即停止。
- **Evidence Pack**：角色矩阵、三策略 decision records、EditProvenance 与
  SourceEvidence 隔离断言、编辑/diff/history/revert 录屏、Release/Head 前后 hash、
  pending/reject 不变证据、专家优先级冲突证据和 source click。

## 8. G6A · OCR PDF / 图片纵切

- **CURRENT_RED**：`LOCKED_BY_G5`；G5 PASS 后转为
  `NO_EXACT_OCR_IMAGE_SOURCE_LOCATOR`。
- **NEXT_PHYSICAL_RESULT**：真实扫描 PDF 与真实图片各跑通 parse→Formal Candidate→
  entity/FieldAssertion page→精确来源点击。
- **目标**：冻结跨格式 `SourceLocator` 联合类型并先打通 OCR；复用 WeKnora 解析、原件
  存储和 viewer，Harness 只消费解析结果、校验 locator 和编译知识。
- **冻结输入**：至少 1 份真实扫描 PDF、1 张真实图片、文件 hash/SourceRevision、预期
  assertion/Evidence；union IDs 为 `TEXT_BLOCK_OFFSET`、`PDF_PAGE_BBOX`、
  `IMAGE_REGION`、`DOCX_PARAGRAPH_RANGE`、`PPTX_SLIDE_SHAPE_RANGE`、
  `XLSX_SHEET_CELL_RANGE`；PDF locator 含 `text_origin=NATIVE|OCR`。
- **允许写域**：既有解析 adapter 的最小复用、Harness locator union/validator、WeKnora
  通用 viewer deep link/highlight；该格式测试和 Evidence Pack。
- **明确非目标**：不自建 OCR 引擎、文件库或 viewer，不改保险 Claim 语义，不以生成
  文本或第 1 页兜底，不因 OCR 不准伪造 quote/bbox。
- **Day 2 物理结果**：两个真实来源均产出持久 SourceRevision 与可重开 locator；至少
  一个 OCR Candidate 的 quote 可在原图区域精确高亮，TEXT_BLOCK_OFFSET 回归仍通过。
- **真实 DoD / 验收证据**：扫描 PDF 和图片分别完整跑通；Candidate/page/release/source
  identity 可追溯；点击打开 exact PDF page+bbox 或 exact image region，quote 与 OCR
  产物一致；刷新、pinned read 后 locator 不漂移；原生文本 block/offset 未回归。
- **时间盒**：3–5 个工作日。
- **停止条件**：解析器无稳定 locator、点击只能近似定位、需要第二 OCR/viewer、文件
  identity 变化或 locator 验证失败，立即 fail closed 并关闭 G6A。
- **Evidence Pack**：原件/revision hashes、parse manifest、locator payload/validator、
  Candidate/page/release IDs、PDF/图片精确点击录屏、TEXT_BLOCK_OFFSET 回归和失败样本。

## 9. G6B · Word 纵切

- **CURRENT_RED**：`LOCKED_BY_G6A`；G6A PASS 后转为
  `NO_EXACT_DOCX_SOURCE_LOCATOR`。
- **NEXT_PHYSICAL_RESULT**：一份真实 Word 材料跑通 parse→Formal Candidate→page→
  精确段落或表格单元格来源点击。
- **目标**：复用 Word 解析与预览；以 `DOCX_PARAGRAPH_RANGE` 扩展 G6A union，其中
  `range_kind=PARAGRAPH|TABLE_CELL`，不新增平行 Evidence 路径。
- **冻结输入**：真实 DOCX、file/SourceRevision hash、预期 assertion、段落与表格样本、
  G6A locator contract 和 exact viewer 行为。
- **允许写域**：现有 DOCX parse adapter、locator payload/validator、通用 viewer deep
  link；Harness Candidate/page adapter、测试和证据。
- **明确非目标**：不自建 Office 转换服务或 Word viewer，不把转换后 PDF 当原件，
  不改变 G6A locator union 或新建格式专用发布链。
- **Day 2 物理结果**：真实 DOCX 已有可重开 SourceRevision；至少一个段落和一个表格
  单元格 locator 经 validator 后进入 Candidate，并能从 Preview 点击定位。
- **真实 DoD / 验收证据**：真实 Word 全链成功；paragraph/table-cell 两种 range_kind
  均精确；Candidate、FieldAssertion、Active page 和原件 locator 同 identity；刷新、
  current/pinned 与标题变化不导致 locator 漂移。
- **时间盒**：2–4 个工作日。
- **停止条件**：只能下载整份文件、段落/单元格无法稳定定位、必须重写解析器或以猜测
  offset 代替 locator，立即 fail closed。
- **Evidence Pack**：DOCX/revision hash、parse/locator manifest、两类点击录屏、
  Candidate/page/release trace、validator/test 结果和 diff/status。

## 10. G6C · PPT 纵切

- **CURRENT_RED**：`LOCKED_BY_G6B`；G6B PASS 后转为
  `NO_EXACT_PPTX_SOURCE_LOCATOR`。
- **NEXT_PHYSICAL_RESULT**：一份真实 PPT 材料跑通 parse→Formal Candidate→page→
  exact slide/shape 来源点击。
- **目标**：复用 PPT 解析与预览，以 `PPTX_SLIDE_SHAPE_RANGE` 表达 slide、shape 和
  文本范围；沿用同一 Candidate、Evidence、Review 与 Active。
- **冻结输入**：真实 PPTX、file/SourceRevision hash、包含相似文字的多 slide/shape
  样本、预期 assertion、G6A union 和 viewer contract。
- **允许写域**：现有 PPTX adapter、locator validator、通用 viewer deep link；
  Harness format adapter、测试和 Evidence Pack。
- **明确非目标**：不自建演示文稿渲染器，不只按 quote 搜第一个命中，不把 slide 截图
  当新 SourceRevision，不新增 PPT 专用知识库。
- **Day 2 物理结果**：真实 PPTX 解析成功；至少一个 Candidate 绑定 exact slide+shape，
  页面来源点击在有重复文字的情况下仍打开正确对象。
- **真实 DoD / 验收证据**：真实 PPT 全链成功；slide/shape/text-range locator 可重算；
  页面 source click 精确；current/pinned/revert 后仍指向同一原件对象；无 quote-first
  fallback，其他 locator union 成员回归不变。
- **时间盒**：2–4 个工作日。
- **停止条件**：shape identity 不稳定、只能定位到整份或整页、同文案误跳、需要第二
  viewer/解析服务，立即 fail closed。
- **Evidence Pack**：PPTX/revision hash、parse/locator payload、重复文字反例、
  Candidate/page/release trace、精确点击录屏、union 回归与 diff/status。

## 11. G6D · Excel / 表格纵切

- **CURRENT_RED**：`LOCKED_BY_G6C`；G6C PASS 后转为
  `NO_EXACT_XLSX_TABLE_SOURCE_LOCATOR`。
- **NEXT_PHYSICAL_RESULT**：一份真实 Excel/表格材料跑通 parse→Formal Candidate→
  page→exact sheet/cell-range 来源点击。
- **目标**：复用表格解析，确定性保留数字、单位、行列头和合并单元格上下文；以
  `XLSX_SHEET_CELL_RANGE` 接入同一 Evidence/Release 生命周期。
- **冻结输入**：真实 XLSX（含至少一个多 sheet 或合并表头场景）、file/SourceRevision
  hash、预期 cell range/value/unit/header、G6A union 与 viewer contract。
- **允许写域**：现有 spreadsheet/table adapter、确定性 cell normalization、locator
  validator、通用 viewer deep link；Harness adapter、测试和 Evidence Pack。
- **明确非目标**：不自建电子表格引擎，不让模型改原始数字/单位，不把整张 sheet 当
  Evidence，不复制表格到第二事实库，不新增专用发布链。
- **Day 2 物理结果**：真实 workbook 解析成功；至少一个数值 assertion 保留 exact
  value/unit/header 并绑定 sheet+cell range；Preview 点击高亮正确范围。
- **真实 DoD / 验收证据**：真实 Excel/表格全链成功；sheet、cell/range、header、unit
  可重算，合并单元格处理确定；Candidate/page/Active 与原件同 identity；source click
  精确且 current/pinned 后不漂移；数值从 parser 到 release 无模型改写。
- **时间盒**：3–5 个工作日。
- **停止条件**：数值或单位漂移、表头丢失、只能定位整 sheet、公式结果无法绑定 frozen
  workbook identity、需要第二 parser/viewer，立即 fail closed。
- **Evidence Pack**：XLSX/revision hash、parse/cell lineage、前后数值 hash、locator
  validator、Candidate/page/release trace、精确点击录屏、跨格式 union 回归。

## 12. Q0 · Pack-scoped 领域专家质量门（医疗险 Schema67 先行）

- **CURRENT_RED**：`LOCKED_BY_G6D`；G6D PASS 后转为
  `SCHEMA67_QUALITY_NOT_EVALUATED`。
- **NEXT_PHYSICAL_RESULT**：具名领域专家先对冻结医疗险 Schema67 benchmark 完成一轮
  可复算评估；随后每个计划进入生产的其它 pack 各自产出 pack-scoped
  `QUALITY_PASS` 或逐字段 `QUALITY_FAIL`，而非主观签字或由医疗险外推。
- **目标**：最后收口 815 延后的业务抽取质量，并建立可复用的逐 pack 准入门；模型原始
  结果与专家修订后 Release 分开报告，人工修订不能抬高模型指标。11/11 Catalog 注册不
  等于 11/11 质量准入。
- **冻结输入**：v5 Catalog identity；在开卡前冻结 `QUALITY_ADMISSION_WAVE_1`（至少包含
  医疗险、重疾险、寿险/储蓄型之一、意外/护理/失能之一）；当前待准入 pack 的 exact N-field benchmark、
  SourceRevisions、SchemaPack/prompt/model/config、
  expected-present、critical/high-risk exact set、Golden answers/Evidence、comparator、
  evaluator、分母、阈值和 gate hash；具名专家、时间与 Golden digest。
- **允许写域**：Golden、benchmark manifest、独立 evaluator、质量报告与 Evidence Pack；
  首轮失败后仅可修改预先声明的一个 prompt/model-config/normalizer 变量。
- **明确非目标**：不改 benchmark、答案、风险集合、阈值或分母，不跳字段，不把 UNKNOWN
  当未尝试，不以专家修订冒充模型抽取，不在 Q0 新增产品功能。
- **Day 2 物理结果**：医疗险 benchmark 67/67 已由模型原始输出 attempted；后续 pack
  为 N/N attempted；专家逐字段审核面可用；报告同时展示 `MODEL_RAW` 与
  `EXPERT_REVISED_RELEASE`，所有错误有 pack/field ID。
- **真实 DoD / 验收证据**：医疗险 67/67、其它 pack N/N attempted；critical/high-risk 逐字段 state、normalized
  value、适用范围和 Evidence 正确且无遗漏；其他 expected-present recall≥90%；present
  precision≥95%；进入 Release 的全部正式值 Evidence 语义支持与 exact source click=100%；
  hallucinated fact=0；每个 UNKNOWN 有具体 typed reason；零分母、漏评和 locator fallback
  均 fail closed。MODEL_RAW 与专家修改量/修改后 Release 分报；每个 pack 的 Q0 PASS
  都需要模型门和 Release 门分别 PASS。未评估 pack 保持
  `REGISTERED_NOT_QUALITY_ADMITTED`，不阻塞 Catalog 注册，但禁止生产内容发布。
- **Q0 PASS 语义**：`QUALITY_ADMISSION_WAVE_1` 中每个 pack 均独立 PASS；这不表示其余
  注册 pack 已准入。后续启用其它 pack 时复用同一 Q0 模板逐包执行，不新增平行质量平台。
- **时间盒**：每个 pack 每轮 2–4 个工作日，每个 pack 最多两轮；医疗险先行，其它 pack
  按实际上线顺序逐包执行，不把 11 包塞进一次无界 Goal。
- **停止条件**：Golden 未获具名专家批准、输入/gate hash 漂移、有人要求改分母或多变量
  调参、无法区分原始模型与人工修改，立即停止；首轮失败只准一次单变量纠偏，第二轮
  仍失败固定为 `QUALITY_FAIL`，G7 不解锁。
- **Evidence Pack**：catalog/pack identity、benchmark/Golden/gate hashes、专家身份/时间、
  医疗险 67 行或其它 pack N 行逐字段报告、
  原始与修订双报、指标分子分母、错误桶、UNKNOWN reasons、Release source-click 结果、
  单变量 diff 和两轮（如有）完整 run identities。

## 13. G7 · 多格式 FLOW + QUALITY 联合验收

- **CURRENT_RED**：`LOCKED_BY_Q0`；Q0 PASS 后转为
  `JOINT_ACCEPTANCE_NOT_RUN`。
- **NEXT_PHYSICAL_RESULT**：冻结的 10–15 份多格式材料在同一产品 runtime 完成一次
  FLOW + QUALITY 联合验收并产生唯一终态。
- **目标**：不增加功能，只证明前述能力组合后仍是一个统一知识库、一个生命周期、一个
  Active；FLOW 与 QUALITY 同时 PASS 才接受 830。
- **冻结输入**：11/11 Catalog manifests；10–15 份真实多格式材料及 exact revisions，
  覆盖 PDF/OCR/图片、Word、PPT、Excel/表格，以及至少 4 个已完成 pack-scoped Q0 的
  代表性 SchemaPack（医疗险、重疾险、寿险/储蓄型之一、意外/护理/失能之一），以及
  既有实体、新实体、相似/歧义实体、
  多实体材料、第二批更新和冲突；同时冻结 Q0 gate、代码/runtime/model/config identity。
- **允许写域**：验收脚本、只读观测、最小演示数据与 Evidence Pack；产品功能、schema、
  evaluator、阈值和 locator contract 全部冻结。
- **明确非目标**：不在 G7 修功能、补兼容、换模型、改 Golden 或降低质量门；不搭压测/
  运维平台；不把历史分卡 PASS 拼成联合 PASS。
- **Day 2 物理结果**：完整 corpus 至少跑完一次，产生逐材料/逐实体/逐能力矩阵和 exact
  failure list；即使失败也必须能定位到既有 Goal，不得在 G7 内热修。
- **真实 DoD / 验收证据**：同一 runtime 真实完成 upload/parse→SchemaPack/entity
  resolution→Candidate/ChangeSet→page/concept/classification→Preview/Review→唯一 Active；
  演示更新、CONFLICT、专家编辑、current、pinned、R2、revert 和每种格式 exact source
  click；11/11 SchemaPack 均可在 Catalog 中按 exact identity 选择并通过结构校验；参与
  真实 E2E 的至少 4 个 pack 不串模，且每个 pack 均满足
  `FieldDefinition count == independent FieldAssertion page count`，并可从所属的 pack-specific
  PresentationProfile 节点进入；歧义不误合并、冲突
  不改 current、页面不混版。未完成 pack-scoped Q0 的其它注册 pack 不生成生产 Active。
  所有参与 E2E 的 pack Q0 gate/hash 仍有效且联合样本 Release Evidence=100%、
  hallucinated fact=0。只有
  `FLOW=PASS AND QUALITY=PASS` 才可写 `830_ACCEPTED`；其他组合均为 NOT_ACCEPTED。
- **时间盒**：2–3 个工作日。
- **停止条件**：任何 identity/gate 漂移、需要新增功能、出现第二 Wiki/Active、locator
  fallback、错合并、混版或质量失败，立即停止；回到哪个 Goal 及是否重开只能由用户裁决。
- **Evidence Pack**：corpus/revision manifest、11/11 Catalog 结构 hash 与参与 E2E 的至少
  4 个已质量准入 SchemaPack hash、全链 run
  timeline、entity/classification/change/review/release IDs、current/pinned/revert 读证据、
  各格式 source-click 录屏、联合 FLOW/QUALITY 报告和最终独立审查。

## 14. 状态变更与最终报告

每张卡只能由总控依据本卡 Evidence Pack 把状态从 `LOCKED/RED` 改为 `WIP`，再改为
`PASS`、`FAIL` 或 `STOPPED`。任何窗口不得自行宣布产品 PASS。每次状态变更至少报告：

```text
GOAL_ID
CURRENT_RED
NEXT_PHYSICAL_RESULT
FROZEN_INPUT_DIGEST
WRITE_DOMAINS
NON_GOALS
DEADLINE
REAL_PASS_EVIDENCE
FLOW_STATUS
QUALITY_STATUS
SCHEMA_CATALOG_STATUS
QUALITY_ADMITTED_PACK_SET
```

G7 结束时只有两类诚实终态：

```text
FLOW=PASS / QUALITY=PASS / 830_ACCEPTED
FLOW!=PASS or QUALITY!=PASS / 830_NOT_ACCEPTED
```

低质量但流程跑通、专家人工补齐、旧卡单独 PASS、测试全绿或截图齐全，都不得产生
第三种“基本通过”状态。
