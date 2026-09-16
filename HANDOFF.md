# HANDOFF — Enterprise LLM Wiki

> 当前运行/交接状态的唯一入口。贡献规则只以 [`AGENTS.md`](AGENTS.md) 为准；
> 规格和历史讨论分别留在适用 OpenSpec 与历史合订文档，不在这里重复。

## 0. Mission 160 当前状态（2026-09-15）

- `CURRENT`：M160 重点字段完整性代码与真实百炼复测已完成；独立结果为 `provider-run-m160-six-products-business-priority.json`，run=`v5-trial-d145de09d8cbefea`。
- `SOFTWARE`：完整 V5 测试 82 项通过（2 个环境/依赖 warning），M160 focused 2/2、M158 regression 9/9、严格 mypy、Ruff、compileall=`PASS`。
- `PREFLIGHT`：M159 基线 `133/143=93.01%`；新门禁识别 596 等待期缺 `start`、1828 缺 `within_wait_consequence`，会保留基线并要求重新抽取。
- `BUSINESS`：30 次 `qwen-plus` 调用覆盖 6 款产品；反馈评估 `6 RESOLVED / 3 PARTIAL / 3 UNRESOLVED / 18 NOT_SCORABLE`；材料支持总体 `133/143=93.01%`，不宣称全局召回提升。
- `MATERIALS`：预检仍计 390 scanned / 388 readable / 2 unreadable；596 的 60 页服务手册已恢复，2 页历史一页纸缺失保持 unreadable。
- `DELIVERY`：software=`PASS`；provider probe=`PASS`；local live=`PASS`；container health/provisioning/GitHub live=`NOT RUN`。无 Candidate、Draft、Release、Active 或 serving effect。
- `NEXT_READY`：等待业务评估本地 M160 预览；如需再次抽取，必须新建/批准后续 Mission，不把本次局部提升当作全局召回结论。
- `TERMINAL`：当前预览 `http://127.0.0.1:5174/v5-preview` 已读取 M160 artifact；一次 1828-1 长字段重试后仍不完整，已 fail-closed。详细记录见 `docs/insurance-kb/55-m160-business-priority-field-completeness.md`。

## 0. Mission 158 当前状态（2026-09-13）

- `CURRENT`：M158 代码与验收器已完成；Mission 159 使用修正后的 32 次微批次合同成功
  重跑六款，独立结果为 `provider-run-m159-six-products-business-quality.json`，run
  `v5-trial-b45293f71e3b0cd0`。失败的 M158 尝试没有伪装为结果。
- `BASELINE`：M157 六款 20 PDF，材料支持字段 `133/143=93.01%`；七字段 30 条反馈中
  保险责任候选被 Evidence 定位误杀、疾病定义超长截断、缴费方式和部分等待期/权益仍未闭合。
- `DELIVERY`：software=`PASS`（80 个 V5 测试、Ruff、严格 mypy、compileall；前端 7 个
  结果合同测试、2 个页面组件测试、`vue-tsc` 和生产构建通过）；provider probe=`PASS`
  （32/32 次，29 个主批次、3 次重试，0 次 429）；local live=`PASS`，8091 返回 exact
  M159 run，5174 已修正历史 18 次/单产品 4 次上限并成功解析 32 次、六款回执分布
  `6/3/3/3/8/9`。container health/provisioning/GitHub live=`NOT RUN`。
- `BUSINESS`：材料支持有值率保持 `133/143=93.01%`；38 个七字段中 5 个改值。业务
  30 条反馈为 `5 RESOLVED / 2 PARTIAL / 5 UNRESOLVED / 18 NOT_SCORABLE`；相对 M157
  机器可判项只新增解决 1828 等待期，不能宣称七字段已全部闭合。
- `NEXT_READY`：人工复核 1816 疾病定义/免责和 1828 保险责任扩展；继续处理 596 权益、
  1830 缴费方式/保险责任、5003 缴费方式/保险责任、1828 权益及疾病定义/免责。
- `TERMINAL`：前端 `http://127.0.0.1:5174/v5-preview`，后端
  `http://127.0.0.1:8091/v5-preview-api/provider-run`。适用 OpenSpec：
  `openspec/changes/158-business-seven-field-quality-closure/`。

## 0. Mission 157 当前状态（2026-09-11）

