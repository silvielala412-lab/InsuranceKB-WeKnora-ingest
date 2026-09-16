# 原项目抽取模块与启动说明

本文对应原始 `InsuranceKB-WeKnora` 项目，不包含后续 `v5_preview` 迭代内容。使用者只需要把命令中的“项目根目录”替换成自己的目录即可，不需要重新拉代码。

## 1. 先说结论

- 原项目已经有完整的保险语义抽取管线，代码集中在 `harness/src/insurance_harness/compiler/`。
- 原项目没有单独名为 `ingest` 的 Python 服务目录；平台侧 Ingest 在 Go 的 `internal/application/service/wiki_ingest.go`，保险语义处理在 Python `compiler` 管线。
- 原项目抽取入口是批处理 CLI，不是网页预览服务。`wiki-api` 主要提供 Harness 治理和任务观测 API，启动它不会自动抽取产品字段。
- 当前 v5 预览服务属于后续新增层，查看原项目效果时不需要覆盖、停止或修改现有 8091/5174 服务。

## 2. 原项目代码位置

### 2.1 平台 Ingest：上传和解析

| 路径 | 作用 |
| --- | --- |
| `internal/application/service/wiki_ingest.go` | WeKnora 原生上传、解析任务和 Wiki ingest 编排 |
| `docreader/parser/pdf_parser.py` | PDF 文本解析 |
| `docreader/parser/chain_parser.py` | 按文件类型选择解析器 |
| `docreader/parser/base_parser.py` | 解析器基础接口 |
| `docreader/parser/registry.py` | 解析器注册和选择 |

这一层产出页文本、文档结构和可供下游检索的原文，不负责把“险种简称、适用人群、费率可调”等字段填入保险 Schema。

### 2.2 保险抽取 Harness

| 路径 | 作用 |
| --- | --- |
| `harness/src/insurance_harness/compiler/cli.py` | 抽取命令入口：`extract`、`extract-replay`、`apply-judgements` |
| `harness/src/insurance_harness/compiler/pipeline.py` | 主流程、状态、产物和断点续跑 |
| `harness/src/insurance_harness/compiler/sections.py` | 文档分段、章节路由、文档族识别 |
| `harness/src/insurance_harness/compiler/routing_data.py` | 字段到抽取组的映射和同义词线索 |
| `harness/src/insurance_harness/compiler/extract.py` | 分批调用 LLM、解析候选值、接 Evidence |
| `harness/src/insurance_harness/compiler/llm.py` | 模型客户端、百炼 OpenAI 兼容调用、Replay 客户端 |
| `harness/src/insurance_harness/compiler/parsing.py` | 对抗性 JSON 输出解析 |
| `harness/src/insurance_harness/compiler/verification.py` | 引文归一化和原文匹配校验 |
| `harness/src/insurance_harness/compiler/evidence_verifier.py` | Evidence 真实性、来源和定位校验 |
| `harness/src/insurance_harness/compiler/cleaning.py` | 占位值清洗、空值和弱值处理 |
| `harness/src/insurance_harness/compiler/gapfill.py` | 针对 unknown 字段的定向补漏 |
| `harness/src/insurance_harness/compiler/voting.py` | 高风险字段多次尝试和一致性判断 |
| `harness/src/insurance_harness/compiler/judge.py` | 人工/裁决队列接口 |
| `harness/src/insurance_harness/compiler/native_pdfplumber.py` | 本地 PDF 解析适配器 |
| `harness/src/insurance_harness/compiler/native_mineru_cloud.py` | MinerU 解析适配器 |
| `harness/src/insurance_harness/compiler/parsed_documents.py` | 解析产物模型和来源边界 |

### 2.3 Harness 服务入口

| 路径 | 作用 |
| --- | --- |
| `harness/src/insurance_harness/service_shell/cli.py` | `wiki-api` 和 `wiki-worker` 两个进程入口 |
| `harness/src/insurance_harness/service_shell/apps.py` | API/Worker 健康检查和观测路由 |
| `harness/src/insurance_harness/service_shell/config.py` | `WIKI_` 前缀的服务配置 |

## 3. 原项目抽取链路

```text
WeKnora 上传/解析
        ↓
页文本、页码、chunk、来源身份
        ↓
compiler.cli
        ↓
文档族识别和章节切分
        ↓
字段组路由（每批少量字段）
        ↓
LLM 输出字段值 + 原文引文 + 页码
        ↓
JSON 解析 → Evidence 原文回验 → 类型/占位值清洗
        ↓
高风险字段投票 → unknown 定向补漏
        ↓
pred.jsonl、manifest.json、judge-queue.jsonl
```

原项目的关键特点是：模型只负责语义判断，解析、字段路由、Evidence 回验、类型校验和产物落盘由代码完成。

## 4. 环境准备

在自己的项目根目录执行。首次使用或锁文件变化后执行一次即可：

```powershell
uv sync --directory harness
```

如果需要运行前端或查看 WeKnora 原生界面，再执行：

```powershell
npm ci --prefix frontend
```

原项目的 Python 配置从 `harness/.env` 读取，模板见 `harness/.env.example`。真实 key 只通过本机环境变量或未提交的 `.env` 注入，不要写入代码和文档。

## 5. 离线回放抽取（不启动 HTTP 服务）

这是查看原项目抽取逻辑最安全的方式，不会碰现有 8091/5174，也不会访问 WeKnora 或外部模型。

### 5.1 使用已有 Replay 夹具

