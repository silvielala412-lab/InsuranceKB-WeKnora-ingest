# OpenSpec Change 编号注册表（权威占号处）

> **开发入口**：先读仓库唯一必读/贡献规范 [`AGENTS.md`](../../AGENTS.md)，再按
> 其中 SDD 队列使用本注册表。本文只负责 OpenSpec/迁移占号与状态，不复制流程。
>
> **规则（2026-07-16 起生效）**：开新 change 或新 Alembic 迁移前，**先在本表占号**，与 change 目录同 PR 提交；两个 PR 抢同号时，以先合入 main 者为准，后者改号。
> 背景：022 曾被两个独立 change 同时使用（见下），多轨并行后必须先占号再开工。

## Change 编号台账

| 149 | six-insurance-class-local-preview | ✅ Mission 149 / LOCAL EVAL COMPLETED | 保留 M146 三款并补跑年金险、意外险、失能收入损失保险各一款；新增 9 PDF、6/6 次 qwen-plus；六款材料支持口径 126/145=86.90%，8091/5174 已切换；零 DB/Release/Active/GitHub 写入 |
| 150 | serious-illness-two-product-local-preview | ✅ Mission 150 / LOCAL EVAL COMPLETED | 新增重疾险 1828、L2332 两款；6 份 PDF、4/6 次 qwen-plus；合并预览 8 款/7 类，材料支持条件下 78.26% 与 100%；8091/5174 已切换，零 DB/Release/Active/GitHub 写入 |
| 151 | field-semantic-retrieval-gapfill | ✅ Mission 151 / LOCAL CODE COMPLETE | 字段全解析页候选召回、Schema 语义词与答案形态排序、片段字符位置、费率表降噪、动态补抽共用 Retriever；业务 11 个直接漏抽字段 Top-5 候选召回 11/11；37 项 V5 测试通过，零 provider/DB/live/GitHub 写入 |
| 152 | eight-product-dynamic-gapfill-review | 🚧 Mission 152 / APPROVED | 基于 M150 八款冻结 Preview 与 M151 Retriever，补抽 unknown、复核业务表中的不全/错误字段；最多 18 次 qwen-plus，独立 artifact，更新本地 8091/5174；零生产 DB/Release/Active/GitHub 写入 |
| 153 | business-badcase-regression-table-aware-performance | 🚧 Mission 153 / APPROVED | 四份业务问题表结构化、问题类型分流、表格感知候选、已确认结果防回退、单次运行复用与上下文降重；不做持久化候选缓存，零 provider/DB/live/GitHub 写入 |
| 154 | four-product-concurrency-performance | ✅ Mission 154 / LOCAL CODE COMPLETE | 最多四路产品级并发、产品内批次串行、全局调用预算、稳定顺序合并、429 自动降级和阶段耗时；55 项 V5 测试通过，零 provider/DB/live/GitHub 写入 |
| 155 | eight-product-concurrent-provider-run | ✅ Mission 155 / LOCAL EVAL COMPLETED | 八款、26 PDF、454 页；16/18 次 qwen-plus，材料支持口径 172/185=92.97%，Provider 6m54s、端到端 22m29s；8091/5174 已切换，零生产 DB/Release/Active/GitHub 写入 |
| 156 | seven-field-atomic-completeness | 🚧 Mission 156 / APPROVED | 六款、20 PDF、390 页；七个重点字段做全材料候选、原子事实、完整性复核和真实重跑；最多 18 次 qwen-plus，独立结果，零生产 DB/Release/Active/GitHub 写入 |
| 157 | seven-field-section-applicability-evidence | ✅ Mission 157 / LOCAL EVAL COMPLETED | 六款、20 PDF、390 页；24/24 次 qwen-plus，接受 4 个值变化，材料支持口径保持 133/143=93.01%；主附险权益纠偏有效，疾病定义仍受 32K 输出截断影响；8091/5174 已切换，零生产 DB/Release/Active/GitHub 写入 |

| 148 | dynamic-field-gapfill-control | ✅ Mission 148 / LOCAL CODE COMPLETE | 前端字段级补抽/复核入口；后端按候选片段→相邻页→全材料动态扩展并返回 Candidate/Evidence/diff；30 个 Python、4 个前端测试及 type-check/build 通过；不跑产品、不调用 Provider、不写 DB/Active/GitHub |

| 146 | service-supplemental-materials | ✅ Mission 146 / LOCAL EVAL COMPLETED | 596 增加 2 份服务权益 PDF（60 页文本 + 2 页 OCR）；服务字段新增 3 个 present，固定基础字段 83/153→85/153；6 次 qwen-plus、2 次 qwen-vl-ocr；8091/5174 已切换；零 DB/Release/Active/GitHub 写入 |

