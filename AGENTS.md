# Enterprise LLM Wiki 项目必读与贡献规范

> 本文件是仓库唯一的项目必读、贡献与 SDD 流程入口。`README.md`、
> `CLAUDE.md`、`HANDOFF.md` 和 OpenSpec 注册表只能链接到这里，不得复制或
> 改写本文件的流程规则。`HANDOFF.md` 只记录运行/交接状态；适用 OpenSpec
> 只记录某个 Goal 的 Requirement 与验证事实。

本仓库的产品本体是 **Enterprise LLM Wiki**。WeKnora 提供企业平台、权限、
上传、解析、检索和 Wiki 载体；Python Harness 负责寿险语义编译、治理、
Candidate、审核与发布授权。正式线上知识只有一个 serving Active Release
authority；当前条件接受 WeKnora 承载该 Active Head。Harness 不保存第二个
serving Head，旧 PostgreSQL `current_release`/ReleaseSnapshot/publisher 链只作
冻结审计，不构成当前实现授权。

## 当前生效：本地独立开发模式

本仓库当前仅作为独立的本地开发与测试版本，不再作为原 GitHub 仓库的交付
lane。本节优先于下文所有 Mission Card、OpenSpec、SDD、PR、clean worktree、
review/integration 与 GitHub 门禁描述：

- 用户要求范围内的本地源码、配置、测试和文档修改可以直接实施并验证；不要求
  先建 Mission Card、OpenSpec、Requirement ID、RED 证据、PR 或逐项批准。
- 允许在当前工作区工作，但必须保留并兼容用户已有的未提交修改；测试规模按
  风险决定，SDD/Goal/验证矩阵仅在用户明确要求时创建。
- 默认不得向原 `origin` 或其他远程仓库执行 `push`、创建/更新 PR、merge，或
  改写远程状态。以后如需恢复远程交付，必须由用户对 exact remote 和动作另行
  明确授权，届时才重新启用下文的上游交付流程。
- 本地开发授权不扩展为生产数据库写入、migration/backfill、部署、发布、激活、
  破坏性操作，或会付费/传送业务数据的外部 provider 调用；这些动作仍需单独
  明确授权。
- 下文的产品架构、安全不变量与 serving authority 约束继续有效；仅流程门禁在
  本地独立开发模式下停用。

## 上游交付参考阅读序列（当前非门禁）

仅当用户明确恢复原仓库的上游交付流程时，才按以下顺序阅读：

1. 830 任务先读 `jlx_enterprise_llm_wiki_technical_blueprint_830.md`、
   `docs/insurance-kb/28-development-execution-charter-830.md` 与
   `docs/insurance-kb/29-goal-cards-830.md`；非 830 任务跳过本项
2. `docs/superpowers/specs/2026-07-29-weknora-sole-serving-active-release-authority-adr.md`
3. `docs/superpowers/specs/2026-07-29-enterprise-llm-wiki-authority-amendment-2.md`
4. `jlx_enterprise_llm_wiki_complete_728_v3.md` 的 `§M0` 与当前任务相关章节；
   只有总体架构评审才要求阅读全文
5. `HANDOFF.md` 的最顶部当前状态块
6. 对应的 `openspec/changes/<NNN>/`；B0 是已授权的证据冻结/资产裁决，不新建
   OpenSpec，也不授权产品实现

`CLAUDE.md` 不再维护另一份必读清单；其他开发入口必须指回本节。

## 上游交付 SDD 流程（当前停用）

以下队列只适用于用户明确恢复的上游/正式交付，不是本地开发的前置条件：

1. `Goal`：记录业务目标、唯一 Owner、范围、非目标和 STOP 条件；需要外部写入
   或新授权时先取得 Mission Card 批准。
2. `OpenSpec`：先占号并冻结适用 OpenSpec；每项 Requirement 使用稳定 ID。
3. `RED`：为每个 Requirement 记录能在旧实现上失败的最小测试/检查；环境错误
   和缺依赖不得冒充 RED。
