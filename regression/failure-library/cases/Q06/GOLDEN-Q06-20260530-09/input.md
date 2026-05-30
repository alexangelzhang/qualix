# Golden Sample — AUDIT-033

- 项目: failure-cause (sfp-fault-service)
- Phase: Q06
- 审计状态: WRONG_TARGET

## 审计项描述

queryFaultMetaByStep 负数 parentId 参数返回错误

## 实际发现

补充 assertNotEquals(0, result.getCode()) 或异常类型断言

## EUT ID

EUT-033
