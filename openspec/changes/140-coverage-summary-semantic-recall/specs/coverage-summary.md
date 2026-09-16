# M140 保什么语义召回规格

## M140-R1 全材料候选

### Scenario: 不依赖固定文件名

- Given 一个产品的多个 PDF 页面，文件名可以任意变化
- When 构建 `coverage_summary` 候选上下文
- Then 所有页面先被扫描，文档名只出现在 locator/上下文标签中，不参与路由判断

### Scenario: 非标题式责任表达

- Given 页面只出现“我们承担……、给付……、保险金……”等责任语义
- When 构建 `coverage_summary` 候选上下文
- Then 页面进入候选，即使没有“保什么”或“主要保单利益”标题

## M140-R2 语义汇总

### Scenario: 跨页跨文件合并

- Given 保障项目分散在多个页面或多个 PDF
- When LLM 抽取 `coverage_summary`
- Then 返回覆盖项目的完整汇总，保留触发条件/限制，并给出逐字 Evidence

### Scenario: 审核不吞值

- Given value 已由原文候选支持，但某条 Evidence 暂不能定位
- When 合并或审核候选
- Then 不把 value 改成空值；标记为待核验，供后续人工复核

## M140-R3 非退化

### Scenario: 现有字段不回退

- Given 同一三产品样本和现有 V5 Schema
- When 运行 M140
- Then 除 `保什么` 外的字段有值率不低于 M139 对应结果，且 `险种简称` 保持 3/3
