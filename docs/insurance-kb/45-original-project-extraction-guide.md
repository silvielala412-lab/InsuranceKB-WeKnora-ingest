# 原项目抽取模块与运行说明

本文用于帮助新使用者运行原项目的文档抽取功能。命令中的“项目根目录”请替换成自己电脑上的项目目录，不需要使用本文作者的本地路径。

## 1. 项目能做什么

原项目分为两部分：

1. 平台侧负责文件上传、PDF/Word/Excel 解析、分页和文本切片。
2. 抽取模块负责按照保险知识字段，从解析后的材料中提取字段值，并保存原文依据。

抽取结果不会直接覆盖原文。每次运行都会生成独立的结果目录，方便复查、重跑和对比。

## 2. 代码位置

### 2.1 文件解析

| 相对路径 | 作用 |
| --- | --- |
| `internal/application/service/wiki_ingest.go` | 文件接收和解析任务编排 |
| `docreader/parser/pdf_parser.py` | PDF 文本解析 |
| `docreader/parser/chain_parser.py` | 根据文件类型选择解析器 |
| `docreader/parser/base_parser.py` | 解析器基础接口 |
| `docreader/parser/registry.py` | 解析器注册和选择 |

### 2.2 字段抽取

| 相对路径 | 作用 |
| --- | --- |
| `harness/src/insurance_harness/compiler/cli.py` | 命令行入口 |
| `harness/src/insurance_harness/compiler/pipeline.py` | 抽取流程和运行产物 |
| `harness/src/insurance_harness/compiler/sections.py` | 章节切分和文档结构识别 |
| `harness/src/insurance_harness/compiler/routing_data.py` | 字段分组、关键词和同义词线索 |
| `harness/src/insurance_harness/compiler/extract.py` | 分批提取字段值和原文引用 |
| `harness/src/insurance_harness/compiler/llm.py` | 模型调用和回放调用 |
| `harness/src/insurance_harness/compiler/parsing.py` | 模型输出解析 |
| `harness/src/insurance_harness/compiler/verification.py` | 原文引用匹配检查 |
| `harness/src/insurance_harness/compiler/evidence_verifier.py` | 证据来源和定位检查 |
| `harness/src/insurance_harness/compiler/cleaning.py` | 空值、占位值和格式清洗 |
| `harness/src/insurance_harness/compiler/gapfill.py` | 对未提取字段做定向补充提取 |
| `harness/src/insurance_harness/compiler/voting.py` | 对高风险字段做多次判断和一致性检查 |
| `harness/src/insurance_harness/compiler/judge.py` | 人工复核或裁决队列 |
| `harness/src/insurance_harness/compiler/native_pdfplumber.py` | 本地 PDF 解析适配 |
| `harness/src/insurance_harness/compiler/native_mineru_cloud.py` | MinerU 解析适配 |

## 3. 抽取流程

```text
上传文件
   ↓
解析 PDF/Word/Excel，保留页码和原文
   ↓
按章节和字段分组
   ↓
模型提取字段值、原文引用和页码
   ↓
检查引用是否真的存在于原文
   ↓
做类型、格式和占位值清洗
   ↓
高风险字段多次判断
   ↓
对仍为空的字段做定向补充提取
   ↓
生成字段结果、运行清单和复核队列
```

模型只负责理解语义；文件解析、字段路由、引用检查、格式校验和结果落盘由程序完成。

## 4. 环境要求

- Python 3.12 或更高版本
- `uv`
- 如果需要运行前端，再准备 Node.js 和 npm
- 如果需要运行平台依赖，再准备 Docker Desktop 或兼容的 Docker Compose

在项目根目录首次安装 Python 依赖：

```powershell
uv sync --directory harness
```

如果需要前端依赖：

```powershell
npm ci --prefix frontend
```

## 5. 本地回放运行

本地回放适合先验证流程，不会访问平台接口，也不会产生新的模型调用。需要准备：

- 一个产品目录，目录内放待处理的 PDF 文件；
- 一份已经录制好的模型响应目录。

在项目根目录执行：

```powershell
$env:HARNESS_MODEL_PROFILE = "replay"
uv run --directory harness python -m insurance_harness.compiler.cli extract-replay `
  "产品目录" `
  --replay-identity "replay-identity" `
  --parser-fingerprint "pdfplumber@0.11:text-v1" `
  --replay-dir "模型响应目录" `
  --run-dir "out/replay-run"
