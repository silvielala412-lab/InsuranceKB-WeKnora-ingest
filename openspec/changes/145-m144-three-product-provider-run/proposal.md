# 145 · M144 三款产品真实 provider 验证

## Goal

验证 M144 的产品简介、产品概览内容总结 pass 在三款既有保险产品上的真实效果。

## Boundary

- 产品：596、5003、1826；共 9 份已冻结 PDF。
- Provider：百炼 `qwen-plus`，最多 6 次调用，每款最多 2 次。
- 输出：独立 `provider-run-m144-three-products.json`，不覆盖历史 artifact。
- 仅本地预览，不写生产 DB，不进入 Candidate/Release/Active，不提交或推送 GitHub。

## Acceptance

- run 完成或明确记录部分结果及调用回执；
- 统计 `product_summary`、`product_overview` 的 present/unknown 和 Evidence 验证状态；
- 核对事实字段相对 M143 是否回退；
- 8091/5174 只在 artifact 完整后指向本轮结果并通过 live probe。
