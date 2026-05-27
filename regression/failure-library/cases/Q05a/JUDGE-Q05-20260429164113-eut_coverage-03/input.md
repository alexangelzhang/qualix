# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: eut_coverage (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

REQ-003 的审批通过/拒绝(BR-020/BR-021)的 BPM 发起属集成测试范围，但回调后 domain 层状态处理属单测范围（rejected 回调缺 EUT）