4. `Implementation`：仅修改 Owner matrix 中的路径；跨 Owner 或范围扩张立即
   `BLOCKER`，回到 OpenSpec/计划修订。
5. `Validation`：建立 `Requirement → implementation → test → commit → status`
   矩阵；状态只能是 `PASS | BLOCKED | NOT RUN`，fixture/provider-zero 不得冒充
   真实业务效果。
6. `Deployment`：代码 GREEN 不等于已部署。migration、backfill、provider、
   Candidate、Draft、review、publish、activation、live probe 均须逐项写
   `PASS/BLOCKED/NOT RUN`，未执行不得推断为成功。
7. `Review/Integration`：独立 reviewer 只复核冻结 identity；唯一 integration
   Owner 在 CI 与矩阵闭合后才可合入。不得从 review lane 顺手改生产。

### 豁免

仅纯只读事实核验、审查、监控，或已批准 Goal 内不改变行为的正常验证可以免于
新建 Mission Card/OpenSpec。机械文档/格式修正可以免 RED，但必须在 PR 中写明
豁免理由、精确路径、适用 Requirement ID（若有）及 Reviewer 明确确认。豁免
不能授权 production、migration、provider、DB、deployment 或外部写入。

### 队列与角色

- `Owner`：唯一写者，维护 `CURRENT / BLOCKER / NEXT_READY / TERMINAL`，当前项
  完成后自动进入已批准的下一项。
- `Reviewer`：只读、基于冻结 commit/tree/index 审查；只输出
  `BLOCKER / BACKLOG / REJECTED`，不得形成第二写 lane。
- `Integration Owner`：只负责已批准的机械集成、CI 与最终 identity；不得扩大
  Requirement 或替各 lane 设计新协议。
- `Deployment Executor`：只在单独授权窗口按 runbook 执行，失败即 STOP 并保留
  部分回执；不得把本地/fixture 结果写成 live 事实。

### 状态分层

- `SPEC`：Requirement 已冻结，未说明代码或部署完成。
- `CODE`：实现和 bounded tests 已闭合，未说明真实 provider/DB/live 已执行。
- `DELIVERY`：构建、迁移、配置、部署与 live 回执各自独立记账。
- `BUSINESS`：真实 Candidate/Golden/Review/Active 等业务结果；不得由 fixture、
  provider-zero、代码 GREEN 或容器停止状态推导。

`DELIVERY` 必须再拆成以下六个互不替代的观测维度，每个维度只允许
`PASS | BLOCKED | NOT RUN`，并绑定自己的 identity/receipt：

1. `software`：源码、local build 与 bounded tests；不得包含远端 CI，也不得推导
   镜像或 live 状态。
2. `container health`：exact image/container 的进程与健康；不得由 CI 或宿主端口推导。
3. `provider probe`：exact provider/model/endpoint 的受控调用；provider-zero 只能记
   `NOT RUN`，不得推导语义效果。
4. `provisioning`：migration、配置、public-key rings、backfill 与部署前置；代码中
   存在实现不等于已 provision。
5. `local live`：本地/Colima exact runtime 的实时观察；runtime 停止只能记
   `NOT RUN`，不得写成应用失败。
6. `GitHub live`：GitHub Actions CI、environment/deployment 与远端回执；本地
   software GREEN 不得推导 GitHub live，GitHub CI 也不得推导本地 live。

六个维度之间禁止横向推断；只有各自证据才能改变该维度状态。

### 当前 120/122 状态

截至 2026-08-31，MVP-815 最终有效代码已由 PR #123 以单个重建提交
`ef47bee2b93d6a9cb4511133deaef6e700d915ce` 进入 main，未合入或整体 squash
149 条历史迭代提交。OpenSpec 120 的既有 epoch2 纯 GET C7 已完成 FLOW/UI、
7 分类/67 字段、17/17 citation 与三 PDF 验收；旧 R1、release/receipt/Head/
75 members、五表与生产 8081 不变，DB/provider/model/C4/审批/签名/发布 effects
均为 0。精确源码/tree/制品/回执身份见 `HANDOFF.md` 与 OpenSpec 120
validation report。

