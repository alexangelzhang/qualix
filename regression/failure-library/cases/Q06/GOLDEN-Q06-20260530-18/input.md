# Golden Sample — AUDIT-047

- 项目: failure-cause (sfp-fault-service)
- Phase: Q06
- 审计状态: WRONG_TARGET

## 审计项描述

getFaultDetailById 故障原因启用时返回结果

## 实际发现

补充调用 getFaultDetailById 并验证响应中 faultReasonName 等字段不为空

## EUT ID

EUT-047
