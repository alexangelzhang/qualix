# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_concurrency (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

EUT-039/045 验证了 BPM 回调幂等（相同 processInstanceId 重复回调），但未验证两个不同审批人同时审批的并发场景（SE-013 的核心语义）

