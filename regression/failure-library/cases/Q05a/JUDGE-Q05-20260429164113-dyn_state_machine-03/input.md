# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_state_machine (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

BPM 回调后 SubProcess 从 WAIT_APPROVE→APPROVED 和 WAIT_APPROVE→REJECTED 两条迁移路径，后者无 EUT

