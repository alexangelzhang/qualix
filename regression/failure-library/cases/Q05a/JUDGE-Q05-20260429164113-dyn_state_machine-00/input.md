# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_state_machine (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

SubProcess 状态机覆盖了 WAIT_APPROVE/APPROVED/REJECTED/CANCELLED 四个状态，但 CANCELLED（撤销）的触发需调 BPM API 属集成测试范围，单测仅需验证撤销后 SubProcess 状态变更逻辑

