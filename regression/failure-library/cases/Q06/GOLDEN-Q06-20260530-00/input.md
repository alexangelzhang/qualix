# Golden Sample — AUDIT-019

- 项目: demo-project
- Phase: Q06
- 审计状态: PARTIAL

## 审计项描述

invokeFaultBpmCallback 入参为 null 时提前返回，不触发后续处理

## 实际发现

补充对 Result.fail 返回码的断言，确认方法返回业务失败语义而非静默 null

## EUT ID

EUT-019