- `CURRENT`：七字段章节化抽取、主附险适用范围和 Evidence 唯一高置信重定位已完成
  代码与六款真实重跑。独立结果为 `provider-run-m157-six-products-quality.json`，run
  `v5-trial-1c12e53f0011f760`，M156 文件未覆盖。
- `RESULT`：20 份 PDF / 390 页（388 页可读），24/24 次 qwen-plus，接受 4 个值变化；
  材料支持抽取率保持 `133/143=93.01%`。1814/1816 附加险保单权益得到明确纠偏，
  1830/1828 责任免除的原子结构和覆盖有所改善。
- `QUALITY`：1816/1828 疾病定义和 596 质量补抽仍达到 32768 token 后截断；1828
  短字段批次有一次网络错误，全部保留 M156 基线。业务工作簿不是完整机器可读 Golden，
  `BUSINESS=BLOCKED`，不能宣称正式准确率。
- `PERFORMANCE`：端到端 1422.5 秒（约 23 分 43 秒）；PDF 解析 382.6 秒，Provider
  1018.7 秒。长字段截断抵消了解析提速，整体仅比 M156 快约 35 秒。
- `DELIVERY`：software/provider probe/local live=`PASS`；71 个 V5 测试、Ruff、M157
  mypy 通过；8091/5174 均返回 exact M157 run。container health/provisioning/GitHub
  live=`NOT RUN`。
- `NEXT_READY`：疾病定义按章节分片抽取、原子项确定性去重合并；其他免责的目录只作为
  召回入口，展开实际条款后再入值。不要提高单次输出上限或放宽 Evidence 审核。
- `TERMINAL`：前端 `http://127.0.0.1:5174/v5-preview`，后端
  `http://127.0.0.1:8091/v5-preview-api/provider-run`；详细记录见
  `docs/insurance-kb/52-m157-section-applicability-evidence.md`。

## 0. Mission 156 当前状态（2026-09-11）

- `CURRENT`：字段拓扑接线修复后的六款重跑已完成，结果为
  `provider-run-m156-six-products-seven-field-rerun.json`，run
  `v5-trial-b11a5d5e589ea20d`；首轮失败结果和 M155 均保留。
- `RESULT`：20 份 PDF / 390 页（388 页可读），追加 18/18 次 qwen-plus，15 次
  合格合同、3 次 typed contract failure、无 429。接受 6 处变化，其中 4 处改值、
  2 处只增强 Evidence。材料支持抽取率保持 `133/143=93.01%`。
- `QUALITY`：失能险缴费期限和等待期、重疾险缴费期限有明确提升；仍有 21 个字段
  提议因不完整或弱 Evidence 被拒。596 长责任字段、年金/寿险缴费组合、长篇责任
  免除/疾病定义和主附险权益适用性尚未闭合。`BUSINESS=BLOCKED`，不能宣称正式
  准确率。
- `PERFORMANCE`：端到端 1457.3 秒（约 24 分 17 秒），PDF 解析 600.9 秒，
  Provider 839.2 秒，超过 20 分钟目标；峰值产品/Provider 并发均为 4。
- `DELIVERY`：software/provider probe/local live=`PASS`；8091 与 5174 代理均返回
  exact rerun 和 6 款，页面 HTTP 200。container health/provisioning/GitHub live=
  `NOT RUN`。
- `NEXT_READY`：下一轮先做主险/附加险 applicability 判定，再把超长责任字段拆成
  原子项分页抽取和确定性合并；不应直接放宽审核。
- `TERMINAL`：前端 `http://127.0.0.1:5174/v5-preview`，后端
  `http://127.0.0.1:8091/v5-preview-api/provider-run`；详细记录见
  `docs/insurance-kb/51-m156-six-product-seven-field-rerun.md`。

## 0. Mission 155 当前状态（2026-09-10）

- `CURRENT`：M154 四路入口已完成八款真实重跑，独立结果为
  `provider-run-m155-eight-products-concurrent.json`，run
  `v5-trial-ef6326d0223e4a22`；M150/M152 未覆盖。
- `DELIVERY`：provider probe=`PASS`（16/18 次 qwen-plus，15 次成功，1 次字段合同
  错误后有界重试成功，0 次 429）；local live=`PASS`（8091/5174 返回同一 M155 run、
  8 款）；software=`PASS`；container health/provisioning/GitHub live=`NOT RUN`。
