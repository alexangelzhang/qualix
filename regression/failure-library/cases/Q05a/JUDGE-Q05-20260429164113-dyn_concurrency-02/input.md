# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_concurrency (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

applyEarlyDeliveryAuthStore 的幂等控制（EUT-002）仅验证了串行重复提交，未验证并发提交的竞态条件

