# Golden Sample — AUDIT-030

- 项目: demo-project
- Phase: Q06
- 审计状态: WRONG_TARGET

## 审计项描述

updateBaseFaultInfo BPM服务异常时返回 fail

## 实际发现

将断言改为 assertTrue(result.isError()) 或 assertNotEquals(0, result.getCode())

## EUT ID

EUT-030