- `PERFORMANCE`：端到端 22 分 29.5 秒；材料解析 15 分 22.4 秒、规划 12.8 秒、
  Provider 6 分 54.0 秒、合并主结果 0.13 秒；峰值产品/Provider 并发均为 4。相比 M152
  约 20 分 46 秒串行 Provider 窗口，模型阶段约快 3.0 倍；端到端主要瓶颈是全页表格解析。
- `BUSINESS`：`REVIEW_REQUIRED`。材料支持口径 `172/185=92.97%`，已抽取 350 个，
  与 M152 合计持平；未进行新一轮人工 Golden 准确率复核，不能把该结果写成正式发布。
- `NEXT_READY`：页面可直接验收。若继续提速，应单独批准按字段需要延迟解析表格，
  并以候选召回不下降和抽取率不下降为硬验收。
- `TERMINAL`：前端 `http://127.0.0.1:5174/v5-preview`；后端
  `http://127.0.0.1:8091/v5-preview-api/provider-run`；详细记录见
  `docs/insurance-kb/50-m155-eight-product-concurrent-run.md`。

## 0. Mission 154 当前状态（2026-09-10）

- `CURRENT`：四路产品级并发已接入 M152 实际运行入口；同产品批次串行、独立
  Provider client、全局原子调用预算、稳定顺序合并及 429 的 4→2→1 降级均已实现。
- `DELIVERY`：software=`PASS`（6 项 M154、18 项 M152-M154 定向、全部 55 项 V5
  测试、Ruff、M154 strict mypy、compileall）；provider probe、container health、
  provisioning、local live、GitHub live=`NOT RUN`。
- `SAFEGUARD`：Schema、Prompt、Evidence 和 M153 回归审核逻辑冻结；候选/上下文在
  并发前构建，线程只读；调用失败也占预算，重试不会挤占未开始批次的首轮预算。
- `PERFORMANCE`：本地 8 产品×3 等延迟批次模拟由 1.217 秒降到 0.307 秒，约 3.96
  倍；这不是百炼真实耗时。真实运行会在 audit `performance` 中记录四阶段、每产品、
  每调用等待/耗时、峰值并发和降级事件。
- `KNOWN_LIMIT`：Windows 全仓 pytest 仍被既有 Unix `fcntl` 阻断；M152 全依赖 mypy
  仍会看到 OCR/取值模块 3 个既有类型问题。本 Mission 未扩大范围修复。
- `BUSINESS`：`NOT RUN`。未外发材料、未调用百炼，当前 8091/5174 数据未更新。
- `NEXT_READY`：取得单独 Provider 授权后，使用 `--max-product-concurrency 4` 重跑，
  对比 M152 约 20.76 分钟有效 Provider 窗口和新 audit 的完整总耗时。
- `TERMINAL`：实现见 `m154_concurrency.py` 与 `m152_gapfill.py`；说明见
  `docs/insurance-kb/49-m154-four-product-concurrency.md`。

## 0. Mission 153 当前状态（2026-09-10）

- `CURRENT`：业务问题纠偏、表格感知和单次运行复用已完成本地实现。四份业务问题
  表共保留 49 条记录，其中 47 条映射到 v5 字段、2 条显式保留为 Schema gap；18 个
  嵌入图片资产只保存 SHA，不冒充已确认标准答案。
- `DELIVERY`：software=`PASS`（9 项 M153、25 项定向回归、全部 49 项 V5 测试、
  Ruff、M152/M153 strict mypy、compileall）；provider probe、container health、provisioning、local live、GitHub
  live=`NOT RUN`。全量 pytest 在 Windows 被仓库已有 `fcntl` 缺失和 pytest 临时目录
  权限阻断。
- `SAFEGUARD`：候选变 unknown、Evidence 变弱、缺必含事实、出现禁含事实或不满足
  允许值时不会覆盖基线；纯显示问题不触发重抽；业务标准不进入模型 Prompt。
- `PERFORMANCE`：PDF 同次打开抽文本与表格；候选和上下文只在本次进程内复用；费率
  表结构只路由给金额、缴费、领取、费率和减保相关字段，不做持久化缓存。
- `BUSINESS`：`NOT RUN`。本轮未外发材料、未调用模型，不能宣称抽取率、准确率或
  真实耗时已经提高。
- `NEXT_READY`：单独批准后，用同一冻结产品做一次 provider A/B，输出字段级
  before/candidate/decision/after 审计和表格字段耗时；优先确认 18 张业务截图中的标准。