| 145 | m144-three-product-provider-run | ✅ Mission 145 / LOCAL EVAL COMPLETED | 596/5003/1826，9 PDF，6/6 次 qwen-plus；简介/概览 3/3 present；材料支持口径 66/77（85.71%），8091/5174 已切换；零 DB/Release/Active/GitHub 写入 |

| 144 | content-synthesis-pass | ✅ Mission 144 / CODE COMPLETE | 产品简介、产品概览进入独立内容总结目标集；23 项 Python、9 项前端契约测试通过；未调用 provider、未改服务/DB/GitHub |

| 143 | three-field-full-material-semantic-pass | ✅ Mission 143 / LOCAL EVAL COMPLETED | 五款/15 PDF/10 次 qwen-plus；材料支持口径 109/129（84.50%）；8091/5174 已验证；零 DB/Release/Active/GitHub 写入 |

| 142 | material-supported-recall | 🚧 Mission 已批准 / 实现与三产品验证进行中 | 混合字段语义补抽、材料支持分母与 M142 独立试跑；不写生产、不推送 GitHub |

| 号 | change | 状态 | 备注 |
|---|---|---|---|
| 001 | harness-scaffold | ✅ 已交付 | |
| 002 | goldenset-s0 | ⏳ 7/9 | 真跑部分转 020 |
| 003 | product-master-routing | ✅ 已交付 | |
| 004 | extraction-pipeline-mvp | ⚠️ 第一方历史范围通过；不是当前生产证明 | 可由 028 记录 provenance 后选择性重构；真实效果由 030 验收 |
| 005 | eval-refinement-recall | ✅ 已交付 | 归因清单由 024 承接 |
| 006 | template-fastpath | ⚠️ 第一方历史范围通过；不是 TemplatePackage | 可作为 028 能力输入；PP-StructureV3 后置 |
| 007 | claims-changeset-publish | ✅ 旧范围已交付 | 不含 NS-C/P-1 seal/active alias；生产发布继续 fail closed |
| 008 | review-workbench | ✅ T1～T5/T7 已合入（PR #15）；W4/T6 follow-up 可认领 | 轨道 L2；018✅ 已解除整页/回滚前置；Owner 复审=A |
| 009 | concept-layer | 📋 历史规格已收口；当前不授权实施 | 旧迁移 0008 已撤号且不可复用；后续须按 033 Milestone 重新立项 |
| 010 | structured-import | ⚠️ T1～T4 历史范围已合入；旧续作路线撤销 | 已有能力不是当前生产证明；旧迁移 0007 已撤号且不可复用 |
| 011 | knowledge-health | 📋 历史规格已收口；当前不授权实施 | 旧迁移 0010 已撤号且不可复用；后续按修正案 Milestone C 重新立项 |
| 012 | qa-objects | 📋 历史规格已收口；当前不授权实施 | 旧迁移 0009 已撤号且不可复用；后续须按 033 Milestone 重新立项 |
| 013 | insurance-mcp | 📋 MVP core 可认领 | 先交付产品对齐/事实/证据与 snapshot/hash envelope；完整 compare/history 矩阵留 M2 |
| 014 | batch-orchestration | 📋 提案 | M3，暂不排 |
| 015 | feedback-flywheel | ✅ 已合入 main（PR #18） | 离线 trace→durable 飞轮；迁移 0012（三表单事务/Space 隔离）；Langfuse 直连与 ReviewItem 动作投影保持 gated |
| 016 | enterprise-knowledge-scope | ✅ 已交付 | |
| 017 | weknora-source-bridge | ✅ 软件交付；live NOT RUN | |
| 018 | release-snapshot-read-model | ✅ 已合入 main（PR #9，2026-07-17） | 独占迁移 0005 |
| 019 | golden-quality-gate | ✅ 已合入 main（PR #8） | |
| 020 | golden-v01-baseline-run | 🚧 13 产品 canonical admission BLOCKED；真实 D2～D4 未运行 | 企业 M2；不阻塞 030 的独立 23-entry 受控输入 MVP admission |
| 021 | source-lifecycle-ordering | ✅ 已合入 main（PR #23） | 迁移 0006，实际链 `0012 → 0006`；deterministic 1901，PG 25/skipped=0 |
| 022 | review-hardening | ✅ 已交付 | ⚠️ 编号冲突历史记录：与下行同号，两者均已合入，**目录不改名**，冲突就此冻结 |
| 022 | test-portfolio-rebalance | ✅ 已交付 | 同上 |
| 023 | local-weknora-live-environment | ✅ 已合入 main（PR #10） | 受信 live workflow |
| 024 | extraction-recall-uplift | ⚠️ 第一方软件范围已合入；真实收益未验证 | 028 可选择性复用；030 证明 MVP slice 效果，完整 020 验证留 M2 |
| 025 | merge-weak-value-guard | ⛔ 旧计划撤销 / history-only | 旧迁移 0011 已撤号且不可复用；后续须按 033 重新切片 |
| 026 | claim-data-quality-persistence | 🔒 已占号（目录未开） | `data_quality` 的 Claim/Revision/Snapshot/MCP 端到端字段+迁移+回填（12 号文档 #2 采纳项至今只在 pred 侧，主链未落——PR #11 四轮对账发现）；业务确需时立项，010/013 不预支承诺 |
| 027 | production-weak-model-boundary | ✅ 已合入；能力保留 | 历史交付能力，不再作为旧 Wave 路线状态源；后续由 033 DAG 消费 |
| 028 | template-compilation-runtime-mvp | ⛔ superseded / history-only | 旧 PR28/runtime 路线不得继续实现、重放或作为生产 authority |
| 029 | release-manifest-approval-mvp | ⛔ superseded / history-only | 历史规格仅供审计；由 033 后续 Release/Review 小 PR 重新交付 |
| 030 | enterprise-wiki-mvp-slice | ✅ 已合入；能力保留 | 历史交付能力，不再作为旧 Wave 路线状态源；后续由 033 DAG 消费 |
| 031 | operational-run-admission | ⛔ superseded / history-only | 旧 runtime/PR 路线冻结，不更新、不重放、不授予生产 authority |
| 032 | human-wiki-reader-mvp | ⛔ superseded / history-only | 历史规格仅供审计；后续消费面按 033 Milestone 重建 |
| 033 | production-architecture-reset | ✅ D0 已合入；Amendment 2 / Mission 0 治理修订进行中 | 当前治理入口；服务中的唯一 Active authority 改为 WeKnora，旧 Postgres Active→Outbox→Projector 发布链已被 Amendment 2 取代；不是迁移号 |
| 034 | c0-canonical-envelope | ✅ 已实现并合入（PR #36） | 033 §16 C0；纯 Python 包，无迁移 |
| 035 | p1-job-outbox | ✅ 已实现并合入（规格 PR #38；实现 PR #53） | 旧 PR #44 保持 `CLOSED / ARCHIVED / NOT MERGED`；迁移 0015；5 条非阻断 follow-up 归 042 |
| 036 | capacity-contract | ✅ 已实现并合入（PR #46） | CAP0；CapacityProfile 合同已交付，八项 launch 问卷仍待业务确认；不是迁移号 |
| 037 | weknora-revision-contract-spike | ✅ 已执行并合入（PR #40）；双合同 `insufficient` | W0；已触发 W1（038），只读 spike，不是迁移号 |
| 038 | w1-weknora-revision-manifest | ✅ 源码已实现并合入（规格 PR #41；实现 PR #55） | local-live 仍锁 `5eefa70e` 且不含 W1；项目 `000066` 与 upstream v0.7.1 `000066` 冲突，runtime adoption 须独立 Mission 闭合 |
| 039 | p3-api-worker-shell | ✅ 已实现并合入（规格 PR #48；实现 PR #58） | 033 §16 P3；零 Harness migration；下一项仅为 043 所需的最小 ACL-inspection authority |
| 040 | g0a-golden-asset-kernel | 规格 ✅ 已合入（PR #42）；`SPEC-ONLY / IMPLEMENTATION NOT STARTED` | 编号冲突已关闭；后续实现须独立 TDD/复审，不得称 G0a 已验收或产品已完成 |
| 041 | p5a0-product-version-resolver | ✅ 已合入 main（PR #56） | ⚠️ 该目录先于注册表行创建（占号规则被绕过），此行为事后补记；后续窗口一律先占号再开目录 |
| 042 | p1-followup-backlog | 🔒 已占号（目录未开，比照 026 惯例） | 035 四轮评审的 5 条 BACKLOG，完整清单含 live 证据与建议修法见 [23 号 §8 D-2026-07-27-19](../../docs/insurance-kb/23-mvp-control-board.md)；预期零迁移；**开工前须取 Mission Card 批准并按正式 delta 格式建目录** |
| 043 | p2d-space-security-boundary | `SPEC-ONLY / REQUIRES AMENDMENT AFTER S0-R` | 保留 Space/principal/epoch/ACL、跨 Space 拒绝与失败零写；`wiki_projector`、旧投影和新 Release principal/binding 协议不得原样复用；实现预留迁移 0016 |
| 044 | p1-read-only-active-fence-verifier | ✅ 已实现并合入（PR #59） | P1 零迁移 follow-up；只读 current row + DB clock 验证 Space/job/generation/running/attempt/unexpired lease；不续租、不推进状态、不写 Outbox |
| 045 | weknora-80a5003-continuous-adoption | 🚧 Source + bridge + trusted images + digest pin complete；Full Artifact probes open | 上游能力基线 `80a5003`；镜像构建源码 `a8bf55ae...`；当前主线 `529d72c...`；固定 digest 已落地，但 Full Artifact/W1 runtime probes 尚未闭合 |
| 046 | weknora-release-capability-falsification | 第一轮 `RELEASE_PATH_NOT_FEASIBLE`（PR #70） | 冻结十路径预算缺少真实生产路由入口；零功能/测试/migration 实现，载体是否可行仍待 048 窄修订复验 |
| 047 | s0q-quality-feasibility | `SPEC + MISSION CARD / BLOCKED_ON_INPUT` | 缺少真实冻结的 WeKnora/W1 parsed artifact 输入；不得用人工清洗 Markdown 代替 |
| 048 | s0r-router-budget-amendment | `SPEC-ONLY / IMPLEMENTATION NOT STARTED` | 只为 S0-R 增加 `internal/router/router.go`，总路径上限 11；其余预算不变 |
| 049 | s0q-full-golden-freeze | ✅ 具名人工已批准；S0-Q frozen full Golden 可用；Draft 交付待定 | 复用现有 Golden 系统；`gpt-5.6-sol` 对 596-1 全部 60 个当前可抽取字段完成双 blind pass、Evidence 回验和 exact-hash 批准；只供 S0-Q，不是生产或 machine_auto authority |
| 050 | postgres-embeddings-forward-repair | ✅ 已实现并合入 main（PR #78） | 修复 official ledger 已推进但 PostgreSQL retrieval 的 `embeddings` 表缺失；仅新增 enterprise forward migration，未重跑 PDF、模型或历史 migration |
| 051 | enterprise-knowledge-compiler-architecture | ✅ 已合入 main（PR #79） | 父级知识编译合同；只冻结 A→C→B→{D,E}→F→G，不实现 parser/provider/runtime/migration |
| 052 | material-profile-template-binding | ✅ 已合入 main（PR #80） | ProductVersion 596-1 三 PDF 的薄 MaterialProfile 绑定层；含 parser-neutral default + 至多一次 bounded upgrade policy，复用现有 TemplatePackage resolver，零 migration |
| 053 | parsed-document-contract | ✅ 已合入 main（PR #82） | Parser-neutral ParsedDocument/ParseManifest 与质量门合同；零 parser/provider/DB/WeKnora 写 |
| 054 | extraction-task-attempt-receipt | ✅ 已合入 main（PR #84） | Durable ExtractionTask/Attempt/Receipt 与一次定点 repair 合同；零 provider/live |
| 055 | weknora-sensitive-log-redaction | ✅ 已合入 main（PR #81） | GORM 慢 SQL 与失败 SQL 参数脱敏；零 migration/provider/live |
| 056 | native-pdfplumber-parsed-document-adapter | ✅ 已合入 main（PR #83） | native/pdfplumber 原生事实薄适配；缺失结构显式 unsupported，不做 OCR/VLM fallback |
| 057 | extraction-evidence-verifier-targeted-repair | ✅ 已合入 main（PR #85） | 051 Child D2；确定性 Evidence/业务规则回验与最多一次失败字段 targeted repair；直接绑定 054 exact receipt DTO |
| 058 | incremental-changeset-conflict-retraction | ✅ 已合入 main（PR #86） | 051 Child E；纯确定性 affected-only ChangeSet draft、字段级来源权威、冲突与独占支持撤回；零 migration/DB/provider/Release |
| 059 | fixture-candidate-human-batch | ✅ 已合入 main | 051 Child F 的 PR1；直接消费 058 public contract，仅 fixture Candidate + human_batch envelope，PR2 才拥有 CAS activate/pinned/revert |
| 060 | mineru-cloud-native-parsed-document-adapter | ✅ 已合入 main（PR #88） | 保留 MinerU pipeline `content_list.json` 原生结构，经过 Go ReadResult 脱敏 sidecar 桥接到 053；provider/live=0 |
| 061 | 596-1-vertical-falsification | ✅ 已合入 main | exact 三 PDF / Schema60 的解析准入、双臂冻结与 Golden-blind 质量证伪；capture 工具不单独占用 OpenSpec 编号 |
| 062 | mineru-native-cross-page-falsification | ✅ 已合入 main（PR #92） | exact two-document native middle.json fact projection；provider/live=0 |
| 063 | mineru-two-source-capture-runner | `DELIVERY IN PROGRESS / PROVIDER NOT RUN` | task-local exact terms→rate runner；只组合061/062 capture API，零retry/fallback |
| 064 | freeform-arm-evidence-binding | `IMPLEMENTATION IN PROGRESS` | 扩展 057：自由文本 field output 与 exact ParsedDocument/ParseManifest locator+quote 的可重放 binding receipt；语义正确性仍归 061 Golden scorer |
| 065 | release-proof-596-1 | 🚧 并行 Mission 进行中 | 由独立 Owner 交付，不与 067 共享写域 |
| 066 | 596-1-weak-strong-ceiling | `RED / BLOCKED ON 067` | 同一 MinerU artifact 上 DeepSeek V4 Flash 与离线 GPT-5.6-sol ceiling |
| 067 | 061-public-single-arm-golden-score | 🧊 STABLE CANDIDATE / REVIEW PENDING | 只公开已准入 MinerU 单臂对 exact 049 Golden 的确定性评分 seam |
| 068 | mineru-semantic-content-custody | ✅ 已随 PR #97 合入 | 060 native structure 的同次 semantic custody |
| 069 | 596-1-semantic-input-binding | 🚧 独立开发中 | 与 070 零共享写域 |
| 070 | golden18-human-gate | 🚧 实现中 | 596-1 Golden18 外部具名人工 decision/receipt 纯验证门 |
| 071 | offline-single-arm-raw-score | 🚧 implementation in progress | Strong-model single-arm results are descriptive `UNADMITTED_RAW`; no production or Release authority |
| 072 | five-field-source-authority-rebind | 🚧 独立开发中 | 仅纠正 strong blind 裁决确认的五个 task input source/material binding；零 provider/Golden/scorer 改动 |
| 073 | 596-1-exact8-field-contracts | 🚧 implementation in progress | 四项任务本地合同+四项用户决策权威阻断门；零 provider |
| 074 | fair-weak-strong-rerun-contract | 🚧 stacked implementation in progress | 依赖 PR #105/073；同一 3PDF/Schema60/task/prompt/budget/normalizer 的一次性双臂冻结门，零 provider |
| 075 | golden-v2-human-review-intake | 🧭 Mission 已批准 / 计划中 | 只消费原 P0-7 + P1-11 人工复核；决策齐全前不生成 v2，不运行模型 |
| 076 | candidate-wiki-member-manifest-compiler | 🧭 Mission 已批准 / 计划中 | Candidate/HumanBatch → deterministic Wiki pages/member manifest；零 provider/DB/WeKnora |
| 077 | release-human-review-dossier | 🧭 Mission 已批准 / 计划中 | Candidate/Evidence/ChangeSet → 只读 JSON+HTML 审核包；不得默认选择或自批 |
| 078 | 596-1-incremental-update-vertical | 🧭 Mission 已批准 / 计划中 | 合成 fixture 验证 affected-only enrich/supersede/conflict/retract；零 Golden/provider/Release |
| 079 | fair-experiment-executable-bridge | ✅ 实现与独立验证完成（PR #112） | 074 frozen pair → 066/071 scoring 前门；零 provider/Golden 值读取 |
| 080 | candidate-review-release-handoff | ✅ 实现与独立验证完成（PR #114） | Candidate → Review dossier → Release preparation 同身份纵切；零签名/激活 |
| 081 | golden18-xlsx-import-bridge | ✅ 实现与独立验证完成（PR #113） | 当前人工复核包 → typed 18 项决策请求；空白保持 pending、零 Golden 写入 |
| 082 | mineru-capture-typed-failure | ✅ 已由 PR #117 吸收并验证；Draft PR #115 已关闭 | MinerU capture 固定阶段失败码；真实闭环无重试/无 fallback |
| 083 | mineru-capture-custody-intake | ✅ 已由 PR #117 吸收并验证；Draft PR #116 已关闭 | exact Go capture bytes → immutable typed intake；零隐式 ADMIT |
| 086 | mineru-derived-cross-page-binding | ✅ 已整合并验证（PR #117） | 原生 marker 归并为有序关系集合；证据不足继续 fail closed |
| 087 | 596-1-private-artifact-admission-runner | ✅ 已整合并验证（PR #117） | 三份真实私有制品贯穿 Admission；终态 `COMPOSITION_SEAM_VERIFIED` |
| 089 | mineru-typed-cross-page-marker-provenance | ✅ 已整合并验证（PR #117） | 原生 cross-page / lines-deleted marker 保留路径与 custody |
| 091 | mineru-marker-evidence-custody-bridge | ✅ 已整合并验证（PR #117） | marker companion 进入同次 capture 与 083 bundle digest |
| 092 | 596-1-relation-bound-admission-integration | ✅ 已整合并验证（PR #117） | 有序关系集合进入 Admission；终态 `READY_FOR_QUALITY_FALSIFICATION` |
| 093 | cross-page-authority-compatibility-replay | ✅ 已整合并验证（PR #117） | authority/profile compatibility 离线回放，漂移即 fail closed |
| 094 | bounded-capture-to-admission-execution-wrapper | ✅ 已整合并验证（PR #117） | bounded capture → custody → relation → Admission 单次执行包装 |
| 095 | 087-actual-dependency-wiring | ✅ 已整合并验证（PR #117） | 087 私有 bytes 进入真实依赖链；不兼容时零部分输出 |
| 096 | 091-derived-relation-receipt-bridge | ✅ 已整合并验证（PR #117） | actual intake → derived binding → 私有 canonical receipt |
| 097 | 596-1-no-provider-full-synthetic-vertical-rehearsal | ✅ 已整合并验证（PR #117） | 无 provider 全链排练已完成，随后由真实三 PDF 闭环取代其交付门 |
| 098 | actual-marker-endpoint-pair-derivation-input-bridge | ✅ 已整合并验证（PR #117） | marker custody → endpoint-pair input；不从正文相似度推断结构 |
| 099 | bounded-real-capture-readiness-gate | ✅ 已整合并验证（PR #117） | bounded real capture 前门与 exact identity/custody gate |
| 100 | 096-private-receipt-092-authority-adapter | ✅ 已整合并验证（PR #117） | private receipt → exact Admission authority/profile/map inputs |
| 101 | marker-authority-envelope | ✅ 已整合并验证（PR #117） | verified marker custody → immutable authority envelope；无关系臆断 |
| 102 | 086-marker-preserving-intake-replay-seam | ✅ 已整合并验证（PR #117） | 083/091 marker custody replay compatibility；不改变关系算法 |
| 103 | terms-section-derived-endpoint-pair-input-bridge | ✅ 已整合并验证（PR #117） | 条款嵌套 marker 归并为真实 section endpoint pairs |
| 104 | marker-authority-readiness-wiring | ✅ 已整合并验证（PR #117） | public authority → endpoint replay → readiness evidence |
| 105 | dual-map-authority-actual-execution-wiring | ✅ 已整合并验证（PR #117） | 条款/表格关系映射进入 095/087 actual seam |
| 106 | mineru-native-section-anchor-evidence | ✅ 已整合并验证（PR #117） | 条款真实 ZIP 得到 3 个可复算 section-anchor relations |
| 107 | section-anchor-readiness-injection | ✅ 已整合并验证（PR #117） | section anchors 注入 103、Admission 与 087 链 |
| 108 | legacy-fixture-marker-envelope-compatibility | ✅ 已整合并验证（PR #117） | 旧 fixture 显式携带 canonical envelope；生产 gate 不放宽 |
| 109+ | 暂停新增外围 Mission | ⏸️ MVP 主航道收口 | 不再用微型 OpenSpec、adapter 或 synthetic 任务替代真实闭环 |
| 120 | schema-wiki-medical-596-1-mvp | MVP-ACCEPTED / C7 FLOW+UI PASS / C4 DEFERRED | 最终有效代码经 PR #123 以一个重建提交进入 main；既有 epoch2 纯 GET 重开完成 7 分类/67 字段、17/17 citation、三 PDF 与 exact authority。旧 R1、release/receipt/Head/75 members、五表和生产 8081 不变；DB/provider/model/C4/审批/签名/发布 effects 0 |
| 122 | schema67-golden-quality-gate | CODE-INTEGRATED / QUALITY-INCONCLUSIVE / HISTORY REFERENCE | `linyao` source Review COMPLETED；Schema67 `COMPLETE_67`（67/0，51保留+16合法 unknown）；旧 EC-02 真实结论 `QUALITY_FAIL` 且不在 main。后续 C4 从最新 main 新开 Mission，不继承旧 Candidate/reviewer/attestor |
| 123 | llm-first-candidate-resolution | 🚧 Mission 136 / LOCAL WORKTREE ONLY | 规则、模板和外部映射只生成候选；所有业务候选进入一次 LLM 语义裁决，再经过 Evidence/类型校验。禁止原项目推送、生产写入、真实 PDF 外发与 provider 调用 |
| 124 | nine-product-v5-extraction-evaluation | ✅ Mission 139 / LOCAL EVAL COMPLETED | 9 款/27 PDF/399 页/6 类 Schema 已完成；M139 记录 9 次 qwen-plus，材料支持口径 237/324，8091/5174 已验证；M137/M138 保留，零 DB/Release/Active/GitHub 写入 |
| 140 | coverage-summary-semantic-recall | ✅ Mission 140 / LOCAL EVAL COMPLETED | 三款/9 PDF/6 次 qwen-plus；`coverage_summary` 三款均 present，原三款有值字段未回退；M140 第一轮服务中，重跑文件单独保留；零 DB/Release/Active/GitHub 写入 |
| 141 | v5-value-guidance-normalization | ✅ Mission 141 / LOCAL EVAL COMPLETED | v5 取值说明编译为字段约束并接入 LLM prompt/回包归一化；三款/9 PDF/6 次 qwen-plus；present 116/221→121/221；M140 保留，零 DB/Release/Active/GitHub 写入 |
| 158 | business-seven-field-quality-closure | 🚧 Mission 158 / WIP | 六款 20 PDF 的七个业务重点字段专项闭环；长字段分片、有效 Evidence 子集、短字段联合校验和 30 条反馈独立验收；最多 32 次 qwen-plus，零 DB/Release/Active/GitHub 写入 |
| 160 | business-priority-field-completeness | 🚧 Mission 160 / LOCAL EVAL | 基于 M159 六款 20 PDF，强化等待期复合条件及缴费、权益、责任、免责、疾病定义字段的完整抽取与 Evidence 门禁；最多 32 次 qwen-plus，零 DB/Release/Active/GitHub 写入 |

