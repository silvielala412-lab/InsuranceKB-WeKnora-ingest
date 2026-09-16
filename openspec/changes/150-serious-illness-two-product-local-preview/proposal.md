# 150 · 两款重疾险本地预览

## Goal

在保留 Mission 149 六款本地结果的前提下，接入两款独立重疾险材料，验证当前
Schema 67 的抽取链路，并把结果追加到本地预览。新结果和 M149 均保留，任何
失败都不能伪装成成功。

## Owner And Budget

- 唯一写 Owner：当前总控 Codex；执行 effort：`high`。
- 新增产品：1828、L2332；共 6 份 PDF、98 页。
- Provider：百炼 `qwen-plus`，最多 6 次调用；每款最多 2 次抽取尝试。
- 只写当前 worktree 的代码、独立 artifact、合并 artifact 和本地服务配置；不提交或推送 GitHub。

## Frozen Inputs

- 现有基线：`provider-run-m149-six-types.json`，不得覆盖。
- 1828：`平安安佑福（全能版）重大疾病保险`，metadata SHA-256
  `6842f82ada88bc4780a227633a96bbff793411875068898a99e65b7f7486aac6`；PDF
  SHA-256 以代码白名单和运行前 preflight 为准。
- L2332：`平安个人重大疾病保险`，metadata SHA-256
  `c26c39d72186e6c13ebc351e9cf87b7f9598adcb58d7846936abcad9f880e228`；PDF
  SHA-256 以代码白名单和运行前 preflight 为准。
- 输入根目录：`D:\pa code\pythonproject\insurance product pa\平安人寿产品文件`。

## Requirements

- **M150-R1**：Provider 调用前严格校验两款产品的 metadata、文件名、SHA-256 和页数；漂移时零调用。
- **M150-R2**：仅调用 1828、L2332，使用 `qwen-plus`，总调用不超过 6 次，并保留每次尝试回执。
- **M150-R3**：新结果写入 `provider-run-m150-serious-illness.json`，不得覆盖 M149 或历史结果。
- **M150-R4**：合并预览保留 M149 六款 product payload 的 exact canonical bytes，追加两款重疾险；产品总数 8，险种去重数 7。
- **M150-R5**：合并 artifact 通过现有 loader 和 digest 校验后，才更新本地 8091；5174 可切换并显示两款重疾险。
- **M150-R6**：`serving_effect=NONE`、`review_publish_admission=false`；不写生产 DB，不形成 Candidate、Release 或 Active。

## Stop Conditions

- 任一冻结输入身份漂移，或 preflight 不通过；
- 6 次调用用尽仍有产品没有合法 Preview；
- 合并改变 M149 canonical payload，或 artifact 无法通过既有合同；
- 需要修改生产发布链、生产数据库或 GitHub 状态。
