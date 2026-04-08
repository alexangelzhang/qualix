# 风险与异常分类目录（Java DDD+TMF）

> 本目录是 Phase A.6（技术方案质量评审）和 Phase C（单测审计）的判定锚点。
> 每个类型包含：定义、Java 场景下的典型触发条件、代码信号、判定规则。

---

## 风险类型

### R-AMB: 需求歧义/验收口径不一致

**典型触发条件**
- PRD 用「大概」「可能」「适当」等模糊词描述业务规则
- 同一业务概念在不同章节有不同定义（如「订单金额」有时含运费有时不含）
- 验收标准缺少具体数值（如「快速响应」未定义 RT 上限）

**判定规则**
- 技术方案中出现 TODO/TBD/待确认 → R-AMB
- 接口入参/出参的枚举值未穷举 → R-AMB
- 状态迁移条件用自然语言描述而非明确的前置条件 → R-AMB

### R-STATE: 状态机缺口/非法迁移

**典型触发条件**
- 领域对象有状态字段但未画状态机图
- 存在跳跃迁移（如 CREATED 直接到 COMPLETED，跳过 PROCESSING）
- 并发场景下两个操作同时触发状态迁移

**代码信号**
- `enum XxxStatus` 或 `String status` 字段
- `if (status == A) { status = B; }` 无前置校验
- 缺少 `@Version` 乐观锁保护状态迁移

**判定规则**
- 状态枚举值 > 3 但无状态机文档 → R-STATE
- 状态迁移方法无前置状态校验 → R-STATE (CRITICAL)
- 状态迁移无并发保护（乐观锁/分布式锁）→ R-STATE + R-CONCUR

### R-IDEMP: 幂等与重复请求

**典型触发条件**
- 用户重复点击提交按钮
- 消息队列重复投递（at-least-once）
- 定时任务重复触发
- RPC 超时重试

**代码信号**
- 写操作方法无 `@Idempotent` 或幂等 key 参数
- INSERT 无唯一约束兜底
- MQ Consumer 无消费去重表

**判定规则**
- 写接口无幂等设计说明 → R-IDEMP
- 技术方案提到「重试」但未说明幂等策略 → R-IDEMP
- 金融/支付类操作无幂等 → R-IDEMP (CRITICAL)

### R-CONCUR: 并发竞争/锁冲突

**典型触发条件**
- 库存扣减、余额变更等热点资源并发写
- 同一聚合根被多个线程/请求同时修改
- 分布式锁获取失败后的降级策略缺失

**代码信号**
- `synchronized` / `ReentrantLock` 使用
- `@Version` 乐观锁字段
- `RedissonClient.getLock()` / `DistributedLock`
- `UPDATE ... SET amount = amount - #{qty} WHERE amount >= #{qty}`

**判定规则**
- 热点资源写操作无任何并发控制 → R-CONCUR (CRITICAL)
- 有乐观锁但无重试策略 → R-CONCUR
- 分布式锁无超时释放机制 → R-CONCUR

### R-CONSIST: 跨服务数据一致性

**典型触发条件**
- 扣库存 + 创建订单跨两个服务
- 主表写成功但从表写失败
- RPC 调用成功但本地事务回滚

**代码信号**
- 同一方法内调用多个 RPC/Gateway
- `@Transactional` 内包含 RPC 调用
- 无 Saga/TCC/本地事务表/消息事务

**判定规则**
- 跨服务写操作无补偿/回滚机制 → R-CONSIST (CRITICAL)
- `@Transactional` 内嵌套 RPC 调用 → R-CONSIST
- 技术方案提到「分布式事务」但未说明具体方案（Saga/TCC/消息表）→ R-CONSIST

### R-DEPEND: 外部依赖失败/超时

**典型触发条件**
- 下游服务不可用（部署/故障）
- 第三方 API 超时或返回非预期格式
- 中间件（Redis/MQ/ES）连接失败

**代码信号**
- RPC 调用无 timeout 配置
- 无 `@HystrixCommand` / `@SentinelResource` / 手动熔断
- catch 块吞异常后返回 null

**判定规则**
- RPC 调用无超时配置 → R-DEPEND
- 无降级/熔断策略 → R-DEPEND
- 核心链路依赖非核心服务且无降级 → R-DEPEND (CRITICAL)

### R-OBS: 可观测性不足

**典型触发条件**
- 关键业务操作无日志
- 异常被 catch 但未记录
- 无 metrics 埋点（RT/QPS/错误率）

