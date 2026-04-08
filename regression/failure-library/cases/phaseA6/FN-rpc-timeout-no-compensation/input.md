# 触发输入

## 技术方案片段

> 5.2 下单核心流程
>
> 1. 调用库存服务扣减库存 `InventoryService.deduct(skuId, qty)`
> 2. 创建订单记录 `OrderRepository.save(order)`
> 3. 发送下单成功消息 `MQ.send("order.created", orderId)`

## 期望输出

Failure Mode 分析应识别：

- 业务路径: 下单核心流程
- 故障场景: 步骤 1 成功（库存已扣）但步骤 2 失败（订单未创建）
- 状态: **CRITICAL_GAP** — 无补偿机制，库存泄漏
- 建议: 引入 Saga 补偿或本地事务表

## 实际输出

Failure Mode 分析中该路径标记为 SAFE，未识别跨服务调用的部分失败场景。