- `TERMINAL`：实现见 `harness/src/insurance_harness/v5_preview/m153_quality.py` 和
  `m152_gapfill.py`；说明见 `docs/insurance-kb/48-m153-business-quality-table-performance.md`。

## 0. Mission 152 当前状态（2026-09-09）

- `CURRENT`：八款产品字段级动态补抽已完成。M150 基线共 328 个 present，本轮结果为
  350 个，新增 22 个；材料支持口径为 `172/185=92.97%`。
- `DELIVERY`：software、provider probe、local live=`PASS`；最终 artifact 有 15 次有效
  qwen-plus 回执，连同前序失败过程按保守口径合计 18/18 次。container health、
  provisioning、GitHub live=`NOT RUN`。
- `BUSINESS`：`BLOCKED`。缺失字段补抽完成，但已有错误/不完整字段的 review sidecar
  在主结果写入后校验失败，完整 before/proposed/diff 未保留；不能宣称这些旧值已修正，
  也不能用 Evidence 定位率代替人工准确率。
- `SAFEGUARD`：5 个缺少可靠依据的 `absent_explicitly` 提议已回退为 `unknown`；不会为
  提高抽取率把“没找到”写成“明确没有”。
- `NEXT_READY`：如继续，只重跑业务问题表中的已有值复核任务并生成审计侧车；不需要再
  全量补抽八款 unknown。
- `TERMINAL`：主结果为 `provider-run-m152-eight-products-gapfill.json`，run
  `v5-trial-7a6372c9c5d8818e`；本地预览为 `http://127.0.0.1:5174/v5-preview`；详细结果见
  `docs/insurance-kb/47-m152-eight-product-dynamic-gapfill.md`。

## 0. Mission 151 当前状态（2026-09-09）

- `CURRENT`：字段全材料候选召回与动态补抽上下文升级已完成本地实现。普通抽取和
  M148 动态补抽共用可插拔 `FieldCandidateRetriever`；默认实现扫描产品版本全部
  已解析页，并保留文档、页码、字符位置和命中原因。
- `DELIVERY`：software=`PASS`（6 项 M151、全部 9 个 V5 测试文件共 37 项、Ruff、
  strict Mypy、compileall）；provider probe、container health、provisioning、
  local live、GitHub live 均=`NOT RUN`。
- `OFFLINE QUALITY`：`E:\wiki badcase ly` 中 11 个直接“未抽取”字段，其支持段落
  均进入各字段 Top 5，候选召回 `11/11`。该数字不是实际字段抽取率。
- `BUSINESS`：`NOT RUN`。没有外发材料、调用外部模型、重跑产品、写生产数据库或
  形成 Candidate/Release/Active。
- `NEXT_READY`：另行批准后，只对这 11 个 `unknown` 字段执行动态补抽，分开统计
  候选命中、模型填充、Evidence 验证和最终准确性；不需要整产品重跑。
- `TERMINAL`：Mission 151 本地代码与离线候选验收完成；详细结果见
  `docs/insurance-kb/46-m151-field-semantic-retrieval-gapfill.md`。

## 0. Mission 150 当前状态（2026-09-08）

- `CURRENT`：Mission 150 已批准，目标是在 M149 六款本地预览中追加两款重疾险：
  1828 `平安安佑福（全能版）重大疾病保险`、L2332 `平安个人重大疾病保险`。
- `边界`：6 份冻结 PDF、最多 6 次百炼 `qwen-plus`；独立结果和合并预览均写当前
  worktree；不覆盖 M149，不写生产 DB/Candidate/Release/Active，不提交或推送 GitHub。
- `CURRENT_RED`：已闭合；旧注册表先失败，接入后定向测试通过。
- `DELIVERY`：provider PASS（4/6 次）；local live PASS（8091/5174 返回 8 款、7 类）；software PASS；provisioning/container health/GitHub live 均 NOT RUN。
- `BUSINESS`：两款均生成合法 Preview，但均为 `REVIEW_REQUIRED`；材料支持条件下抽取率为 1828=78.26%、L2332=100%。未创建 Candidate/Release/Active。
- `NEXT`：重疾险字段逐项人工复核或另开补抽 Mission；本卡不再追加 provider 调用。
- `TERMINAL`：Mission 150 本地交付完成，完整结果见 `docs/insurance-kb/41-m150-two-serious-illness-products.md`。

## 0.1. Mission 149 当前状态（历史交接）