**代码信号**
- `catch (Exception e) { }` 空 catch
- `catch (Exception e) { return null; }` 吞异常
- 关键方法无 `log.info/warn/error`

**判定规则**
- 写操作无审计日志 → R-OBS
- 异常分支无 log.error → R-OBS
- 核心链路无 RT/成功率监控 → R-OBS

### R-PERM: 权限与数据越权

**典型触发条件**
- 用户 A 可以操作用户 B 的数据
- 接口未校验操作者身份
- 批量接口未做数据归属校验

**代码信号**
- 查询/更新 SQL 无 `WHERE user_id = #{currentUserId}` 条件
- Controller 方法无 `@RequiresPermissions` / `@PreAuthorize`
- 批量操作未逐条校验归属

**判定规则**
- 写接口无操作者身份校验 → R-PERM (CRITICAL)
- 查询接口可通过 ID 遍历获取他人数据 → R-PERM
- 批量导出无数据范围限制 → R-PERM

### R-PERF: 性能与资源瓶颈

**典型触发条件**
- 循环内执行 RPC/SQL（N+1 问题）
- 全表扫描无索引
- 大对象序列化/反序列化
- 无分页的列表查询

**代码信号**
- `for (item : list) { dao.query(item.getId()); }` 循环查询
- `SELECT * FROM table` 无 WHERE/LIMIT
- `JSON.toJSONString(hugeObject)` 大对象序列化

**判定规则**
- 循环内 RPC/SQL 调用 → R-PERF
- 列表查询无分页 → R-PERF
- 技术方案未评估数据量级和 RT 目标 → R-PERF

### R-SEM: 关键业务语义遗漏或实现偏差

**典型触发条件**
- 排序规则与 PRD 不一致（如按时间倒序 vs 正序）
- 聚合计算精度丢失（BigDecimal 未指定 scale）
- 去重逻辑遗漏（如按 userId+skuId 去重但代码只按 skuId）
- 时效判断边界错误（如「3天内」是否含当天）

**代码信号**
- `double` 用于金额计算（应为 `BigDecimal`）
- `Collections.sort()` 无自定义 Comparator
- `distinct()` 或 `GROUP BY` 字段不完整

**判定规则**
- 金额/比例计算用 double/float → R-SEM (CRITICAL)
- 排序/去重/聚合逻辑与 PRD 描述不一致 → R-SEM
- 时间比较未考虑时区 → R-SEM

### R-STABLE: 关键语义稳定性不足

**典型触发条件**
- 同一输入多次执行结果不同（如依赖 HashMap 遍历顺序）
- 重复执行产生额外副作用
- 跨批次处理结果不一致

**代码信号**
- `HashMap` 用于需要稳定顺序的场景（应为 `LinkedHashMap`）
- `Math.random()` / `UUID.randomUUID()` 影响业务逻辑
- 无幂等保护的批量处理

**判定规则**
- 业务结果依赖集合遍历顺序但用 HashMap/HashSet → R-STABLE
- 重复执行同一请求产生不同结果 → R-STABLE

---

## 异常分支类型

### E-INVAL: 参数非法/边界非法

**典型场景**
- Controller 入参 null/空串/超长/非法枚举
- 金额为负数或零
- 日期格式错误、时间范围倒置

**Java 代码信号**
- `@NotNull` / `@NotBlank` / `@Size` / `@Valid` 注解
- `Preconditions.checkArgument()` / `Assert.notNull()`
- `if (param == null) throw new IllegalArgumentException()`

**单测判定规则**
- 每个写接口至少测 null、空串、边界值三类非法输入
- 断言异常类型和错误码，不能只断言「抛了异常」

### E-NOTFOUND: 关键对象不存在

**典型场景**
- 根据 ID 查询订单/用户/商品返回 null
- 关联对象已被删除（如订单存在但商品已下架）
- 缓存未命中且 DB 也无记录

**Java 代码信号**
- `Optional.orElseThrow()` / `Optional.isEmpty()`
- `if (entity == null) throw new BizException(NOT_FOUND)`
- `dao.selectById(id)` 返回值未做 null 检查

**单测判定规则**
- 每个 `selectById` / `findByXxx` 调用点必须有 null 路径测试
- 断言返回的错误码而非仅断言抛异常

### E-CONFLICT: 状态冲突/并发冲突

**典型场景**
- 订单已取消但用户尝试支付
- 乐观锁版本号不匹配
- 唯一键冲突（重复插入）