```

如果出现 `replay_fixture_required`，说明没有传入 `--replay-dir`。

## 6. 使用模型进行抽取

该模式会把待处理材料发送给配置的模型服务。运行前请确认材料范围、网络访问和调用预算。

在项目根目录执行：

```powershell
$env:HARNESS_MODEL_PROFILE = "offline-eval"
$env:HARNESS_LLM_BASE_URL = "模型服务地址"
$env:HARNESS_LLM_API_KEY = "从本机安全凭据注入"
$env:HARNESS_LLM_MODEL_WEAK = "模型名称"

uv run --directory harness python -m insurance_harness.compiler.cli extract-replay `
  "产品目录" `
  --replay-identity "local-material-v1" `
  --parser-fingerprint "pdfplumber@0.11:text-v1" `
  --run-dir "out/model-run"
```

API key 不要写入代码、脚本、文档或 Git。若项目配置使用网关裁决模式，还需要按 `harness/.env.example` 配置对应的裁决模型。

## 7. 从平台材料抽取

如果材料已经在平台知识库中，可以使用平台来源入口：

```powershell
uv run --directory harness python -m insurance_harness.compiler.cli extract `
  --source weknora `
  --space-id "<space-id>" `
  --knowledge-id "<knowledge-id>" `
  --parser-fingerprint "<parser-fingerprint>" `
  --product-id "<product-id>" `
  --product-name "<product-name>" `
  --run-dir "out/platform-run"
```

这个命令需要在 `harness/.env` 或系统环境变量中配置：

```text
HARNESS_WEKNORA_BASE_URL
HARNESS_WEKNORA_API_KEY
```

如果只是熟悉抽取流程，建议先使用第 5 节的本地回放方式。

## 8. 结果文件

运行目录一般包含：

```text
pred.jsonl          每个字段的预测值、状态、置信度和原文引用
manifest.json       运行身份、模型、调用次数和失败统计
judge-queue.jsonl   需要人工复核的字段
checkpoint.sqlite   中断后继续运行所需的检查点
dead-letters.jsonl  多次失败后隔离的任务
```

命令结束时会打印运行编号、模型、字段数量、调用次数、失败数量以及 `pred.jsonl` 的路径。

## 9. 继续运行和人工复核

### 9.1 中断后继续

在原命令后增加 `--resume`，并保持相同的运行目录：

```powershell
uv run --directory harness python -m insurance_harness.compiler.cli extract-replay `
  "产品目录" `
  --replay-identity "replay-identity" `
  --parser-fingerprint "pdfplumber@0.11:text-v1" `
  --replay-dir "模型响应目录" `
  --run-dir "out/replay-run" `
  --resume
```

### 9.2 应用复核结果

人工或裁决流程生成 JSONL 后，可以写回同一运行目录的字段结果：

```powershell
$env:HARNESS_MODEL_PROFILE = "manual"
uv run --directory harness python -m insurance_harness.compiler.cli apply-judgements `
  "out/model-run" `
  "复核结果.jsonl"
```

## 10. 常见问题

| 现象 | 处理 |
| --- | --- |
| `uv` 找不到 | 安装 uv 后重新打开终端，再执行依赖安装。 |
| `缺少弱模型网关配置` | 使用回放模式，或补齐模型服务地址、key 和模型名。 |
| `invalid_model_profile` | 回放使用 `replay`，模型评测使用 `offline-eval`。 |
| `replay_fixture_required` | `replay` 模式必须提供 `--replay-dir`。 |
| 抽取结果为空 | 检查产品目录是否包含 PDF、解析器是否能读取 PDF，以及运行日志中的失败原因。 |
| 字段有值但被标记待复核 | 查看 `judge-queue.jsonl` 和 Evidence 引用；待复核不等于原文没有数据。 |
| 运行中断 | 使用相同参数和运行目录追加 `--resume`。 |

## 11. 安全提醒

- 不要把 API key、数据库密码和平台 Token 提交到 Git。
- 使用模型抽取前，确认文档是否允许发送到外部模型服务。
- 原始材料、抽取结果和复核文件应按项目权限保存。
- 生产环境使用前，应补充真实数据验证、权限配置和运行审计。
