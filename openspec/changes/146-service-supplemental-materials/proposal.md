# 146 · 596 服务权益补充材料

## Goal

把用户确认归属于产品 596 的两份“安有医”服务材料接入 V5 试跑，验证服务与权益
字段是否增加，同时保证材料不会改写保险核心事实。

## Owner And Budget

- 唯一写 Owner：当前总控 Codex；执行模型：`gpt-5.6-sol high`。
- OCR：百炼 `qwen-vl-ocr`，只处理 2 页图片 PDF，最多 2 次调用。
- 抽取：百炼 `qwen-plus`，596、5003、1826 最多 7 次调用。
- 本地一个 change set，不创建 PR，不提交或推送 GitHub。

## Frozen Inputs

- 原三款产品 9 份 PDF 保持 M145 身份不变。
- 596 补充 `安有医健康服务手册（尊享版）.pdf`：SHA-256
  `9c9c6343fd0333084345376bec52bf30d2692a7e23ea98fb04a5722a8fa8f8be`，60 页。
- 596 补充 `平安添瑞·安有医（安医保尊享版）一页纸.pdf`：SHA-256
  `fa52b05bcf8561fa82d4c24db34585870a4b014f2315e742a9c43db41f91fead`，2 页。

## Requirements

- `M146-R1`：补充目录必须严格匹配文件名、SHA-256 和页数；文件漂移必须在
  provider 调用前拒绝。
- `M146-R2`：图片页必须经 `qwen-vl-ocr` 得到非空文本并记录模型、页码和文本
  SHA-256；OCR 失败不得静默忽略该页。
- `M146-R3`：补充材料只允许用于 `policyholder_rights`、
  `eligible_service_packages`、`medical_service_benefits`、`product_faq`，不得进入
  险种名称、保险责任、投保和费率等字段上下文。
- `M146-R4`：规则与关键词只负责召回服务页面，LLM 负责语义选择；外部映射字段在
  本次存在受控材料来源时可以进入服务字段补抽，但仍需 Evidence。
- `M146-R5`：补抽返回 unknown、较弱 Evidence 或非法响应时保留 M144 首轮结果；
  不得用补充材料覆盖更强的保险事实。
- `M146-R6`：输出独立
  `provider-run-m146-three-products-supplemental.json`，逐产品比较 M145 的字段增减、
  材料支持条件下抽取率和 Evidence 状态。
- `M146-R7`：仅更新本地 8091/5174；不写生产 DB，不进入 Candidate、Release、
  Active，不执行 GitHub 写入。

## Stop Conditions

- 补充材料无法限定到服务字段，或发现会覆盖 596 核心产品事实；
- OCR 达到 2 次、qwen-plus 达到 7 次仍无法形成完整 artifact；
- 任一历史 provider artifact 可能被覆盖。
