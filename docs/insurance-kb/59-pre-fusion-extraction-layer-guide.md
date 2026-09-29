# 融合前 V5 抽取层导读

本文面向刚拉取 `InsuranceKB-WeKnora-ingest` 的开发者，说明融合上游基础设施之前，保险产品抽取链路的代码边界、数据合同、运行入口和常见误区。

本文描述的是 `harness/src/insurance_harness/v5_preview/` 这条 V5 预览抽取链。它是当前保险字段抽取质量的来源；不要把它与后续上游 `product_ingestion` 任务链或旧版 `compiler` 抽取链混为一谈。

## 1. 先看整体边界

```text
产品 PDF / 补充材料
        |
        v
材料身份冻结、页面读取、OCR 回执
        |
        v
Schema 字段选择与候选页面召回
        |
        v
Schema-guided LLM 抽取
        |
        v
Evidence 回原文核验、字段质量门禁
        |
        v
V5CandidatePreview
        |
        +--> provider-run / audit / feedback 封存文件
        |
        +--> 只读预览、概念关系、搜索问答 API
```

V5 抽取层只负责生成候选预览和评测产物，不直接代表正式 Wiki Active Release。预览成功、字段有值或页面能够展示，都不能推导出已经审核、发布或上线。

平台侧的文件上传、知识库权限和通用解析属于 WeKnora/Go 服务；前端只负责展示和交互。模型只负责根据给定 Schema 和上下文返回候选值，字段路由、来源核验、状态约束和产物封存由 Python 代码负责。

## 2. 代码地图

### 2.1 V5 抽取主链

| 模块 | 职责 | 主要入口/出口 |
| --- | --- | --- |
| `v5_preview/catalog.py` | 加载 V5 Schema catalog，计算 catalog 摘要 | `load_v5_catalog()`、`catalog_sha256()` |
| `v5_preview/contracts.py` | 定义输入、Schema、字段、Evidence、Preview 合同 | `IngestRequest`、`CandidateField`、`V5CandidatePreview` |
| `v5_preview/ingest.py` | 插件注册、险种选择、字段拓扑校验、编译 Preview | `IngestPluginRegistry`、`V5PreviewCompiler.compile()` |
| `v5_preview/source_manifest.py` | 冻结产品/PDF/页数/SHA 等材料身份 | 材料清单与来源版本校验 |
| `v5_preview/material_loader.py` | 读取 PDF 页面、校验文件身份、保留页码和不可读信息 | `load_frozen_pdf_pages()` 等材料读取函数 |
| `v5_preview/ocr.py` | 对扫描页执行 OCR，并记录 OCR 回执 | OCR 页面文本和诊断 |
| `v5_preview/prepared_trial.py`、`trial_preparation.py` | 将材料准备成一次试验可消费的产品上下文 | `PreparedProduct`、准备阶段诊断 |
| `v5_preview/dynamic_ingest.py` | 按字段召回候选页、组织上下文窗口、处理长字段分片 | 候选页面/片段/批次规划 |
| `v5_preview/field_profiles.py` | 字段提示词方向、重点字段和风险画像 | 字段级抽取指导 |
| `v5_preview/value_constraints.py` | 值类型、枚举、空值和格式约束 | 字段值归一化/约束检查 |
| `v5_preview/llm_plugin.py` | 构造 Schema-guided 请求，调用 OpenAI-compatible Provider，解析闭合 JSON | `SchemaGuidedLlmPlugin.extract()` |
| `v5_preview/source_evidence.py` | 将 Evidence locator/quote 回查材料原文 | VERIFIED、NORMALIZED_MATCH、UNRESOLVED、AMBIGUOUS |
| `v5_preview/extraction_completion.py` | 对抽取缺口进行补抽编排 | 补抽字段和差异结果 |
| `v5_preview/source_supported_completion.py` | 仅对材料明确支持的字段生成补充结果 | 材料支持诊断和保守补全 |
| `v5_preview/full_schema_quality.py` | 全 Schema 字段覆盖和材料支持质量统计 | 字段覆盖/缺口分类 |
| `v5_preview/business_field_quality.py`、`m156_quality.py`、`m157_quality.py`、`m158_quality.py`、`m160_quality.py` | 业务重点字段、批次和替换质量门禁 | audit、replacement decision |
| `v5_preview/trial_contracts.py` | Provider、产品、字段和运行结果的批次合同 | `V5ProviderTrialRun` 等 |
| `v5_preview/trial_runner.py`、`m158_run.py`、`m160_run.py` | 单产品/多产品批量编排、并发、调用预算和结果合并 | `run_m158()`、`run_m160()` |
| `v5_preview/trial_artifacts.py`、`provider_trial.py` | 运行结果摘要、SHA 校验和原子落盘/读取 | `load_provider_trial_run()` |
| `v5_preview/api.py` | 只读读取封存结果，并提供预览、搜索问答和流式接口 | `/v5-preview-api/*` |