- `CURRENT`：新增年金险 1830、意外险 1814、失能收入损失保险 1816 已完成试跑，
  并与 M146 原三款组成六款、六险种本地预览；原 M146 artifact 未覆盖。
- `DELIVERY`：software=`PASS`（组合 artifact 合同校验、6 项定向测试）；provider
  probe=`PASS`（新增 3 款 9 份 PDF，6/6 次 qwen-plus）；local live=`PASS`（8091
  和 5174 均返回六款）。container health、provisioning、GitHub live=`NOT RUN`。
- `BUSINESS`：仅形成 6 个本地 `REVIEW_REQUIRED` Preview；新增三款材料支持口径
  `57/65=87.69%`，六款合计 `126/145=86.90%`。未写生产 DB，没有 Candidate、
  Release、Active 或 GitHub 变更。
- `BLOCKER`：无。1830 第二次响应不完整，系统保留了第一次有效结果；新增三款仍有
  39 条 Evidence 未定位，不能据此宣称业务准确率。
- `NEXT_READY`：人工抽样核验新增三款的值与 Evidence；如继续优化，优先使用 M148
  字段级补抽处理 unknown 和 Evidence 未定位字段，不再全量重跑。
- `TERMINAL`：Mission 149 本地评估完成；适用 OpenSpec 为
  `149-six-insurance-class-local-preview`。

## 0. Mission 148 当前状态（2026-09-07）

- `CURRENT`：字段级半动态补抽/复核已完成本地代码实现。前端只发送产品版本、当前
  Preview hash、动作和字段 ID；后端负责候选片段、相邻页、全材料三层扩展，并返回
  Candidate、Evidence、before/proposed/after 差异和阶段回执。
- `DELIVERY`：software=`PASS`（30 个 V5 Python 测试、最终 7 项 M148 复跑、Ruff、Mypy、
  4 个前端测试、type-check、production build）；container health、provider probe、provisioning、local live、
  GitHub live=`NOT RUN`。
- `BUSINESS`：`NOT RUN`。本轮没有重跑三款产品，没有模型调用、PDF 外发、生产 DB、
  Candidate Review、Release 或 Active 变更。
- `BLOCKER`：真实 Provider 与产品材料 repository 尚未在 8091 runtime 绑定；因此本轮
  只能确认控制链和保值逻辑，不能宣称抽取率或准确率已经提高。
- `NEXT_READY`：单独冻结三产品与调用预算后，把材料 repository、qwen-plus executor
  注入 8091，执行字段级补抽并对比首轮/补抽后的材料支持抽取率与冲突率。
- `TERMINAL`：适用 OpenSpec 为 `148-dynamic-field-gapfill-control`；不提交或推送 GitHub。

## 0.1. Mission 146 当前状态（2026-09-03）

- `CURRENT`：596 服务权益补充材料已接入并完成三款真实 provider 验证；结果文件为
  `provider-run-m146-three-products-supplemental.json`，run=`v5-trial-62ef515559bba588`。
- `DELIVERY`：software、provider probe、local live=`PASS`；8091 和 5174 均返回
  M146 三款结果。provisioning、GitHub live=`NOT RUN`。
- `BUSINESS`：未写生产 DB，没有 Candidate/Release/Active 变更；2 份新增 PDF 仅归属
  596（60 页文本 + 2 页 OCR），6 次 `qwen-plus`、2 次 `qwen-vl-ocr`。596 新增
  `可享服务`、`增值服务`、`产品Q&A` 三个 present，固定基础字段口径为 `85/153=55.56%`。
- `BLOCKER`：三款仍为 `REVIEW_REQUIRED`；596 的服务字段部分 Evidence 仅为
  `NORMALIZED_MATCH`，`增值服务`当前不是完整服务目录。5003 持平，1826 净回退 4 个字段，
  说明 qwen-plus 仍有输出方差。
- `NEXT_READY`：拆分服务目录/次数条件/Q&A 字段级任务，清洗 OCR 版面和编码后做人工抽样；
  暂不单纯扩大调用预算。
- `TERMINAL`：本地服务 URL 为 `http://127.0.0.1:5174/v5-preview`；后端接口为
  `http://127.0.0.1:8091/v5-preview-api/provider-run`。

## 0.2. Mission 145 当前状态（2026-09-03）

- `CURRENT`：M144 内容总结 pass 已完成三款真实 provider 验证；结果文件为
  `provider-run-m144-three-products.json`，run=`v5-trial-38e10677cadec24d`。