## Alembic 迁移编号台账（harness/migrations/versions/）

| 号 | 归属 change | 状态 |
|---|---|---|
| 0001 | 003 product_domain | ✅ |
| 0002 | 007 knowledge_domain | ✅ |
| 0003 | 016 enterprise_knowledge_scope | ✅ |
| 0004 | 017 source_evidence_lineage | ✅ |
| 0005 | 018 release_snapshot_read_model | ✅（PR #9 已合入） |
| 0006 | 021 source-lifecycle-ordering | ✅ 已随 PR #23 合入；实际 down_revision=0012 |
| 0007 | 旧 010 structured-import 计划 | superseded / not reusable（D-2026-07-27-10） |
| 0008 | 旧 009 concept-layer 计划 | superseded / not reusable（D-2026-07-27-10） |
| 0009 | 旧 012 qa-objects 计划 | superseded / not reusable（D-2026-07-27-10） |
| 0010 | 旧 011 knowledge-health 计划 | superseded / not reusable（D-2026-07-27-10） |
| 0011 | 旧 025 merge-weak-value-guard 计划 | superseded / not reusable（D-2026-07-27-10） |
| 0012 | 015 feedback-flywheel（flywheel_checkpoints + flywheel_observations + knowledge_gaps） | ✅ 已随 PR #18 合入；down_revision=0005 |
| 0013 | 旧 029 计划 | superseded / not reusable；D0 不预占替代 migration |
| 0014 | 旧 028 runtime 计划 | superseded / not reusable；D0 不预占替代 migration |
| 0015 | 035 p1-job-outbox 实现 | ✅ 已随 PR #53 合入；`down_revision="0006"`，实际链 `0005 → 0012 → 0006 → 0015`，单 head |
| 0016 | 043 p2d-space-security-boundary | 🔒 已占号；SPEC-ONLY，migration 文件未创建；实现阻断于 P3 ACL inspection authority，未来 down_revision 必须指向实现时 main 的真实 single head |
| 0017+ | （空闲） | 先占号再开 migration |