### 2.2 前端适配层

| 模块 | 职责 |
| --- | --- |
| `frontend/src/api/schema-wiki/v5/v5PreviewContract.ts` | 前端 V5 合同类型和导航投影 |
| `frontend/src/api/schema-wiki/v5Preview.ts` | 调用 catalog、provider-run、preview、search、stream API |
| `frontend/src/views/knowledge/schema-wiki/v5-preview/V5SchemaPreview.vue` | 抽取预览、概念关系、搜索问答三个页面状态和交互 |
| `frontend/src/views/knowledge/schema-wiki/v5-preview/v5FieldTable.ts` | 将受支持的字段值解析成表格；不能识别的值仍以文本显示 |
| `frontend/src/views/knowledge/schema-wiki/v5-preview/v5Concepts.ts` | 从多产品 Preview 投影概念及产品实例关系 |
| `frontend/src/views/knowledge/schema-wiki/v5-preview/v5SearchMarkdown.ts` | 将问答结果中的 Markdown/表格渲染到页面 |

## 3. 三个容易走错的入口

### 3.1 真实批量抽取入口

最近的批量验证入口是：

```text
m160_run.run_m160()
  -> m158_run.run_m158()
  -> 材料准备与全页读取
  -> dynamic_ingest 候选召回
  -> llm_plugin Schema-guided 抽取
  -> source_evidence 原文核验
  -> 质量门禁/保守替换
  -> V5ProviderTrialRun
```

`m160_run.py` 是本轮参数和材料范围编排，不是全部抽取逻辑。需要修改抽取质量时，优先定位 `dynamic_ingest.py`、`llm_plugin.py`、`source_evidence.py` 和质量模块，不要把逻辑堆到 `m160_run.py`。

### 3.2 单次领域编译入口

`V5PreviewCompiler.compile(request)` 的职责是把插件结果编译成合法 `V5CandidatePreview`：

```text
IngestRequest
  -> 选择已审核险种 Schema
  -> resolve catalog plugin
  -> plugin.extract(request, schema)
  -> 校验产品/版本/来源身份
  -> 校验字段 ordinal + field_id 拓扑
  -> 计算 preview_sha256
  -> V5CandidatePreview
```

它不读取 PDF，不安排多产品并发，也不负责模型网络调用。模型和材料编排在批量引擎；该编译器只负责合同边界和 fail-closed 校验。

### 3.3 前端 API 入口