OpenSpec 122 与旧 EC-02 只保留历史质量证据；旧实验结论是 `QUALITY_FAIL`，
不在 main。C4 定制仍为 `DEFERRED`，必须从执行时最新 main 新开 Mission，重新
冻结 Candidate/Golden/Evidence、Metric、人工责任、provider/model 与预算；不得
从 C7 PASS 推导 C4 PASS，也不得修改已验收 serving release。

### 当前 830 B0 状态

830 当前唯一 WIP 是 `B0`，正式 base 为
`99205db986eae2a9fa4bc956c053b94298d0b114`，执行分支为
`codex/830-b0-asset-baseline`。B0 只冻结 815 FLOW 证据、11 类 Schema v5 输入、
有限候选四态裁决、验证/镜像影响和 branch/worktree 机械索引；产品代码、Provider、
环境、Docker 与 G1+ 均未获授权。Evidence Pack 位于
`docs/insurance-kb/evidence/830-b0/`，状态为
`EVIDENCE_FROZEN_PENDING_CONTROLLER_REVIEW`；总控复核前不得宣布 B0 最终 PASS，
G1 及后续 Goal 保持 `LOCKED`。下文 C4 描述只保留历史边界，不是当前下一项队列。

2026-07-24 生产架构设计与 2026-07-21 北极星继续保留产品、Evidence、Conflict、
弱模型、Candidate 批审和过程护栏，但其 PostgreSQL serving authority、
P11/P12 Projector 与 fenced projection 执行方向已经 superseded。

历史 Mission 0 顺序（仅作架构背景，不是当前任务队列）：

```text
Mission 0
├── 80a5003 Release capability gap matrix → S0-R
└── S0-Q 立即并行
           ↓
S0-R PASS AND S0-Q PASS
           ↓
MVP 纵向闭环；legacy 仅按需改接，物理清理后置
```

S0-R 是输入就绪后的两工作日证伪窗口，不是生产 Kernel 交付承诺；S0-Q 必须
消费 WeKnora/W1 冻结解析制品，禁止人工清洗 Markdown。MVP profile 暂定
`1 Space = 1 RAW KB + 1 release-managed Wiki KB`，不是永久企业不变量。
OpenSpec 043 为 `SPEC-ONLY / REQUIRES AMENDMENT AFTER S0-R`，不得按旧
`wiki_projector` 语义原样实现。

## 上游 MVP 主航道协作（当前停用）

仅当用户明确恢复原 GitHub 仓库交付时，本节流程才生效。届时由 Owner 向用户
提交 **Mission Card** 并取得逐项批准。Mission Card 至少包含：

- 业务目标与现在做的理由；
- 唯一写 Owner、执行模型与 reasoning effort；
- 依赖、预计 PR 数、预计周期；
- exact 验收条件、明确非目标；
- 阻断问题定义。

纯只读事实核验、审查、监控，以及已批准任务内的正常验证，无需另开 Mission
Card；这些例外不得被扩大为写入或外部状态变更授权。未获批准不得写实现、迁移
或功能规格。GitHub 上已有分支、PR、旧测试或历史现场不构成开工授权；W1、
P1、G0a 等后续功能仍须各自取得 Mission Card 批准。

当前排期不包含 Claude。三个 Codex lane 采用“两个独立开发 lane + 一个动态
review/integration lane”，角色按任务轮换。review lane 空档只执行用户已批准
的任务或只读准备，不固定等待。跨 agent 必须有唯一写 Owner；每项工作从最新
`origin/main` 的独立 clean worktree 开始，不得并发写同一文件域。