**Java 代码信号**
- `OptimisticLockException` / `DuplicateKeyException`
- `UPDATE ... SET version = version + 1 WHERE version = #{version}`
- `if (order.getStatus() != CREATED) throw new BizException(INVALID_STATUS)`

**单测判定规则**
- 状态冲突：构造非法前置状态，断言拒绝操作且状态未变
- 乐观锁：模拟版本号不匹配，断言重试或失败
- 唯一键：模拟重复插入，断言幂等或明确报错

### E-TIMEOUT: 下游超时

**典型场景**
- RPC 调用超时（Dubbo/gRPC/HTTP）
- 数据库慢查询超时
- Redis 操作超时

**Java 代码信号**
- `@DubboReference(timeout = 3000)`
- `RestTemplate` / `FeignClient` 超时配置
- `catch (TimeoutException e)`

**单测判定规则**
- Mock 下游超时，断言降级行为或明确的超时异常
- 断言超时后不产生脏数据（事务回滚或补偿）

### E-REMOTE: 下游返回错误码

**典型场景**
- 支付网关返回「余额不足」
- 库存服务返回「库存不足」
- 第三方 API 返回非 200 状态码

**Java 代码信号**
- `if (!response.isSuccess()) throw new BizException(response.getCode())`
- `RpcResult.getCode() != 0`
- HTTP status 4xx/5xx 处理

**单测判定规则**
- 每个 RPC 调用点至少测一个错误码路径
- 断言错误码透传或转换正确
- 断言失败后本地状态一致（无半成功）

### E-EMPTY: 下游空响应

**典型场景**
- RPC 返回 null 或空列表
- 数据库查询返回空结果集
- 缓存 miss 且 DB 也无数据

**Java 代码信号**
- `if (result == null || result.isEmpty())`
- `CollectionUtils.isEmpty(list)`
- `Optional.empty()`

**单测判定规则**
- Mock 下游返回 null/空列表，断言不抛 NPE
- 断言空响应时的业务行为（降级/默认值/明确报错）

### E-DBERR: 持久化失败/事务异常

**典型场景**
- 数据库连接池耗尽
- 死锁导致事务回滚
- 主从延迟导致读不到刚写入的数据

**Java 代码信号**
- `@Transactional(rollbackFor = Exception.class)`
- `catch (DataAccessException e)`
- `catch (DeadlockLoserDataAccessException e)` 重试

**单测判定规则**
- Mock 持久化异常，断言事务回滚（无脏数据）
- 断言异常后领域状态未被错误推进
- 有重试机制的需测重试次数和最终失败行为

### E-DEGRADE: 降级与兜底路径

**典型场景**
- 推荐服务不可用时返回默认列表
- 缓存不可用时直接查 DB
- 非核心功能异常时不影响主流程

**Java 代码信号**
- `@SentinelResource(fallback = "xxxFallback")`
- `catch (Exception e) { return defaultValue; }`
- `@HystrixCommand(fallbackMethod = "fallback")`

**单测判定规则**
- 降级路径必须有独立测试，不能只测正常路径
- 断言降级返回值符合业务预期（非 null/非空壳）
- 断言降级时的日志/监控告警触发

### E-SEM: 关键语义错误/语义丢失/重排异常

**典型场景**
- 金额计算精度丢失（0.1 + 0.2 != 0.3）
- 列表排序后顺序与业务预期不符
- 分页查询跳过或重复数据

**Java 代码信号**
- `BigDecimal.setScale()` 缺失
- `Comparator` 不满足传递性
- `LIMIT #{offset}, #{size}` 无稳定排序字段

**单测判定规则**
- 金额计算必须用 BigDecimal 且断言精度
- 排序测试必须包含相等元素的稳定性验证
- 分页测试必须验证总数、边界页、空页

---

## 风险分级

| 分级 | 分值范围 | 说明 |
|------|---------|------|
| 低 | 1-5 | 不影响核心功能，可延后修复 |
| 中 | 6-11 | 影响非核心功能或边界场景 |
| 高 | 12-25 | 影响核心功能、数据一致性或资金安全 |

## 最小映射规则

- 每个 REQ 至少 1 个 UT
- 每个高风险 RISK 至少 1 个 EUT
- 每个 EUT 必须映射到具体 RISK 和 REQ/BR
- 每个关键语义条目（SEM）至少 2 个 UT（规则正确性 + 边界或稳定性）
- 每个关键语义高风险至少 1 个 EUT（冲突输入/重复或乱序输入/跨批次混合/边界窗口异常，按需适用）
