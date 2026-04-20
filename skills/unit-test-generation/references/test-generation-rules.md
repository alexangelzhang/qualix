# 单测生成详细规则

## DDD+TMF 分层测试要求

### DDD 分层

| 层级 | 测试重点 | Mock 策略 |
|------|---------|----------|
| Client | 契约与校验注解测试（参数约束、返回结构），无业务断言 | 无需 mock |
| Application/CmdExe | DTO→Domain 映射正确、异常包装策略、仅编排不承载领域规则 | Mock 下层 Service |
| Domain | 聚合根不变式、状态迁移、幂等、并发语义、通过 Gateway 接口隔离 | Mock Gateway |
| Infrastructure | Gateway/Mapper 持久化正确、外部调用失败处理、DO↔Domain 映射 | Mock 外部依赖 |

### TMF 分层

| 层级 | 测试重点 | Mock 策略 |
|------|---------|----------|
| CmdExe | Command→Creator 映射、调用 DomainService 后映射、业务异常包装 | Mock DomainService |
| DomainService | `decideSteps` 输出链路、`TMF.execute` 成功/失败、锁获取/释放、`handleException` | Mock TMF runtime |
| DomainStep | `process()` 主路径、`invokeStep()` 调用顺序、`rollback()` 触发与补偿 | `mock TMF.findAbility()` |
| DomainAbility | `firstExtension()` 与 `allOf` 行为、`defaultExtension()` 有/无默认实现、扩展点异常 | Mock Extension |

## Mock 数据质量要求

- Mock 返回值必须符合接口契约，至少包含被测方法会访问的所有字段
- 禁止返回空对象或全默认值（会掩盖真实调用时的字段缺失问题）
- 从技术方案的 DTO 定义中提取必填字段构造 mock 数据

## Mock 优先级层级（Prefer Real Over Mock）

| 优先级 | 方式 | 适用场景 | 示例 |
|--------|------|---------|------|
| 1 | Real | 内存数据库、本地缓存 | H2 替代 MySQL，HashMap 替代 Redis |
| 2 | Fake | 轻量级替代实现 | InMemoryRepository 替代 JPA |
| 3 | Stub | 固定返回值 | `when(...).thenReturn(fixedValue)` |
| 4 | Mock | 行为验证 | `verify(gateway).save(any())` |

原则：能用 Real/Fake 就不用 Stub/Mock。过度 mock 会让测试与实现耦合，重构时大面积失败。

## DAMP 原则（Descriptive And Meaningful Phrases）

测试代码优先可读性，而非 DRY（Don't Repeat Yourself）：

- 每个测试方法应该是一个**完整的故事**，读者不需要跳转到 helper 方法才能理解测试意图
- 允许测试间有适度重复（如 setup 数据构造），只要每个测试独立可读
- 共享 helper 只用于**真正的基础设施**（如数据库初始化），不用于业务数据构造
- 测试方法名必须描述场景，不是实现：`shouldRejectWhenAmountExceedsLimit` 而非 `testValidate`

## EUT 矩阵模板

| EUT ID | 绑定 SE | 路径类型 | 风险等级 | Given | When | Then |
|--------|---------|---------|---------|-------|------|------|
| EUT-001 | SE-001 | Happy | T1 | 正常订单数据 | 调用创建订单 | 订单状态=CREATED, 金额正确 |
| EUT-002 | SE-001 | Exception | T1 | 重复订单号 | 调用创建订单 | 抛 DuplicateException, 状态未变更 |
| EUT-003 | SE-003 | Boundary | T2 | 金额=0.01(最小值) | 调用退款 | 退款成功, 精度正确 |

## 覆盖度统计模板

| 维度 | 总数 | 已覆盖 | 覆盖率 |
|------|------|--------|--------|
| SE → EUT | N | M | M/N |
| Happy Path | - | X | - |
| Exception | - | Y | - |
| Boundary | - | Z | - |
| T1 核心 | A | B | B/A |

## 红线规则（违反即 FAIL）

1. EUT 全部是 Happy Path，无 Exception/Boundary → FAIL
2. 存在 `assertNotNull` 冒充业务覆盖 → Phase Q06 会判 WRONG_TARGET
3. 异常测试只有 `assertThrows` 无业务效果断言 → Phase Q06 会判 WRONG_TARGET
4. Mock 返回空对象/默认值掩盖字段缺失 → 测试通过但实际会 NPE
5. T1 核心路径的 SE 无对应 EUT → FAIL
6. 编译不通过 → BLOCKED（compile_check gate 拦截）
7. 无推理日志 → BLOCKED（finalize 硬性校验）
