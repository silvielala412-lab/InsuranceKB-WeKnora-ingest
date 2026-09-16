# Mission 150 · 两款重疾险本地抽取结果

## 结果

- 新增产品：1828 `平安安佑福（全能版）重大疾病保险`、L2332 `平安个人重大疾病保险`。
- 输入：6 份 PDF，共 98 页；运行前完成 metadata、文件集合、SHA-256、页数、产品身份和 Schema 67 校验。
- 独立 artifact：`provider-run-m150-serious-illness.json`。
- 新 run：`v5-trial-701cb35731058b68`，最终 artifact 记录 4 次 `qwen-plus` 调用；两款均有合法 Preview，均为 `REVIEW_REQUIRED`。
  首次 runner 在连续网络失败时暴露失败态合同问题并消耗 2 次调用，修复后重跑使用剩余 4 次；Mission 150 外部调用总数为 6，未超批准上限。
- 合并 artifact：`provider-run-m150-eight-types.json`，run
  `v5-trial-5b733975961c29a8`，SHA-256
  `dd759dbc02548d0951bf255d5aa27d756764f4794fd7382758eb10c3fdda2b69`。
  合并后 8 款产品、7 个险种；M149 原六款 payload canonical bytes 未改变。

## 抽取概况

| 产品 | Schema 字段 | 已有值 | unknown | 材料支持字段 | 支持字段中已抽取 | 材料支持条件下抽取率 |
|---|---:|---:|---:|---:|---:|---:|
| 安佑福（全能版）1828 | 67 | 40 | 23 | 23 | 18 | 78.26% |
| 平安个人重大疾病保险 L2332 | 67 | 40 | 25 | 17 | 17 | 100.00% |

这里的“材料支持条件下抽取率”按本项目约定计算：材料支持且抽出的字段 / 材料支持字段。
它不是模型准确率；本 Mission 没有为重疾险冻结 Golden，因此准确率不宣称已评估。

## 服务验证

- `software`：PASS，Mission 150 定向测试 3 passed；M139 兼容测试 2 passed；模块编译通过。
- `container health`：NOT RUN，本次使用本地进程，不涉及容器镜像。
- `provider probe`：PASS，最终 artifact 的 4 次真实 `qwen-plus` 调用使 2/2 产品生成 Preview；连同失败态修复前的 2 次调用，Mission 总数为 6，未超过批准上限。
- `provisioning`：NOT RUN，无 migration、backfill、生产配置或数据库写入。
- `local live`：PASS，8091 和 5174 均返回 run `v5-trial-5b733975961c29a8`、8 款产品、7 个险种；5174 `/v5-preview` 返回 200。
- `GitHub live`：NOT RUN，未提交、推送或创建 PR。

`serving_effect=NONE`、`review_publish_admission=false` 保持不变；本结果仅供本地预览和后续字段审核。
