# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_state_machine (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

工单回退场景（EUT-043）仅验证了 statusDataList 展示，未验证回退后 SubProcess 状态的保持逻辑

