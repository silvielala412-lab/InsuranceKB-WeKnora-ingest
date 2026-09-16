# Mission 136 · LLM-first 候选裁决

## Goal

在自有 `InsuranceKB-WeKnora-ingest` worktree 内，把规则、模板和外部映射从“最终
取值器”改成“候选生成器”。所有业务字段候选经过一次 LLM 语义裁决，再由现有
Evidence、类型和三态校验确认，降低规则误选和规则短路造成的漏字段。

## Owner 与边界

- 唯一写 Owner：当前 Codex 会话；只修改本 worktree。
- 依据：用户批准 `Mission 136`。
- 允许：Python 抽取管道、提示词、单元/管道测试和维护文档。
- 禁止：PA-ALG 原项目推送或提交、真实 Provider/百炼调用、原始 PDF 外发、数据库、
  Candidate/Release/Active、Docker 和生产服务改动。

## 本次交付

1. fastpath/规则候选不再跳过 LLM；统一进入语义裁决。
2. LLM 可在多个候选和候选页上下文中选择或纠正值，并保留裁决来源。
3. 险种简称等关键字段若已有候选但无法裁决，记录 `candidate_unresolved`，不能静默
   变成普通未知。
4. 现有 Evidence 回验、类型校验、三态语义和发布边界保持不变。

## 验收

- 规则候选对应的 LLM 调用可由测试桩证明；
- 正确 Evidence 值能从多个候选中选出，错误候选不能直接覆盖语义裁决；
- 语义裁决失败不写入未验证值，并留下可追踪的未决原因；
- 现有 compiler 定向测试和新增测试通过；
- `git diff --check` 通过，真实 provider/live 状态记为 `NOT RUN`。

## 验证矩阵

| Requirement | 实现 | 测试/证据 | commit | 状态 |
|---|---|---|---|---|
| LFC1 | `compiler/semantic_resolution.py`、`compiler/pipeline.py` | `test_semantic_resolution_136.py`、模板管道断言 | 未提交 | PASS |
| LFC2 | `compiler/prompts/__init__.py`、resolver 审计元数据 | 两个候选同场景测试，保留候选 Evidence/页上下文 | 未提交 | PASS |
| LFC3 | `candidate_unresolved` 分支 | 不可回验值测试 | 未提交 | PASS |
| LFC4 | 复用 `run_validation_chain`，未改发布边界 | `test_compiler_extract.py`（10 条） | 未提交 | PASS |
| LFC5 | 本地 worktree 例外 | provider/PDF/DB/live 均未执行 | 未提交 | NOT RUN（按范围） |
| 全管道 Windows 回归 | 未改既有 POSIX 锁实现 | `fcntl`、`O_DIRECTORY`、`O_NONBLOCK` 阻断 | 未提交 | BLOCKED（环境/基线） |

## 后续但本卡不做

- 全量召回索引和跨文档候选生成器；
- Schema Discovery/Assisted Schema；
- 三款真实产品重跑及前端展示；
- 生产模型准入、部署和数据库落库。

## 维护台账

以下项目保留在后续迭代队列，本次不宣称完成：

| 状态 | 项目 | 下一步验收 |
|---|---|---|
| TODO | 全 PDF 页面高召回候选扫描（跨文档、跨页） | 固定分母后比较字段召回率、Evidence 命中率和调用耗时 |
| TODO | 候选页以外的定向补抽 | 对 `candidate_unresolved`/unknown 生成可重放的页级补抽任务 |
| TODO | 外部映射接入 | 将产品主数据/XLSX 作为候选来源，再走同一语义裁决，不让模型猜主数据 |
| TODO | Schema Discovery / Assisted Schema | 先离线评测，再决定是否允许模型提出新字段和分类 |
| TODO | 三款真实产品重跑和前端展示 | 需单独 Mission 批准 provider、样本外发、结果写入和服务启动 |
| BLOCKED | Windows 本地完整管道回归 | 先解决仓库既有 POSIX 文件锁兼容，不能用桩结果代替真实回归 |
