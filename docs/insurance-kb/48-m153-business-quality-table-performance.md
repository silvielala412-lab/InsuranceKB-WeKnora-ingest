# Mission 153：业务问题纠偏、表格感知与单次运行提速

## 本轮范围

本轮只做本地代码和离线验收：不调用百炼，不外发 PDF，不写生产库，不改
8091/5174 的业务结果，不提交或推送 GitHub。四份业务问题表只读，原文件没有被
修改。

## 已处理

1. **业务问题变成可检查的数据**

   新增 `harness/src/insurance_harness/v5_preview/m153_quality.py`。解析四份
   `E:\wiki badcase ly` 工作簿的 `Sheet1`，保留工作簿 SHA、产品 ID、sheet、行号、
   字段名、问题备注和嵌入图片 SHA。问题类型统一为：
   `missing / incomplete / wrong / summary_incomplete / summary_wrong / display_only /
   schema_gap`。一行有多个问题时全部保留。

   离线结果：49 条业务记录，47 条能映射到 v5 字段，2 条明确保留为 Schema gap；
   4 个工作簿共有 18 个嵌入图片资产。图片没有被当成标准答案，当前只作为待人工
   确认或后续 OCR 的参考资产。

2. **先保住正确值，再处理问题值**

   `compare_field_value` 提供字段级确定性比较：候选变 unknown、Evidence 变弱、
   缺少必含事实、出现禁含事实或不满足允许值时，分别保留基线或标记
   `regression`；新值与基线冲突时标记 `needs_review`，不自动覆盖。

   M152 的问题批次现在会跳过纯 `display_only` 记录；混合了抽取错误/不完整的问题
   仍会进入复核。提示中只传问题类型，不把业务备注里的标准答案注入生产抽取
   Prompt。

3. **表格页保留位置**

   `TablePage` 保留文档、页码、表序号、表头、行号和列号，
   `extract_pdf_tables` 和 M152 的单次 PDF 加载会记录表格提取成功、无表格或失败。
   表格提取失败时仍保留原页面文本。

   费率表不再无条件塞进所有字段：只有金额、缴费、领取、费率、减保等语义字段
   才追加表格行；产品简介等普通字段会排除费率表页面，避免长表格挤占上下文。

4. **同次运行减少重复工作**

   M152 的材料对象新增同次运行内的候选和上下文内存索引，键为产品险种和有序字段
   集合；同一批次再次请求时直接复用。上下文按行去重，索引不落盘，也不跨运行
   复用。`RunExtractionIndex.context_with_receipt` 可输出字符数、页数、重复页数、
   候选构建次数和构建耗时。

   同时提供 `plan_bounded_batches`，并发上限硬限制为 2，批次按原始顺序生成，后续
   可由 `execute_bounded_batches` 执行并按 batch index 稳定合并。本轮没有调用模型
   验证并发吞吐。

   121 页离线合成样本（1 页含目标等待期，120 页为长费率表）对比旧上下文构建：
   旧上下文 59,924 字符，新上下文 199 字符，目标候选仍为 `1 -> 1` 且目标原文仍在；
   构建时间本机一次观测为 `187.221ms -> 103.268ms`，同一字段集合再次读取为
   `0.002ms`。这是代码路径基准，不是实际产品/provider 性能结论。

## 离线验收

- Mission 153 新增测试：`9 passed`。
- 全部 V5 测试：`49 passed`；其中与 M148、M151、M152 组合的定向回归为
  `25 passed`。
- Ruff：本轮文件 `All checks passed`。
- compileall：通过。
- M152/M153 两个本轮相关模块严格 mypy：通过。
- 全量 pytest 在 Windows 收集阶段被已有 `fcntl` 缺失和 pytest 临时目录权限阻断，
  不能据此推导业务失败。

## 对费率表与 Schema 的结论

费率表页数长本身不是 Schema 字段变少的直接原因，真正的问题是表格被当成长文本
后，行列关系丢失，且无关表格占用模型上下文。现在已把表格转换为带位置的结构，
并按字段语义路由。这样能改善费率、缴费、领取、金额等字段的定位；它不会凭空给
没有原文的字段造值，也不会自动修正嵌入截图中的标准答案。下一轮真实重跑后，应
分别统计表格字段召回、Evidence 定位和最终业务准确率，不能只看字段 present 数。

## 当前状态

本轮 `software=PASS`；`provider probe / container health / provisioning / local live /
GitHub live=NOT RUN`；`BUSINESS=NOT RUN`。没有真实模型调用，因此不能宣称抽取率、
准确率或线上速度已经提升；本轮交付的是可回归、可定位、可复用的代码基础。
