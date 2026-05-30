# Golden Sample — AUDIT-024

- 项目: demo-project
- Phase: Q06
- 审计状态: WRONG_TARGET

## 审计项描述

queryFaultInfoList 有效参数调用 repository 查询

## 实际发现

替换为对 queryFaultInfoList 返回值的业务断言，如 assertNotNull(result.getData()) 并验证 repository mock 被调用

## EUT ID

EUT-024
