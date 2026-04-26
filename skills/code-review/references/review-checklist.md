# 代码评审 Checklist

## 依赖新增审查（Dependency Discipline）

当 diff 中出现新的 `import`、`pom.xml` 依赖、`go.mod` require 时，必须回答以下 5 个问题：

| # | 问题 | 不通过的处理 |
|---|------|------------|
| 1 | 现有技术栈能否解决这个问题？ | 标 `[MAJOR]` 建议用现有方案替代 |
| 2 | 这个依赖的体积/复杂度是否合理？ | 标 `[MAJOR]` 如果引入了重量级框架解决简单问题 |
| 3 | 是否活跃维护？（最近 6 个月有 commit） | 标 `[MINOR]` 提醒维护风险 |
| 4 | 是否有已知安全漏洞？ | 标 `[BLOCKER]` 如果有未修复的 CVE |
| 5 | License 是否兼容？ | 标 `[BLOCKER]` 如果 License 不兼容 |

## 变更拆分策略

当变更过大时建议：
- **按功能垂直切**：一个完整功能路径（API→Service→Domain→Gateway）为一个 PR
- **按文件组切**：模型变更 / 业务逻辑 / 配置变更分开
- **重构与功能分离**：纯重构（rename/move）和功能变更不混在一起

## Java 代码评审重点

### 并发安全
- 写操作是否有分布式锁或乐观锁保护
- 幂等键设计是否合理
- 重复请求的返回语义是否明确

### 金额处理
- 金额字段必须使用 BigDecimal，禁止 double/float
- 精度设置是否正确（精确到分 = scale 2）
- 四舍五入策略是否明确

### 事务边界
- @Transactional 注解是否在正确的层（Application/CmdExe，不在 Domain）
- 事务内是否有外部 RPC 调用（可能导致长事务）
- 事务回滚条件是否正确（rollbackFor）

### DDD+TMF 链路
- Provider 层是否有参数校验和幂等拦截
- CmdExe 是否只做编排，不含业务规则
- Domain 层是否通过 Gateway 接口隔离外部依赖
- TMF Step 是否通过 `TMF.findAbility()` 调能力，禁止直接注入

### 异常处理
- catch 块是否有实质性处理（不能只打日志）
- 业务异常是否有正确的错误码
- 外部调用是否有超时配置和降级策略

## 评审报告模板

```markdown
# 代码评审报告

## PROFILE_CONTEXT
- 项目: <project_id>
- 分支: <feature_branch> vs <base_branch>
- 架构类型: DDD+TMF / DDD / 其他

## CALL_CHAIN
### 功能点 1: <功能名>
Provider → CmdExe → DomainService → Step(xxx) → Ability(xxx) → Gateway

## 问题清单

### [BLOCKER] 文件:行号
- 风险说明: ...
- 修复建议: ...
- 证据: ...
- 链路位置: [链路: Provider → CmdExe → ...]

## REQ/BR/SE → CODE/TEST 覆盖缺口

| REQ/BR/SE ID | 描述 | 代码覆盖 | 测试覆盖 | 缺口说明 |
|-------------|------|---------|---------|---------|

## 结论

STATUS: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT

## 自我评审记录
（Judge/Critique 发现的问题记录在此）
```