- `DELIVERY`：software、provider probe、local live=`PASS`；8091 和 5174 均返回
  三款产品的 M144 结果。provisioning、GitHub live=`NOT RUN`。
- `BUSINESS`：没有写生产 DB，没有 Candidate/Release/Active 变更；本轮 3 款、9 份
  PDF、6 次 `qwen-plus`，材料支持口径为 `66/77=85.71%`。产品简介和产品概览
  均为 `present`（3/3）。
- `BLOCKER`：相同三款的 M143 基线为 `65/77=84.42%`，本轮加权提升 1.30 个百分点，
  但 5003 回落、1826 提升，事实字段仍有输出方差。596 第二次补抽因响应过长
  (`finish_reason=length`) 以 `LLM_RESULT_NOT_COMPLETE` 拒绝，首轮结果已保留。
- `NEXT_READY`：拆分简介/概览的定向短任务并做重复一致性评测；针对回退事实字段做
  证据定位，不直接扩大 provider 预算。
- `TERMINAL`：本地服务 URL 为 `http://127.0.0.1:5174/v5-preview`；后端接口为
  `http://127.0.0.1:8091/v5-preview-api/provider-run`。

## 0.3. Mission 143 当前状态（2026-09-03）

- `CURRENT`：M143 三字段全材料语义抽取已完成本地验证；结果文件为
  `provider-run-m143-five-products.json`，run=`v5-trial-d51edcaae8aa3e36`。
- `DELIVERY`：software、provider probe、local live=`PASS`；8091 和 5174 均返回
  五款产品的 M143 结果。provisioning、GitHub live=`NOT RUN`。
- `BUSINESS`：没有写生产 DB，没有 Candidate/Release/Active 变更；本轮 5 款、15 份 PDF、
  10 次 `qwen-plus`，材料支持口径为 `109/129=84.50%`。
- `BLOCKER`：与 M142 首三款单次基线相比，本轮为 `65/77=84.42%`，未证明整体召回率提升；
  596 持平，5003 和 1826 有回落。主要风险是长上下文下模型选择和二次结果合并的方差。
- `NEXT_READY`：先做同一产品的重复一致性评测和目标字段证据定位，再决定是否调整上下文切片或预算。
- `TERMINAL`：本地服务 URL 为 `http://127.0.0.1:5174/v5-preview`；后端接口为
  `http://127.0.0.1:8091/v5-preview-api/provider-run`。

## 0.4. Mission 144 当前状态（2026-09-03）

- `CURRENT`：产品简介/产品概览内容总结 pass 已完成代码实现；纯 LLM 字段在 unknown 时
  进入第二阶段，使用全材料有序上下文和已验证事实上下文。
- `DELIVERY`：software=`PASS`；provider probe、provisioning、local live、GitHub live
  均=`NOT RUN`。本轮未调用 provider，因此 8091/5174 仍展示 M143 artifact。
- `BLOCKER`：尚未有 M144 真实 provider 回执，不能提前宣称两个字段已生成或抽取率提升。
- `NEXT_READY`：按独立输出文件重跑产品，核对内容字段 Evidence 和事实字段回退情况。

## 1. 当前结论（2026-08-31）