```powershell
Set-Location "项目根目录"
$env:HARNESS_MODEL_PROFILE = "replay"
uv run --directory harness python -m insurance_harness.compiler.cli extract-replay `
  "产品目录" `
  --replay-identity "replay-identity" `
  --parser-fingerprint "pdfplumber@0.11:text-v1" `
  --replay-dir "Replay夹具目录" `
  --run-dir "out/original-replay"
```

`产品目录` 应包含待处理 PDF；`Replay夹具目录` 应包含已经录制的模型响应。该模式不产生新的模型调用。

### 5.2 使用弱模型重新抽取

该模式会把抽取文本发送到配置的模型服务，必须确认数据外发范围和调用预算：

```powershell
Set-Location "项目根目录"
$env:HARNESS_MODEL_PROFILE = "offline-eval"
$env:HARNESS_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:HARNESS_LLM_API_KEY = "<从本机安全凭据注入>"
$env:HARNESS_LLM_MODEL_WEAK = "qwen-plus"
uv run --directory harness python -m insurance_harness.compiler.cli extract-replay `
  "产品目录" `
  --replay-identity "local-material-v1" `
  --parser-fingerprint "pdfplumber@0.11:text-v1" `
  --run-dir "out/original-llm"
```

如果配置了 `HARNESS_JUDGE_MODE=gateway`，还需要配置 `HARNESS_LLM_MODEL_JUDGE_FALLBACK`；默认 `claude-session` 只会生成待裁决队列，不会自动替人工批准。

### 5.3 查看抽取结果

抽取结束后重点查看：

```text
out/original-llm/pred.jsonl          字段级预测、值、Evidence、状态
out/original-llm/manifest.json       运行身份、调用次数、死信、待裁决数量
out/original-llm/judge-queue.jsonl   需要人工/裁决处理的字段
out/original-llm/checkpoint.sqlite   中断后续跑所需的检查点
```

命令结束时会打印 `run`、`model`、字段数、调用数、死信数和 `pred.jsonl` 路径。

## 6. 从 WeKnora 来源抽取

这是原项目的生产来源入口，需要已经存在的 WeKnora Space、Knowledge 和 Harness 配置。它不是本地网页预览：

```powershell
Set-Location "项目根目录"
uv run --directory harness python -m insurance_harness.compiler.cli extract `
  --source weknora `
  --space-id "<space-id>" `
  --knowledge-id "<knowledge-id>" `
  --parser-fingerprint "<parser-fingerprint>" `
  --product-id "<product-id>" `
  --product-name "<product-name>" `
  --run-dir "out/weknora-run"
```

需要在 `harness/.env` 或环境变量中配置 `HARNESS_WEKNORA_BASE_URL`、`HARNESS_WEKNORA_API_KEY`。生产 profile 还受额外的模型准入和运行身份校验约束；如果只是对比原项目抽取效果，优先使用第 5 节的离线回放或受控评测模式。

## 7. 可选：单独启动原项目 Harness API

原项目 API 默认端口是 8000。为了不影响当前 8091/5174，示例使用隔离端口 `18080`；它只提供治理/任务观测接口，不会自动显示 v5 产品抽取结果。

前置条件：可访问的 Harness PostgreSQL。没有数据库时不要启动这个 API，直接使用第 5 节 CLI。

```powershell
Set-Location "项目根目录"
$env:WIKI_POSTGRES_DSN = "postgresql+psycopg://<user>:<password>@<host>:<port>/<database>"
$env:WIKI_API_HOST = "127.0.0.1"
$env:WIKI_API_PORT = "18080"
uv run --directory harness wiki-api
```

检查 API：

```powershell
Invoke-WebRequest "http://127.0.0.1:18080/livez" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest "http://127.0.0.1:18080/readyz" -UseBasicParsing | Select-Object StatusCode
```

停止时在窗口按 `Ctrl+C`。如果异常残留，只停止这个隔离端口对应的进程：

```powershell
Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ }
```

不要把原项目 API 改绑到 8091，也不要用宽范围的 `taskkill`。

## 8. 常见问题

| 现象 | 原因和处理 |
| --- | --- |
| `uv` 找不到 | 安装 uv 后重新打开终端；依赖安装使用 `uv sync --directory harness`。 |
| `缺少弱模型网关配置` | 使用第 5.1 节 Replay，或补齐 `HARNESS_LLM_BASE_URL/API_KEY/MODEL_WEAK`。 |
| `invalid_model_profile` | `extract-replay` 需要 `replay` 或 `offline-eval`，不能使用默认的 `disabled`。 |
| `replay_fixture_required` | `HARNESS_MODEL_PROFILE=replay` 时必须传 `--replay-dir`。 |
| `V5_PROVIDER_RUN_NOT_CONFIGURED` | 这是后续 v5 预览 API 的错误，不属于原项目 CLI。请检查是否误启动了 v5 服务。 |
| 原项目 API 启动失败 | 先检查 `WIKI_POSTGRES_DSN` 和数据库可达性；单纯看抽取结果不需要启动 API。 |
| 端口冲突 | 原项目 API 使用 18080；现有 v5 服务继续使用 8091/5174，不要复用端口。 |

## 9. 与当前 v5 预览的边界

```text
原项目 compiler CLI       → 直接产出 pred.jsonl / manifest.json
原项目 wiki-api            → 治理和任务观测，不是字段预览页
当前 v5_preview API        → 读取 provider-run，提供产品字段预览
当前 v5 前端               → /v5-preview 页面
```

因此，想验证“原项目抽取效果”，看 `pred.jsonl` 和 `manifest.json`；想看当前迭代的产品字段页面，才访问 5174。两套流程可以同时存在，端口和结果目录分开即可。
