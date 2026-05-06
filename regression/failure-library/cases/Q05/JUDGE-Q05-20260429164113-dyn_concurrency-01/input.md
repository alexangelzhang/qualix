# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_concurrency (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

batchModifyDayCapacity 使用 CompletableFuture 并发执行（EUT-068），但未验证并发写入冲突场景