**MVP-815 已完成代码交付与 C7 可见验收。** 正式代码已由
[PR #123](https://github.com/PA-ALG/InsuranceKB-WeKnora/pull/123) 以一个
squash commit 合入 `main`：

- MVP code commit（已在 main）：`ef47bee2b93d6a9cb4511133deaef6e700d915ce`；
- tree：`d868e8f2fd51250c71366c8c723f500482e7de44`；
- parent：`dfa87e11d5a434b6823582285c17498e715dd8f1`；
- 工程交接文档：[PR #124](https://github.com/PA-ALG/InsuranceKB-WeKnora/pull/124)；
- PR #124 合并后的最终 `origin/main` HEAD：
  `99205db986eae2a9fa4bc956c053b94298d0b114`；
- 交付方式：从当时最新 `origin/main` 重建最终状态，**未合入或整体 squash
  149 条历史迭代提交**；
- 远端门禁：两套 deterministic、两套 PostgreSQL integration、两套
  wheel-smoke 全部通过。

830 当前唯一 WIP 是 **B0 · 815 证据基线与资产裁决**。执行分支为
`codex/830-b0-asset-baseline`，正式 base 为上述 `origin/main` HEAD，Evidence Pack
位于 `docs/insurance-kb/evidence/830-b0/`，当前状态为
`EVIDENCE_FROZEN_PENDING_CONTROLLER_REVIEW`。B0 不改产品代码、不启动环境或
Docker；总控给出最终 B0 裁决前不得启动 G1，G1 及后续 Goal 全部 `LOCKED`。

## 2. 用户应体验什么

正式 MVP 入口知识库是 `medical-insurance-mvp`。进入“产品 Schema Wiki”后，
应看到：

- 产品：平安 e 生保（尊享版）医疗保险；
- 徽标：`当前 MVP · 只读`；
- `7 个分类 · 67 个字段`；
- 中文字段名为主标签，英文 `field_id` 仅作次级技术标识；
- 字段值保留 `present / absent_explicitly / unknown` 语义；
- 可从字段打开“原文来源”，切换来源并查看固定页码、框选与引文。

`C6-ISOLATED-R1-ACCEPTANCE-*` 是历史隔离验收库，不是产品入口。页面显示
“产品 Schema Wiki 暂不可用”是 fail-closed 状态，不能据此判断代码版本不存在。
整个页面不可用时先查 entry/serving 映射、唯一 Active Head/release members 和
Wiki + RAW 双 ACL；只有引文正文不可用时再查 native source custody 与
citation-token 运行时签名环。

frozen release scope、named-human decision ring 与 publish-authorization ring 只
属于 Candidate 决策/发布链，Golden evaluator ring 只属于后续 C4；它们都不是 C7
只读体验的前置条件。只读演示不得为了“让页面可用”而打开这些写链路。

端口也不是版本号：

- `8081` 是 C7 期间明确保持不变的旧生产实例；
- `18085`（UI）与 `18094`（隔离后端）是当次 C7 验收环境；
- 正式版本身份由 Git commit/tree、镜像/二进制 SHA、release ID 与 activation
  epoch 共同决定，不能用“打开哪个端口”代替。

## 3. C7 验收事实

C7 使用既有 epoch2 做纯读重开，没有重新审批、签名、发布或推进 Head：

- 验收源码：`9fcf3386833d822a31f2de13fdf76c3eb6b13795`；
- 验收 tree：`7314d1c9bc82dc7efb114affb6f2450d0dbd36ae`；
- 隔离后端二进制 SHA-256：
  `aa069e2566fd0b88fb6280bae8f1759d390fefdcfd32e1820602e0bdaa2ebc34`；
- Active-current 与 explicit-pinned/no-fallback：PASS；
- 7 分类、67 字段：PASS；
- citation preview/content：17/17 PASS；
- canonical lineage：1 个 `text` + 16 个 `parent_text`，唯一 owner 全部 PASS；
- C1 self-hash/native manifest、双 parse 摘要、Unicode code-point offset：PASS；
- 三份 PDF 的页码、bbox、file SHA、quote SHA 与可见高亮：PASS；
- UI 来源切换与三份 PDF 可见验收：PASS；
- 五表终态：preparations/releases/members/heads/receipts =
  `2/2/150/1/2`，验收前后不变；
- 旧 R1、epoch2 release/receipt/Head/75 members、生产 `8081`：不变；
- business DB writes、provider/model、C4、Candidate、release、receipt、Head、
  approval、signature effects：全部为 0；隔离角色密码轮换 1 次，未持久化敏感值。

B0 已把授权范围内的只读副本放入 Evidence Pack。用户冻结输入
`c7-ui-visible-terminal.json` 的 external SHA-256 为
`20575de17ca3a5a98e540848a245ef1af4a27d3e2feca12c7a38424350d45b50`，
canonical self-hash 为
`1d57527fbfa3dbfae9b11d14295a4efde0cc0c379b8d5c506c05ce8a0ea59ff6`。
此前记录的 `0e24db1d6ae4632acb538d03b18d84d2ffd0d41b8c39ef6cb5d251318dfa3396`
对应后续 `c7-ui-cache-corrected-terminal-20260831.json`；两份回执绑定同一 815
commit/tree/backend binary/epoch2 release，但必须分别登记，不能互相替代。

## 4. Chrome 可见验收的正确路径

需要复用用户现有 Chrome 登录态时，使用 Computer Use 直连
`com.google.Chrome`（`node_repl` + `@oai/sky`）。这条路径不依赖 ChatGPT/Codex
浏览器扩展，也不要求切换 Chrome Profile。

必须把两个问题分开：

1. 能否控制 Chrome；
2. WeKnora 站点会话是否仍已登录。

扩展未安装不等于 Chrome 不可控；页面跳到 `/login` 也不等于控制通道故障。
不得把密码、session、token 写入仓库、回执或日志；需要登录时由用户在可见页面
自行完成。

## 5. C4 历史后续边界（不是当前队列）

旧提交 `6d56618d0d9796e10d87f93e6b04188a49da9296` 只作历史参考，**不在
main**。它绑定旧 Candidate、固定 reviewer=`linyao`、固定
attestor=`workspace-owner-houjing`，真实结论是 `QUALITY_FAIL`。

若未来路线重新授权 C4，则必须：

1. 从最新 `origin/main` 新建独立 OpenSpec/Mission；
2. 先冻结业务目标、Metric ID、输入权威、预算、provider/model 边界和人工责任；
3. 使用当前 main 的 canonical Candidate/Evidence/Golden 合同，禁止复制旧哈希、
   旧 reviewer/attestor 或把 `QUALITY_FAIL` 改写成 PASS；
4. provider/model、DB、审批、签名、Candidate/release/Head 等外部动作分别申请并
   记录，默认均为 `NOT RUN`；
5. C4 的失败不能修改当前已验收的 C7 serving release。

历史详细接手卡见
[`docs/insurance-kb/26-mvp-815-engineering-handoff.md`](docs/insurance-kb/26-mvp-815-engineering-handoff.md)。

## 6. 仓库整理状态

已创建完整 Git 引用归档：

- 文件：`../archives/insurancekb-weknora-pre-cleanup-20260831.bundle`；
- mode：`0600`；
- bytes：`147412595`；
- SHA-256：`7d35f64fe2611148ca96760752d6a1c331be8f62433fc07ec274647e66a31725`；
- `git bundle verify`：PASS；486 refs，complete history。

当前主工作区和 4 个历史 worktree 为 dirty，全部保护；任务私有回执、发布证据、
凭据相关目录也不自动删除。clean worktree 的精确处置清单见
[`docs/insurance-kb/27-mvp-815-repository-cleanup.md`](docs/insurance-kb/27-mvp-815-repository-cleanup.md)。

## 7. 绝不再踩的坑

- 端口、知识库名称、容器名称都不是版本身份；必须核对 commit/tree、制品 SHA、
  release/epoch。
- frozen 历史向量与当前工厂输出应分别通过 canonical/typed 校验；不能强迫新
  Candidate 派生哈希等于旧 release，也不能改旧向量“让测试变绿”。
- Python 持久化 quote offset 是 Unicode code-point 域；Go frozen reader 不能按
  UTF-8 byte 下标切中文。
- `parent_text` 必须先完整验真到 canonical native child；overlap 只按唯一连续、
  manifest 顺序和 non-overlap contribution owner 选择，不能“取第一个”。
- task-private replay 缺私有工件时不能向 PostgreSQL lane 泄漏 module-level skip；
  lane 必须 tests > 0、skipped = 0。
- 本地绿不等于 CI 绿；合并前必须等远端真实门禁。
- 不从 dirty 工作区构建正式交付，不整体 merge 历史分支，不在 main 保留推倒重来
  的中间实现。
- 启动 Docker/Colima 可能自动恢复 `8081` 容器；未确认生产影响前不得把“启动
  本地依赖”当作无副作用操作。
- 凭据不得出现在命令行 DSN、traceback、文档或 Git；异常泄漏后先轮换再继续。

## 8. 接手阅读顺序

1. [`AGENTS.md`](AGENTS.md)
2. [830 技术蓝图](jlx_enterprise_llm_wiki_technical_blueprint_830.md)
3. [830 开发执行章程](docs/insurance-kb/28-development-execution-charter-830.md)
4. [830 Goal Cards](docs/insurance-kb/29-goal-cards-830.md)
5. 本文件
6. [B0 Evidence Pack](docs/insurance-kb/evidence/830-b0/)
7. [MVP-815 工程接手卡](docs/insurance-kb/26-mvp-815-engineering-handoff.md) 与
   [OpenSpec 120](openspec/changes/120-schema-wiki-medical-596-1-mvp/) 只作已冻结历史
   证据；后续 Goal 仍须自己的授权与适用 OpenSpec。
