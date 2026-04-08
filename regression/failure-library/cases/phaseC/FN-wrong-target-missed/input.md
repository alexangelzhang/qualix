# 触发输入

## 代码片段

```java
@Test
public void testCreateOrder() {
    OrderDTO dto = new OrderDTO();
    dto.setSkuId("SKU-001");
    dto.setQuantity(1);

    OrderResult result = orderService.createOrder(dto);

    assertNotNull(result);  // 仅验证不为 null
}
```

## Phase A 产物（SE 片段）

- SE-001: 下单成功后，订单状态应为 CREATED，订单金额应等于商品单价 × 数量

## 期望输出

EUT-001 审计状态: **WRONG_TARGET**
- 测试存在但断言过弱：仅 `assertNotNull(result)`，未验证 `result.getStatus() == CREATED` 和 `result.getAmount() == price * qty`

## 实际输出

EUT-001 审计状态: **COVERED**
- 因为 `testCreateOrder` 方法名匹配了下单场景，就判定为已覆盖
