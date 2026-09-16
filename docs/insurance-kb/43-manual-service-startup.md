# v5 抽取预览服务手动启动说明

本文给没有参与开发的使用者使用。命令默认在 **项目根目录** 执行，即当前目录下能看到 `harness`、`frontend` 等文件夹。请先在自己的电脑上进入本地项目目录；本文不包含任何个人电脑路径、账号或 API key。

## 1. 服务组成

| 服务 | 作用 | 默认地址 |
| --- | --- | --- |
| Python Harness v5 preview API | 读取抽取结果、提供预览和可选的实时 LLM 抽取接口 | `http://127.0.0.1:8091` |
| Vite 前端 | 展示 Schema 和产品抽取结果 | `http://127.0.0.1:5174/v5-preview` |

前端的 `/v5-preview-api/*` 请求会转发到 8091。仓库配置的 Vite 默认端口是 5173；本文显式使用 5174，以保持测试地址一致。

## 2. 环境要求

- Python 3.12 或更高版本
- `uv`
- Node.js 和 npm
- 如需启动 WeKnora 基础依赖，再准备 Docker Desktop 或兼容的 Docker Compose

首次使用或锁文件发生变化时，在项目根目录执行：

```powershell
uv sync --directory harness
npm ci --prefix frontend
```

## 3. 启动后端（8091）

打开第一个 PowerShell 窗口，当前目录保持在项目根目录：

```powershell
Set-Location (Join-Path (Get-Location) "harness")
$env:PYTHONPATH = "src"
```

如果要让页面展示已有的 `provider-run` 结果，在同一窗口设置结果文件名。文件通常放在项目根目录，文件名按实际情况替换：

```powershell
$projectRoot = (Get-Location).Parent.FullName
$artifactName = "provider-run-<实际运行编号>.json"
$artifactPath = Join-Path $projectRoot $artifactName
if (-not (Test-Path -LiteralPath $artifactPath)) {
  throw "结果文件不存在：$artifactPath"
}
$env:V5_PREVIEW_RUN_ARTIFACT = $artifactPath
```

启动 API：

```powershell
uv run uvicorn insurance_harness.v5_preview.api:app_factory --factory --host 127.0.0.1 --port 8091
```

如果暂时不展示结果文件，可以不设置 `V5_PREVIEW_RUN_ARTIFACT`；此时健康检查仍可用，但 `/v5-preview-api/provider-run` 会返回未配置结果的提示。切换结果文件后必须重启后端。

需要让局域网其他设备访问时，可将 `--host 127.0.0.1` 改为 `--host 0.0.0.0`，并自行配置防火墙和访问控制。只在本机测试时建议保留 `127.0.0.1`。

## 4. 启动前端（5174）

打开第二个 PowerShell 窗口，并重新进入项目根目录：

```powershell
# 将上一行替换为你自己的项目根目录；后续命令均以项目根目录为当前目录
Set-Location "项目根目录"
$env:VITE_V5_PREVIEW_TARGET = "http://127.0.0.1:8091"
npm --prefix frontend run dev -- --host 0.0.0.0 --port 5174
```

浏览器访问：

```text
http://127.0.0.1:5174/v5-preview
```

只在本机使用时，可把 `--host 0.0.0.0` 改成 `--host 127.0.0.1`。如果后端换了端口，必须同步修改 `VITE_V5_PREVIEW_TARGET` 并重启前端。

## 5. 启动检查

打开第三个 PowerShell 窗口，在任意目录执行：

```powershell
Invoke-RestMethod "http://127.0.0.1:8091/v5-preview-api/health" | ConvertTo-Json
Invoke-WebRequest "http://127.0.0.1:5174/v5-preview" -UseBasicParsing | Select-Object StatusCode
```

正常情况下：

- 后端返回 `status: ok`。
- `provider_run_configured` 为 `true` 表示已加载结果文件。
- 前端请求返回 HTTP `200`。

查看结果文件是否已加载：

```powershell
Invoke-RestMethod "http://127.0.0.1:8091/v5-preview-api/provider-run" |
  Select-Object run_id, status, products
```

查看端口是否监听：

```powershell
Get-NetTCPConnection -LocalPort 8091,5174 -State Listen |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

## 6. 停止和重启

正常停止：在两个服务窗口分别按 `Ctrl+C`，先停前端，再停后端。若进程残留，按端口精确停止：

```powershell
Get-NetTCPConnection -LocalPort 8091 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ }

Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ }
```

然后按第 3、4 节重新启动。不要使用宽范围的 `taskkill`，也不要执行 `docker compose down -v`，避免影响其他项目或删除本地数据卷。

## 7. 可选：WeKnora 基础依赖

只有同时使用常规 WeKnora `/api` 页面、文档解析或检索能力时，才需要基础容器。单独查看 v5 provider-run 结果不依赖这些容器。

在项目根目录执行：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres redis docreader
docker compose -f docker-compose.dev.yml ps
```

容器运行正常不代表 8091/5174 已启动，仍需按第 5 节分别检查后端和前端。

## 8. 可选：实时 LLM 抽取

只展示已有 `provider-run` 文件不需要模型调用。调用 `/v5-preview-api/preview` 重新抽取时，在启动后端的同一窗口设置：

```powershell
$env:V5_PREVIEW_LLM_ENABLED = "1"
$env:HARNESS_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:HARNESS_LLM_API_KEY = "<从本机安全凭据注入>"
$env:HARNESS_LLM_MODEL_WEAK = "qwen-plus"
$env:V5_PREVIEW_LLM_FAMILY = "qwen"
```

不要把 key 写入代码、`.env`、脚本或 Git。模型调用次数和数据外发范围按当前项目的授权要求执行；手动启动服务本身不会自动发起抽取。

## 9. 常见问题

| 现象 | 处理 |
| --- | --- |
| `V5_PROVIDER_RUN_NOT_CONFIGURED` | 检查结果文件名和路径，确认在启动 8091 的窗口设置了 `V5_PREVIEW_RUN_ARTIFACT`，然后重启后端。 |
| `Failed to execute 'json'` 或页面空白 | 先直接访问 `http://127.0.0.1:8091/v5-preview-api/health`；后端失败则重启后端，后端正常则检查前端代理变量和端口。 |
| `V5_PREVIEW_PROVIDER_NOT_CONFIGURED` | 实时 `/preview` 的模型变量不完整；展示已有 provider-run 不受影响。 |
| 5174 访问不了但 5173 可用 | 前端启动时漏了 `--port 5174`，停止当前 Vite 后按第 4 节重启。 |
| 8091 端口占用 | 用第 5 节的端口查询找到旧进程，停止后再启动，或改用新端口并同步修改前端代理。 |
