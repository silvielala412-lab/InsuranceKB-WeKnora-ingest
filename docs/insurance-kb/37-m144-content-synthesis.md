# Mission 144：产品简介与产品概览补抽

## 结论

`产品简介` 和 `产品概览` 不是前端丢失，而是原先只参加首轮大批量抽取。它们属于纯
`LLM生成` 字段，被材料支持和普通 PDF 补抽资格过滤掉；首轮返回 `unknown` 后没有第二次
机会。M144 增加了独立的内容总结目标集：目标字段使用全部 PDF 页面的有序上下文，并接收
首轮已验证事实作为辅助上下文。

内容字段可以生成总结文本，但仍必须给出支撑性逐字 Evidence；材料不足时保留 `unknown`。
这两个字段仍不纳入材料支持抽取率分母。

## 验证

- RED：实现前测试因缺少 M144 内容目标入口而失败。
- GREEN：23 项 Python/V5 回归测试、9 项前端契约测试、ruff、compileall 均通过。
- Provider：本 Mission 未调用外部模型，未覆盖 M143 结果文件。
- 外部状态：未写生产 DB，未进入 Candidate/Release/Active，未提交或推送 GitHub。

## 下一次真实试跑

需要重新调用 provider 才能看到两个字段的实际生成效果。建议使用独立的
`provider-run-m144-content-synthesis.json`，保留 M143 artifact，并单独比较：

1. 两个字段的 `present / unknown` 比例；
2. Evidence 的逐字和页码验证率；
3. 事实字段相对 M143 是否回退；
4. 内容总结是否引入材料外事实。
