# Judge 提取的 Bug Case

- 项目: kind-care
- Phase: Q01
- 维度: se_explicitness (3/5)
- 时间: 2026-04-22T14:40:47.845440

## 问题描述

未提取超时/降级SE：BPM审批系统不可用时善意关怀提交的降级策略

## 证据

涉及外部系统调用(BPM/积分发放)，应有降级SE