默认执行模型为 `gpt-5.6-sol high`。只有数据丢失、安全、权限、迁移、真实并发、
跨模块最终审查等高风险任务使用 `xhigh`。`max`/`ultra` 不得作为默认值，必须
由用户单独批准，并提供代表性 eval 证明其收益。

Reviewer finding 只能归为：

- `BLOCKER`：可复现、在 Mission Card 范围内，并会造成明确验收失败、安全/
  权限缺陷、数据损坏或真实并发错误；
- `BACKLOG`：真实但不阻断当前用户价值，进入后续 Mission Card；
- `REJECTED`：不可复现、低概率假设、范围外重构，或 Tencent/WeKnora 上游
  通用问题。

普通 PR 最多一轮修复复审，高风险 PR 最多两轮。两轮后仍出现同域新的基础问题，
停止追加补丁，回到设计或拆分 PR。达到 Mission Card 验收且 CI 通过后及时合并，
不追求理论完美。一个 PR 只交付一个用户价值，默认应在 1–2 个工作日完成且
reviewer 可在 30 分钟内理解；超出时拆分，或重新取得用户批准。

上游交付硬门禁（当前本地开发不适用）：

- 恢复上游交付后，没有 OpenSpec 不写功能代码，先测试后实现。AI 默认不
  commit/push；用户对指定 Mission 明确授权后，只有总控 AI 可在 exact
  identity、独立复审和门禁通过后执行 commit/push/PR/merge，开发与评审 lane
  不得自行执行。
- 生产只允许经批准、身份冻结的 MiniMax/Qwen/Qwen-VL 能力档弱模型；强模型
  只能用于隔离的离线标注或评测，不能成为生产依赖。
- ReviewPolicy 是按 Space 版本化配置，合法模式为
  `machine_auto | human_batch | hybrid | trusted_import`。任何自动资格缺失、
  漂移、撤销或安全阻断都确定性回落 `human_batch`；人工动作绑定完整
  CandidateRelease，而非逐页面操作。
- 新建 Space 的安全默认值必须是 `human_batch`。
- 生产 `machine_auto` 只有在 G0b 批准后，才能通过显式、版本化的
  ReviewPolicy binding 在其 exact AutomationScope 与 covered capabilities
  内启用；环境、调用者标签或隐式默认均无效。
- superadmin 只可对 exact CandidateRelease 执行一次性 ReviewDecision 动作；
  不得直接改 active pointer，也不得绕过完整性、Space ACL、
  Provenance/Attestation 或恶意内容与其他安全检查。
- 应用只回答 Active WikiRelease 中的已发布知识。原始资料只用于证据核查、
  审核和补编；缺少已发布知识时返回不足或请求补充条件。
- Harness 与 WeKnora 仅通过版本化 REST 和 Source lifecycle event 集成，不
  共享数据库、Redis/Asynq 或队列。MCP 仅是后续 Active Query 消费者适配器。
- WeKnora 新改动必须来自 S0-R capability gap、独立 OpenSpec/Mission Card
  和有界 patch budget；旧 P11/P12 Projector 编号不再自动授权，W1 只保留
  已交付合同。
- Wiki、Evidence、Conflict、版本、不可变 Release、回滚、当前 ACL 与单一
  serving Active Head 是生产闭环不可省略的合同。PostgreSQL Job Store/Outbox
  继续服务任务可靠性，但不得形成第二个 Release serving pointer。
- 第一方 `LLM-wiki-black` 资产只作为迁移来源；保险领域生产逻辑统一收敛到
  Python 3.12 Harness。第三方资产继续按各自许可证管理。

实施采用小 PR、单一领域不变量、strict TDD、独立复审。样本数量、worker 数和
文件数只来自版本化 CapacityProfile 或具体验收画像，不得写成产品硬上限。
总体规划会话维护 Roadmap、控制板、任务卡与验收，不写功能代码；执行会话按
独占文件域实现；评审会话只报告发现，修复退回原 Owner。
