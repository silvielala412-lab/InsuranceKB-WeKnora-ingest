# 124 · Nine-product V5 extraction evaluation

## Goal

将现有三产品 V5 本地试跑扩展为九产品固定评测，覆盖医疗险、终身寿险、两全保险、
年金险、意外险和失能收入损失保险六类 Schema。用同一抽取策略观察跨产品、跨险种
的字段覆盖、候选召回、Evidence 和运行稳定性。

## Owner

- 唯一写 Owner：当前总控 Codex
- 执行模型：`gpt-5.6-sol high`
- 预计 PR：0；只在当前本地二次开发 worktree 执行

## Frozen Input

- 原三款产品及 M137/M138 结果保持不变；
- 新增惠享版长期医疗、爱满分两全、盛世金越普通型终身寿、至尊版年金、附加意外、
  附加失能六款产品；
- 每款冻结 `product_meta.json`、3 份 PDF、文件 SHA-256、页数、产品版本和险种；
- V5 Catalog identity 保持不变。

## Requirements

- `M139-R1`：后端必须接纳且只接纳冻结的九款产品，逐文件校验 hash 和页数。
- `M139-R2`：标准自适应路径每款最多首轮加一次定向补抽，总调用不超过 18 次。
- `M139-R3`：前端合同必须接纳九产品、18 次调用，并继续拒绝越界结果。
- `M139-R4`：结果写入独立 M139 artifact，不覆盖 M137/M138。
- `M139-R5`：报告按产品和险种分别给出字段有值率、材料支持口径、候选页口径、
  Evidence 状态和原三款稳定性；没有专家 Golden 时不得称为准确率。
- `M139-R6`：8091 返回 exact M139 run，5174 页面可读取九款结果。

## Non-goals

- 不修改 V5 Schema 字段定义；
- 不实现无 Schema 发现；
- 不写数据库、Candidate、Release 或 Active；
- 不提交或推送 GitHub；
- 本轮失败后只给优化建议，不自动追加模型调用。

## Stop Conditions

- 样本 hash、页数、产品身份或 Schema 映射漂移；
- Provider 达到 18 次上限；
- 任何旧 M137/M138 文件被修改；
- 需要数据库、生产部署、第二套结果 authority 或额外外发范围。