> **迁移号≠链拓扑**：上表编号只是占号防撞（文件名/revision id 用它），
> **down_revision 链序由实际合入 main 的先后决定**，与数字大小无关。规则：
> 每个实现 PR 在最新 main 重放后，把自己的 down_revision 指向**当时 main 的
> 实际 head**；不允许产生 multi-head；合入后在本表“备注”记录实际链序。
> 数字顺序仅为可读性，不承载任何拓扑语义。

## 历史入口背景（2026-07-29 · Mission 0，`HISTORY-ONLY`）

当前唯一项目必读、贡献与 SDD 入口是仓库根目录的 [`AGENTS.md`](../../AGENTS.md)。
以下列表仅保留 2026-07 Mission 0 的历史审计上下文；不得绕过 `AGENTS.md` 的
当前阅读序列、适用 OpenSpec 或状态矩阵形成实现授权：

- [WeKnora sole serving Active authority ADR](../../docs/superpowers/specs/2026-07-29-weknora-sole-serving-active-release-authority-adr.md)；
- [Enterprise LLM Wiki Authority Amendment 2](../../docs/superpowers/specs/2026-07-29-enterprise-llm-wiki-authority-amendment-2.md)；
- [V3 完整设计](../../jlx_enterprise_llm_wiki_complete_728_v3.md)；
- [V3 MVP handoff](../../mvp_handoff_jlx.md)；
- [OpenSpec 033](033-production-architecture-reset/)；
- [实时状态与决策板](../../docs/insurance-kb/23-mvp-control-board.md)。

