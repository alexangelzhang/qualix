# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_state_machine (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

工单主状态机（待申请结算→待支付→部分支付等）的流转未被 EUT 直接验证，仅通过 EUT-034 间接验证'不改变主状态机'

