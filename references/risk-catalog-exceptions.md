# 异常分支分类目录（Java DDD+TMF）— E-* 类型

> Q06 单测审计使用。每个类型含：典型场景、代码信号、单测判定规则。

---

## E-INVAL: 参数非法/边界非法

**典型场景**：Controller 入参 null/空串/超长/非法枚举；金额为负数或零；日期格式错误

**代码信号**：`@NotNull`/`@NotBlank`/`@Size`/`@Valid`；`Preconditions.checkArgument()`；`Assert.notNull()`

**单测判定规则**
- 每个写接口至少测 null、空串、边界值三类非法输入
- 断言异常类型和错误码，不能只断言「抛了异常」

---

## E-NOTFOUND: 关键对象不存在

**典型场景**：根据 ID 查询返回 null；关联对象已被删除；缓存未命中且 DB 也无记录

**代码信号**：`Optional.orElseThrow()`；`if (entity == null) throw new BizException(NOT_FOUND)`；`dao.selectById(id)` 返回值未做 null 检查

**单测判定规则**
- 每个 `selectById`/`findByXxx` 调用点必须有 null 路径测试
- 断言返回的错误码而非仅断言抛异常

---

## E-CONFLICT: 状态冲突/并发冲突

**典型场景**：订单已取消但用户尝试支付；乐观锁版本号不匹配；唯一键冲突

**代码信号**：`OptimisticLockException`/`DuplicateKeyException`；`UPDATE ... WHERE version = #{version}`；`if (order.getStatus() != CREATED) throw new BizException(INVALID_STATUS)`

**单测判定规则**
- 状态冲突：构造非法前置状态，断言拒绝操作且状态未变
- 乐观锁：模拟版本号不匹配，断言重试或失败
- 唯一键：模拟重复插入，断言幂等或明确报错

---

## E-TIMEOUT: 下游超时

**典型场景**：RPC 调用超时；数据库慢查询超时；Redis 操作超时

**代码信号**：`@DubboReference(timeout = 3000)`；`RestTemplate`/`FeignClient` 超时配置；`catch (TimeoutException e)`

**单测判定规则**
- Mock 下游超时，断言降级行为或明确的超时异常
- 断言超时后不产生脏数据（事务回滚或补偿）

---

## E-REMOTE: 下游返回错误码

**典型场景**：支付网关返回「余额不足」；库存服务返回「库存不足」；第三方 API 返回非 200

**代码信号**：`if (!response.isSuccess()) throw new BizException(response.getCode())`；`RpcResult.getCode() != 0`；HTTP status 4xx/5xx 处理

**单测判定规则**
- 每个 RPC 调用点至少测一个错误码路径
- 断言错误码透传或转换正确
- 断言失败后本地状态一致（无半成功）

---

## E-EMPTY: 下游空响应

**典型场景**：RPC 返回 null 或空列表；数据库查询返回空结果集；缓存 miss 且 DB 也无数据

**代码信号**：`if (result == null || result.isEmpty())`；`CollectionUtils.isEmpty(list)`；`Optional.empty()`

**单测判定规则**
- Mock 下游返回 null/空列表，断言不抛 NPE
- 断言空响应时的业务行为（降级/默认值/明确报错）

---

## E-DBERR: 持久化失败/事务异常

**典型场景**：数据库连接池耗尽；死锁导致事务回滚；主从延迟导致读不到刚写入的数据

**代码信号**：`@Transactional(rollbackFor = Exception.class)`；`catch (DataAccessException e)`；`catch (DeadlockLoserDataAccessException e)` 重试

**单测判定规则**
- Mock 持久化异常，断言事务回滚（无脏数据）
- 断言异常后领域状态未被错误推进
- 有重试机制的需测重试次数和最终失败行为

---

## E-DEGRADE: 降级与兜底路径

**典型场景**：推荐服务不可用时返回默认列表；缓存不可用时直接查 DB；非核心功能异常时不影响主流程

**代码信号**：`@SentinelResource(fallback = "xxxFallback")`；`catch (Exception e) { return defaultValue; }`；`@HystrixCommand(fallbackMethod = "fallback")`

**单测判定规则**
- 降级路径必须有独立测试，不能只测正常路径
- 断言降级返回值符合业务预期（非 null/非空壳）
- 断言降级时的日志/监控告警触发

---

## E-SEM: 关键语义错误/语义丢失/重排异常

**典型场景**：金额计算精度丢失；列表排序后顺序与业务预期不符；分页查询跳过或重复数据

**代码信号**：`BigDecimal.setScale()` 缺失；`Comparator` 不满足传递性；`LIMIT #{offset}, #{size}` 无稳定排序字段

**单测判定规则**
- 金额计算必须用 BigDecimal 且断言精度
- 排序测试必须包含相等元素的稳定性验证
- 分页测试必须验证总数、边界页、空页

---

## 最小映射规则

- 每个 REQ 至少 1 个 UT
- 每个高风险 RISK 至少 1 个 EUT
- 每个 EUT 必须映射到具体 RISK 和 REQ/BR
- 每个关键语义条目（SEM）至少 2 个 UT（规则正确性 + 边界或稳定性）
- 每个关键语义高风险至少 1 个 EUT