旧 2026-07-21/24 架构与 22 号并行蓝图只保留历史审计价值；凡与
Amendment 2 冲突的 Postgres Active→Outbox→Projector serving authority
均不再授权执行。当前唯一主航道为先完成 S0-R/S0-Q 证伪，再按需改接第一条
真实纵切；不得按 PR 数量推断 MVP 已上线。

045 的精确身份必须分层表达：上游功能基线为
`80a5003cc99a427098afe184eee6601916d3d156`；可信镜像构建源码为
`a8bf55ae18441abd380e594afba5000c51cc9633`（已包含 `80a5003`）；Mission 0
启动时项目主线为 `529d72c994369750b26e352a70fd6284e8b0fd9d`，其中包含后续
digest 固定与状态更新。当前运行身份以固定 digest 为准；Full Artifact/W1
runtime probes 仍未闭合，不能写成完整 runtime adoption 已验收。

PR custody（2026-07-28 状态同步前 open PR/issue 均为 `0`）：

- PR #53/#55/#56/#57/#58/#59 均已合入；其中 #57 只交付 043 规格，
  #42 仍只交付 G0a 规格，均不得冒充对应实现已完成。
- 旧 PR #44 已 `CLOSED / ARCHIVED / NOT MERGED`，annotated tag 为
  `archive/pr44-p1-job-outbox-20260727-a6cdc9ae`，**零代码合入**；批准的
  P1 内容由 PR #53 以独立 Git 身份重落地并已合入。
