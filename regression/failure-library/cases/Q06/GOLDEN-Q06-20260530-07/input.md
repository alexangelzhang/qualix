# Golden Sample — AUDIT-031

- 项目: failure-cause (sfp-fault-service)
- Phase: Q06
- 审计状态: PARTIAL

## 审计项描述

queryFaultBrandClassSkuByTime 无故障原因数据时返回空列表

## 实际发现

补充 assertTrue(result.getData().isEmpty()) 确认无数据时返回空列表而非 null

## EUT ID

EUT-031
