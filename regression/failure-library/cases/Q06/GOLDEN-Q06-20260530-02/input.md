# Golden Sample — AUDIT-025

- 项目: demo-project
- Phase: Q06
- 审计状态: WRONG_TARGET

## 审计项描述

queryFaultMetaByStep 全null参数时返回 fail

## 实际发现

补充对 result.getCode() 非0或 result.isError() 的业务断言

## EUT ID

EUT-025