- 旧 PR #26/#28/#33 已关闭，仅保留历史审计价值。
- 下一步只允许 S0-R 与 S0-Q 两条证伪 lane；双 PASS 后也只改接第一条真实纵切
  所调用的入口。P2d、P5a1、legacy 清理、通用 Release Kernel 与额外 migration
  均不得从 Mission 0 自动获得开工授权。

## SUPERSEDED / HISTORY-ONLY — NOT EXECUTABLE · 旧并行开工基线（2026-07-21）

> [!WARNING]
> 分类：`superseded / history-only`；**NOT EXECUTABLE**。以下 027/028/029/030/031/032、NS-0、030 admission 与 HANDOFF MVP-0 路线仅作历史审计，
> 不授予当前实现、迁移、运行、提交或合入权限，不得据此开工或恢复旧分支。

- 北极星与 Integration-first MVP 已批准；总体规划窗口先补齐 027～030、032 的正式 proposal/specs/tasks 和实现 plans，再交独立执行会话；
- `NS-RIGHTS=recorded`：LLM-wiki-black 是项目方第一方资产，可按 provenance + OpenSpec 选择性迁移；第三方许可证另行清点；
- 027 未 verified 前，现有强 judge/fallback/未知模型与任何真实生产编译、merge、release 入口 fail closed；
- 030 MVP admission READY 后只允许运行其 23-entry 受控输入 slice；不修改也不借用 020 canonical BLOCKED 的授权状态；
- S/K/M/I 的文件域、串行 migration lane 和合入顺序见 22；实时状态只在 HANDOFF MVP-0 控制板维护；
- 025、完整 010/013/008、020 D2～D4、P-1、011/014/015 均后置；032 只做独立只读消费面，不得顺手扩成审核或生产 Wiki UI。
