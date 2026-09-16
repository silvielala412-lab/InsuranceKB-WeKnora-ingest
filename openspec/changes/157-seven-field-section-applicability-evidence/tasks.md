# Mission 157 Tasks

- [x] M157-R1 至 M157-R5 与冻结 identity/边界已记录。
- [x] RED：长字段单字段批次与 20 次主调用旧实现失败。
- [x] RED：一段证据支持多个原子项、主附险适用范围及 Evidence 重定位旧实现失败。
- [x] 实现字段章节上下文、M157 审核/定位和可配置六产品运行器。
- [x] 运行焦点与回归测试，记录 Requirement 对应结果。
- [x] 最多 24 次 qwen-plus 重跑六款并生成独立 result/audit。
- [x] 与 M156 逐字段和业务 badcase 对比；验证材料支持口径及无回退。
- [x] 更新 8091/5174，记录前后端 live probe。

## RED 与验证回执

RED 在旧树收集阶段以
`ModuleNotFoundError: insurance_harness.v5_preview.m157_quality` 失败。实现后，worktree
内独立 `--basetemp` 下全部 71 个 `test_v5_*.py` 测试通过；Ruff 通过；M157 两个模块
在 `--follow-imports=skip` 下 mypy 通过。Windows 全仓 pytest 仍会在无关旧模块收集时因
Unix `fcntl` 缺失失败，不计作 M157 RED 或回归失败。

真实运行产物为 `provider-run-m157-six-products-quality.json` 及配套 audit。run 为
`v5-trial-1c12e53f0011f760`，run SHA 为
`b00fc0daa029e07c3f106de6387af4a144c4338d8fca2a482af3e13fb3038247`。24/24 次
qwen-plus 中，20 次主调用与 3 次质量补抽得到 20 个合格返回；1816/1828 疾病定义和
596 质量补抽因 `finish_reason=length` 截断，1828 短字段批次网络失败。失败字段均保留
M156 基线。材料支持抽取率保持 `133/143=93.01%`，接受 4 个值变化。

## Requirement Matrix

| Requirement | Implementation / receipt | Status |
|---|---|---|
| M157-R1 | `m157_quality.py` 单长字段批次；六款主调用 20 次 | PASS |
| M157-R2 | 原子项逐项语义支持，不再按 Evidence 条数误拒 | PASS |
| M157-R3 | 当前产品作用域提示与附加险主险权益拒绝；1814/1816 权益得到纠偏 | PASS |
| M157-R4 | exact/normalized 后的唯一高置信重定位；重复页仍 fail closed | PASS |
| M157-R5 software | 71 个 V5 测试、Ruff、M157 mypy | PASS |
| M157-R5 provider | 24/24 次；6 款均有终态，失败字段保留基线 | PASS |
| M157-R5 quality | 133/143=93.01%，无抽取率回退；正式准确率缺完整 Golden | BLOCKED |
| M157-R5 local live | 8091/5174 返回 exact M157 run，HTTP 200 | PASS |

`BUSINESS=BLOCKED`：两处附加险权益纠偏明确有效，免责字段有结构/覆盖改善，但抽取率
没有增加；疾病定义的枚举规模仍超过单次 32K 输出上限，业务工作簿也不足以自动计算
正式准确率。下一步若继续，应把疾病定义改为“章节分片 -> 原子项 JSON -> 确定性去重
合并”，而不是提高单次输出上限或放宽 Evidence 审核。
