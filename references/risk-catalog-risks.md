# 风险分类目录（Java DDD+TMF）— R-* 类型

> Q01/Q02/Q03 使用。每个类型含：触发条件、代码信号、判定规则。

---

## R-AMB: 需求歧义/验收口径不一致

**触发条件**：PRD 用「大概」「可能」「适当」等模糊词；同一概念不同章节定义不同；验收标准缺具体数值

**判定规则**
- 技术方案出现 TODO/TBD/待确认 → R-AMB
- 接口入参/出参枚举值未穷举 → R-AMB
- 状态迁移条件用自然语言而非明确前置条件 → R-AMB

---

## R-STATE: 状态机缺口/非法迁移

**触发条件**：领域对象有状态字段但未画状态机图；存在跳跃迁移；并发场景下两个操作同时触发状态迁移

**代码信号**：`enum XxxStatus`；`if (status == A) { status = B; }` 无前置校验；缺少 `@Version`

**判定规则**
- 状态枚举值 > 3 但无状态机文档 → R-STATE
- 状态迁移方法无前置状态校验 → R-STATE (CRITICAL)
- 状态迁移无并发保护 → R-STATE + R-CONCUR

---

## R-IDEMP: 幂等与重复请求

**触发条件**：用户重复点击；MQ 重复投递；定时任务重复触发；RPC 超时重试

**代码信号**：写操作无 `@Idempotent` 或幂等 key；INSERT 无唯一约束；MQ Consumer 无消费去重表

**判定规则**
- 写接口无幂等设计说明 → R-IDEMP
- 技术方案提到「重试」但未说明幂等策略 → R-IDEMP
- 金融/支付类操作无幂等 → R-IDEMP (CRITICAL)

---

## R-CONCUR: 并发竞争/锁冲突

**触发条件**：库存扣减、余额变更等热点资源并发写；同一聚合根被多线程同时修改；分布式锁获取失败后降级策略缺失

**代码信号**：`synchronized`/`ReentrantLock`；`@Version`；`RedissonClient.getLock()`；`UPDATE ... WHERE amount >= #{qty}`

**判定规则**
- 热点资源写操作无任何并发控制 → R-CONCUR (CRITICAL)
- 有乐观锁但无重试策略 → R-CONCUR
- 分布式锁无超时释放机制 → R-CONCUR

---

## R-CONSIST: 跨服务数据一致性

**触发条件**：扣库存+创建订单跨两个服务；主表写成功但从表写失败；RPC 调用成功但本地事务回滚

**代码信号**：同一方法内调用多个 RPC/Gateway；`@Transactional` 内包含 RPC；无 Saga/TCC/本地事务表/消息事务

**判定规则**
- 跨服务写操作无补偿/回滚机制 → R-CONSIST (CRITICAL)
- `@Transactional` 内嵌套 RPC 调用 → R-CONSIST
- 技术方案提到「分布式事务」但未说明具体方案 → R-CONSIST

---

## R-DEPEND: 外部依赖失败/超时

**触发条件**：下游服务不可用；第三方 API 超时；中间件连接失败

**代码信号**：RPC 调用无 timeout 配置；无 `@HystrixCommand`/`@SentinelResource`；catch 块吞异常后返回 null

**判定规则**
- RPC 调用无超时配置 → R-DEPEND
- 无降级/熔断策略 → R-DEPEND
- 核心链路依赖非核心服务且无降级 → R-DEPEND (CRITICAL)

---

## R-OBS: 可观测性不足

**触发条件**：关键业务操作无日志；异常被 catch 但未记录；无 metrics 埋点

**代码信号**：`catch (Exception e) { }` 空 catch；`catch (Exception e) { return null; }`；关键方法无 `log.info/warn/error`

**判定规则**
- 写操作无审计日志 → R-OBS
- 异常分支无 log.error → R-OBS
- 核心链路无 RT/成功率监控 → R-OBS

---

## R-PERM: 权限与数据越权

**触发条件**：用户 A 可操作用户 B 的数据；接口未校验操作者身份；批量接口未做数据归属校验

**代码信号**：查询/更新 SQL 无 `WHERE user_id = #{currentUserId}`；Controller 无 `@RequiresPermissions`；批量操作未逐条校验归属

**判定规则**
- 写接口无操作者身份校验 → R-PERM (CRITICAL)
- 查询接口可通过 ID 遍历获取他人数据 → R-PERM
- 批量导出无数据范围限制 → R-PERM

---

## R-PERF: 性能与资源瓶颈

**触发条件**：循环内执行 RPC/SQL（N+1）；全表扫描无索引；无分页的列表查询

**代码信号**：`for (item : list) { dao.query(item.getId()); }`；`SELECT * FROM table` 无 WHERE/LIMIT；大对象序列化

**判定规则**
- 循环内 RPC/SQL 调用 → R-PERF
- 列表查询无分页 → R-PERF
- 技术方案未评估数据量级和 RT 目标 → R-PERF

---

## R-SEM: 关键业务语义遗漏或实现偏差

**触发条件**：排序规则与 PRD 不一致；聚合计算精度丢失；去重逻辑遗漏；时效判断边界错误

**代码信号**：`double` 用于金额计算；`Collections.sort()` 无自定义 Comparator；`distinct()` 字段不完整

**判定规则**
- 金额/比例计算用 double/float → R-SEM (CRITICAL)
- 排序/去重/聚合逻辑与 PRD 不一致 → R-SEM
- 时间比较未考虑时区 → R-SEM

---

## R-STABLE: 关键语义稳定性不足

**触发条件**：同一输入多次执行结果不同；重复执行产生额外副作用；跨批次处理结果不一致

**代码信号**：`HashMap` 用于需要稳定顺序的场景；`Math.random()` 影响业务逻辑；无幂等保护的批量处理

**判定规则**
- 业务结果依赖集合遍历顺序但用 HashMap/HashSet → R-STABLE
- 重复执行同一请求产生不同结果 → R-STABLE

---

## 风险分级

| 分级 | 分值范围 | 说明 |
|------|---------|------|
| 低 | 1-5 | 不影响核心功能，可延后修复 |
| 中 | 6-11 | 影响非核心功能或边界场景 |
| 高 | 12-25 | 影响核心功能、数据一致性或资金安全 |