V5 预览 API 在 `harness/src/insurance_harness/v5_preview/api.py`：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/v5-preview-api/health` | 检查 catalog、LLM、封存 run、搜索配置 |
| `GET` | `/v5-preview-api/catalog` | 返回 Schema catalog |
| `GET` | `/v5-preview-api/provider-run` | 只读加载封存的产品抽取结果 |
| `POST` | `/v5-preview-api/fixture-preview` | 不调用外部模型的 fixture 预览 |
| `POST` | `/v5-preview-api/preview` | 已配置 LLM 时执行单次 Schema-guided 预览 |
| `POST` | `/v5-preview-api/search` | 本地字段检索或 LLM 问答 |
| `POST` | `/v5-preview-api/search/stream` | SSE 流式检索/回答 |
| `POST` | `/v5-preview-api/dynamic-field-gapfill` | 已注入补抽服务时做定向补抽 |

`GET /provider-run` 只读取 JSON artifact，不会因为刷新页面再次调用模型。外部调用必须通过明确的运行入口触发，并且 key 只从环境变量注入。

## 4. 核心数据合同

### 4.1 Schema catalog

catalog 定义险种、Schema、字段顺序和字段身份。每个字段至少包含：

- `field_id`：稳定机器键；
- `display_name`：页面显示名；
- `ordinal`：字段顺序；
- `knowledge_role`：事实、关系、内容或衍生；
- `formation_modes`：原文抽取、规则衍生、LLM 生成或外部映射；
- `value_guidance`/`source_guidance`：模型和召回提示；
- `value_constraint`：值类型/枚举/格式约束。

字段拓扑是闭合合同。模型不能新增字段、删字段、改顺序或把一个产品的结果写到另一个产品。

### 4.2 字段三态

每个 Schema 字段必须处于以下状态之一：

| 状态 | 含义 | 证据要求 |
| --- | --- | --- |
| `present` | 原文有明确业务值 | 必须有非空值和至少一条 Evidence |
| `absent_explicitly` | 原文明确写明没有/不适用 | 必须有 Evidence，不得把“没找到”当成该状态 |
| `unknown` | 当前材料尚未形成结论 | 不带业务值；需要 `unknown_reason` 或补抽诊断 |

“候选页没有命中关键词”只能说明召回不足，不能直接生成 `absent_explicitly`。未知、材料未提供、Evidence 无法核验和 Provider 失败要保留可区分的诊断。

### 4.3 Evidence

V5 `CandidateEvidence` 至少记录：

```json
{
  "source_revision_id": "材料版本",
  "locator": "pdf:条款.pdf#page=3",
  "quote": "原文引用",
  "verification_status": "VERIFIED"
}
```

`source_evidence.py` 会把引用回查到已读取的页面，判断是否逐字匹配、归一化匹配、无法定位或多处匹配。Evidence 失败时，候选不能因为“模型给了值”就直接成为可信结果；质量门禁应保留旧值或将字段置为待复核。

### 4.4 Preview

`V5CandidatePreview` 绑定以下身份：

- `catalog_id`、`catalog_sha256`；
- `schema_id`；
- `source_revision_id`；
- `product_id`、`product_version_id`、产品名称；
- `categories` 和完整 `fields`；
- `preview_sha256`。

Preview 是候选预览合同，不等于 Candidate Review、PublishAuthorization 或 Active Release。

## 5. 一次字段抽取的执行顺序

1. `source_manifest.py` 固定允许的产品文件、文件 SHA、页数和来源版本。
2. `material_loader.py` 读取全部页面；扫描页由 `ocr.py` 生成文本和 OCR 回执。读取失败必须留下诊断。
3. `dynamic_ingest.py` 根据字段提示、关键词、同义词和章节信息排序候选页面，构造上下文窗口。候选召回只用于减少上下文，不是字段不存在证明。
4. `field_profiles.py` 和 `value_constraints.py` 生成字段目标、值约束和风险提示。
5. `llm_plugin.py` 向兼容 OpenAI API 的 Provider 发送 Schema-guided 请求，要求只返回闭合字段结果和 Evidence。
6. `ingest.py` 校验模型结果的产品身份、Schema 身份、字段顺序和 Evidence 来源版本。
7. `source_evidence.py` 回到原始页面核验每条 quote/locator。
8. `extraction_completion.py`、`source_supported_completion.py` 对可由原材料支持的缺口做定向补抽；不得用模型概括替代缺失原文。
9. `business_field_quality.py` 和批次质量模块检查重点字段、证据完整性、材料覆盖和候选是否退化。
10. `trial_artifacts.py` 写入带运行 ID、摘要和 SHA 的 JSON artifact；前端只读取该 artifact。

## 6. 表格字段的处理边界

抽取层的 Schema-guided 结果首先是 `CandidateField.value`。如果原材料是表格，模型应把完整表头、行和适用条件保留在值中，不要只生成一句摘要；Evidence 仍要引用原文表格所在页。

前端的 `v5FieldTable.ts` 目前对已支持的投保年龄、契调/体检标准等字段做结构化渲染。新增表格字段时应同时补：

1. 字段值的稳定序列化约定；
2. `v5FieldTable.ts` 的解析器；
3. 解析失败时的文本降级显示；
4. 表格字段的 Preview 合同测试。

不能为了让页面看起来像表格而丢掉原文列、条件或脚注。

## 7. 本地验证和运行

### 7.1 安装依赖

```powershell
Set-Location "<repo>\harness"
uv sync
```

前端依赖：

```powershell
Set-Location "<repo>"
npm ci --prefix frontend
```

### 7.2 只跑本地确定性测试

```powershell
Set-Location "<repo>\harness"
uv run pytest tests/test_v5_* -q
uv run ruff check src/insurance_harness/v5_preview tests/test_v5_*.py
```

前端 V5 相关测试：

```powershell
Set-Location "<repo>\frontend"
npm run type-check
npm run test:unit -- --run src/views/knowledge/schema-wiki/v5-preview
```

### 7.3 仅启动预览 API

```powershell
Set-Location "<repo>\harness"
uv run uvicorn insurance_harness.v5_preview.api:app_factory --factory --host 127.0.0.1 --port 8091
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8091/v5-preview-api/health
```

默认没有配置 Provider 时，fixture 预览和 catalog 仍可用于本地验证；LLM 预览需要通过环境变量提供 `HARNESS_LLM_BASE_URL`、`HARNESS_LLM_API_KEY`、`HARNESS_LLM_MODEL_WEAK` 和 `V5_PREVIEW_LLM_FAMILY`。不要把 key 写进仓库、文档或脚本。

## 8. 旧链路与当前 V5 的区分

`harness/src/insurance_harness/compiler/` 下仍有通用 compiler、章节切分、旧版 checkpoint、judge 和 gapfill 入口。它们是另一条长期编译链，不能因为名字里有 `extract` 就认为最近 V5 产品批次一定经过这里。

判断一个结果属于哪条链，优先看产物合同和入口：

| 线 | 识别方式 | 处理建议 |
| --- | --- | --- |
| V5 预览抽取 | `V5CandidatePreview`、`V5ProviderTrialRun`、`provider-run-*.json` | 从 `v5_preview` 模块排查 |
| 旧 compiler | `pred.jsonl`、`manifest.json`、`checkpoint.sqlite`、`judge-queue.jsonl` | 从 `compiler/` 模块排查 |
| 正式 Wiki/Release | Go Schema Wiki API、Candidate/Review/Release 合同 | 不把 V5 预览直接当发布数据 |

融合时应保持 V5 抽取和证据核验的能力，先设计明确的合同适配，再接入上游任务、Candidate、审核和 Release；不要让两个抽取器同时成为事实来源。

## 9. 修改抽取层前的检查清单

- 是否修改了 `field_id`、字段顺序、Schema SHA 或来源版本？
- 是否把“没有召回”误写成 `absent_explicitly`？
- 是否保留了原文 Evidence，而不是只保留模型摘要？
- 表格值是否保留列、行、条件和脚注？
- Provider 原始响应和调用计数是否仍可审计？
- 质量门禁失败时是否 fail-closed，保留旧结果/待复核状态？
- 变更是否只影响本地预览，还是会触及正式 Candidate/Release？
- 是否新增了相应的契约、Evidence、表格和前端回归测试？

## 10. 延伸阅读

- `docs/insurance-kb/57-current-v5-ingest-core-modules-entry-exit-example.md`：当前 V5 批量入口和完整调用示例。
- `docs/insurance-kb/56-ingest-layer-modularization-and-extraction-architecture.md`：V5 ingest 模块化设计。
- `docs/insurance-kb/42-ingest-extraction-architecture-and-call-chain.md`：V5、平台解析和长期 compiler 的调用链对照。
- `docs/insurance-kb/43-manual-service-startup.md`：本地服务启动和端口排查。
- `harness/src/insurance_harness/v5_preview/contracts.py`：最权威的 V5 字段/Preview 合同。
- `harness/src/insurance_harness/v5_preview/ingest.py`：最权威的 Preview 编译边界。
