# 审计报告模板

## 审计总览

- 审计范围：`<current_branch> vs <base_branch>`
- 架构类型：`DDD | TMF | DDD+TMF`
- 需求点数量：`<N>`
- 关键语义数量（SEM）：`<N>`
- 场景总数：`<N>`
- 覆盖状态统计：`COVERED/PARTIAL/MISSING/WRONG_TARGET`
- 分层结果：`Client/Application/Domain/Infrastructure/Spec/Step/Ability`
- 覆盖率门禁：`line=<x>% branch=<y>% gate=PASS/FAIL`
- 变异测试：`mutation_score=<x>% survived_critical=<n> survived_exempt=<n> status=PASS/FAIL`
- 结论：`PASS | PASS_WITH_RISKS | FAIL`
- 度量快照（可选）：`WRONG_TARGET=<n> T1_MISSING=<n> NEEDS_CONTEXT=<n> ingest_OK=<true|false>`

## 场景覆盖矩阵

| ReqID | 场景ID | 风险层级(T1/T2/T3) | 架构层 | 场景描述 | 代码点 | 测试用例 | 覆盖状态 | 风险级别 | 证据 |
|-------|--------|------------------|--------|---------|--------|---------|---------|---------|------|

## 关键语义矩阵

| SEM ID | 来源(文本/图片) | 关联 Req/BR | 规则定义 | 代码证据 | UT | EUT | 覆盖状态 |
|--------|--------------|-----------|---------|---------|-----|-----|---------|

## 分层职责-用例映射矩阵

| 层级 | 期望职责 | 必测场景 | 测试用例 | 覆盖状态 | 备注 |
|------|---------|---------|---------|---------|------|

## TMF 编排专项矩阵（若适用）

| 场景ID | 编排节点（decide/execute/step/ability） | 正向/反向 | 当前断言 | 覆盖状态 | 备注 |
|--------|--------------------------------------|---------|---------|---------|------|

## 异常分支断言矩阵

| 场景ID | 异常类型 | 期望业务结果 | 当前断言 | 断言充分性(OK/不足) | 备注 |
|--------|---------|------------|---------|-----------------|------|

## Mapper/Service 断言 checklist 结果

- 模板路径：`templates/mapper_service_assertion_checklist.md`
- 填写状态：`已填写/未填写`
- 未通过项：`<item>`

## 重点风险（Top 5）

`[SEVERITY] <ReqID/场景ID> <风险一句话> | 影响: <业务影响> | 缺口: <漏测点> | 建议: <补测方向>`

## 补测建议（按需求表达）

使用 Given-When-Then：

`<场景ID> Given <前置> When <触发> Then <业务结果>`

## 自我评审记录

（Judge/Critique 发现的问题记录在此）
