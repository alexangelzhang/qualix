# Phase Q05: TDD需求驱动单测生成 (测试大纲建模与实施)

# /ut-generator: 需求驱动的单测实施体系

本阶段负责承接 Phase Q01 输出的结构化需求，在功能代码写完进行提测或入库前，强制采用大模型按照架构规范生成单元测试场景大纲（EUT）与测试代码本体，实现真正的"TDD 左移"。

> **技术栈基线**：本阶段默认使用 Java + DDD + TMF 基线。
> 基线按项目 profile 选择：
> - `java-ddd-tmf`：`references/java-ddd-tmf-baseline.md`
> - `go-service`：`references/go-service-baseline.md`
> 未指定 profile 时回退 Java 默认基线。

## 核心指导思想

1. **以审带写**：生成的测试必须 100% 满足 Phase Q06 的单测覆盖审计基线（断言强度、异常覆盖、分层职责）。
2. **脱离伪覆盖**：禁止从代码 `if-else` 反推用例（代码可能已写错）。强制基于 `REQ/BR/SE` 生成 EUT。
3. **断言约束**：禁止"空气单测"。必须断言：状态变更、副作用交互次数（Mockito.verify）、数据库核心字段写入。
4. **Phase Q06 对齐**：生成的每个测试都要能通过 Phase Q06 的审计标准，不能生成 Phase Q06 会判为 `WRONG_TARGET` 的测试。

## 审计对齐标准（从 Phase Q06 提取）

以下标准直接来自 Phase Q06 的审计规则。Phase Q05 生成的测试必须满足这些标准，否则会在 Phase Q06 被判为不合格。

### 断言正确性（Phase Q06 强校验标准）

对写库类单测（Mapper/Repository/DAO/Service 写操作）必须满足：

1. 结果断言不能停留在 `assertNotNull`。
2. 必须断言主键（生成与回填正确，或插入后可准确查询）。
3. 必须断言时间字段（创建/更新时间是否符合预期语义）。
4. 必须断言新增字段（本次新增列、新增业务字段写入与读取一致）。
5. 必须断言关键业务字段值而非仅对象存在。
6. 必须断言副作用（写条数、状态迁移、事件/消息触发或未触发）。
7. 对编排层（Application/CmdExe/Step）不能只断言"被调用"，需断言业务结果或后果。

若仅做"非空断言"或"调用次数断言"而未验证业务结果 → Phase Q06 会标记 `WRONG_TARGET`。

### 异常场景强制覆盖（Phase Q06 最低要求）

生成的单测必须覆盖以下异常输入与分支：

1. 字段长度溢出。
2. 必填字段为空（null/blank）。
3. 枚举非法值。
4. 数值越界（负值、超上限、精度异常）。
5. 状态非法迁移。
6. 外部依赖超时/失败/脏数据返回。
7. 并发冲突（锁竞争、重复请求）。
8. 配置缺失/错误（开关、路由、步骤链配置）。
9. TMF 链路异常（`decideSteps` 异常、`TMF.execute` 失败、扩展点缺失/异常）。

对核心业务写操作，上述非法/边界输入必须全覆盖并有断言。

### 异常断言完整性（Phase Q06 Step 5 标准）

异常分支用例除了"执行到异常"，还必须包含：

1. 错误结果断言：异常类型、错误码、错误信息（至少其一可稳定断言）。
2. 状态断言：失败后领域状态未被错误推进。
3. 数据断言：数据库无脏写、无重复写、无部分提交。
4. 事务断言：应回滚时必须回滚；需要补偿时有补偿结果。
5. 外部调用断言：重试次数、降级路径、熔断/限流行为符合预期。
6. 幂等断言：重复请求不产生额外副作用。
7. TMF 断言：失败后链路中止正确、`rollback`/补偿行为正确。

若异常分支仅断言"抛了异常"而无业务后果断言 → Phase Q06 会标记 `WRONG_TARGET`。

### 覆盖率目标（Phase Q06 门禁）

1. 增量行覆盖率 `>= 80%`。
2. 增量分支覆盖率 `>= 80%`。
3. 核心领域异常分支单测覆盖 `= 100%`。
4. 对外 API 及依赖第三方格式解析/转换代码：行覆盖 `= 100%` 且分支覆盖 `= 100%`。
5. TMF 关键编排节点（`decideSteps` / `TMF.execute` / `firstExtension|allOf`）必须有正反两类用例。

### 风险分级（决定生成优先级）

1. `T1-核心`：资金、订单、库存、计费、状态机迁移、关键幂等路径 → 必须 100% 覆盖。
2. `T2-重要`：核心链路旁路、高频查询、关键聚合逻辑 → 主流程 + 关键分支。
3. `T3-一般`：低风险工具函数、简单转换、展示辅助 → 主流程可用即可。

## 执行流程

### Step 0: 输入确认与上下文加载

1. 确认 Phase Q01 产物存在（`phase_a_structured.json`）。
2. 确认代码仓库路径和目标模块。
3. 读取 `_upstream_context.md`（不回读原始 PRD）。
4. 读取 `_business_mutations.md`（如存在，了解业务域变异规则）。
5. 识别架构类型：`DDD / TMF / DDD+TMF`。
6. 输出改动清单、影响模块与涉及层。

### Step 1: 契约模型与场景树解构（EUT 建模）

基于 Phase Q01 的产物建立独立的 EUT 矩阵大纲，**逐条对照 SE 列表**：

**1.1 正常流（Happy Path）**：针对主需求 `REQ`/分支需求 `BR` 构建无错调用图景。

**1.2 边界流（Boundary）**：针对 `SE` 中定义的数值阈值、越权漏洞、临界时间戳做参数等价类组合。

**1.3 异常流（Exception）**：对于微服务和 TMF 架构，强制枚举：
  - TMF 中 `Extension` 缺失、`decideSteps` 判断失败或某一个 Ability 执行抛错降级的路径。
  - Infrastructure 层 RPC 调用引发超时、限流错误（模拟返回 5xx 等）。
  - Domain 并发情况下的乐观锁冲突及业务异常。
  - 参数校验异常（null/blank/非法枚举/越界）。
  - 状态非法迁移。
  - 配置缺失/错误。

**1.4 EUT 覆盖度自检**：
  - 逐条检查 Phase Q01 的 SE 列表，确认每条 SE 至少有一个 EUT（`bound_se` 字段正确关联）。
  - 未覆盖的 SE 必须标记原因（不可静默跳过）。
  - 统计三种路径类型分布：Happy/Exception/Boundary 必须均衡，不能全是 Happy Path。

**1.5 风险分级标注**：
  - 每个 EUT 标注 `risk_tier`（T1/T2/T3）。
  - T1 核心路径的 EUT 必须包含 Happy + Exception 两类。

### Step 2: 架构上下文（DDD+TMF）代码脚手架生成

生成单测结构时，严格遵照分层职责界限：

**2.1 DDD 分层**：

| 层级 | 测试重点 | Mock 策略 |
|------|---------|----------|
| Client | 契约与校验注解测试（参数约束、返回结构），无业务断言 | 无需 mock |
| Application/CmdExe | DTO→Domain 映射正确、异常包装策略、仅编排不承载领域规则 | Mock 下层 Service |
| Domain | 聚合根不变式、状态迁移、幂等、并发语义、通过 Gateway 接口隔离 | Mock Gateway |
| Infrastructure | Gateway/Mapper 持久化正确、外部调用失败处理、DO↔Domain 映射 | Mock 外部依赖 |

**2.2 TMF 分层**：

| 层级 | 测试重点 | Mock 策略 |
|------|---------|----------|
| CmdExe | Command→Creator 映射、调用 DomainService 后映射、业务异常包装 | Mock DomainService |
| DomainService | `decideSteps` 输出链路、`TMF.execute` 成功/失败、锁获取/释放、`handleException` | Mock TMF runtime |
| DomainStep | `process()` 主路径、`invokeStep()` 调用顺序、`rollback()` 触发与补偿 | `mock TMF.findAbility()` |
| DomainAbility | `firstExtension()` 与 `allOf` 行为、`defaultExtension()` 有/无默认实现、扩展点异常 | Mock Extension |

**2.3 Mock 数据质量要求**：
  - Mock 返回值必须符合接口契约，至少包含被测方法会访问的所有字段。
  - 禁止返回空对象或全默认值（会掩盖真实调用时的字段缺失问题）。
  - 从技术方案的 DTO 定义中提取必填字段构造 mock 数据。

**2.4 Mock 优先级层级（Prefer Real Over Mock）**：

优先使用真实实现，mock 是最后手段：

| 优先级 | 方式 | 适用场景 | 示例 |
|--------|------|---------|------|
| 1 | Real | 内存数据库、本地缓存 | H2 替代 MySQL，HashMap 替代 Redis |
| 2 | Fake | 轻量级替代实现 | InMemoryRepository 替代 JPA |
| 3 | Stub | 固定返回值 | `when(...).thenReturn(fixedValue)` |
| 4 | Mock | 行为验证 | `verify(gateway).save(any())` |

原则：能用 Real/Fake 就不用 Stub/Mock。过度 mock 会让测试与实现耦合，重构时大面积失败。

**2.5 DAMP 原则（Descriptive And Meaningful Phrases）**：

测试代码优先可读性，而非 DRY（Don't Repeat Yourself）：

- 每个测试方法应该是一个**完整的故事**，读者不需要跳转到 helper 方法才能理解测试意图
- 允许测试间有适度重复（如 setup 数据构造），只要每个测试独立可读
- 共享 helper 只用于**真正的基础设施**（如数据库初始化），不用于业务数据构造
- 测试方法名必须描述场景，不是实现：`shouldRejectWhenAmountExceedsLimit` 而非 `testValidate`

### Step 3: 单测强断言约束代码实现

要求在最终产出 `@Test` 代码时落实以下操作规程：

**3.1 写行为断言**：
  - `assertEquals` 校验关键业务字段（金额、状态、ID、时间戳）。
  - 金额类断言必须精确到分（`assertEquals(expected, actual)` 或 `compareTo`）。
  - 状态类断言必须验证流转后的具体状态值。

**3.2 副作用验证**：
  - `Mockito.verify(client, times(1)).doAction(...)` 验证外部调用。
  - 通知/消息/事件发布必须有 `verify` 验证确实被调用。
  - 不应该被调用的方法用 `verify(mock, never())` 验证。

**3.3 精确异常拦截**：
  - `assertThrows(SpecificException.class, () -> ...)` 捕获具体异常类型。
  - `assertEquals(ExpectedBizCode.ILLEGAL_STATE, ex.getCode())` 验证错误码。
  - 异常后必须补充业务效果断言（状态未变更、数据未写入、事务已回滚）。
  - 禁止 `try{...}catch(Exception e){}` 静默吞异常。

**3.4 追溯性标注**：
  - 每个 `@Test` 方法必须在注释或 `@DisplayName` 中标注关联的 SE/EUT ID。
  - 格式：`// 对应: SE-014 当越权访问时拦截` 或 `@Tag("EUT-003")`。

### Step 4: 编译验证

生成代码后，自检以下编译要素：

1. 所有 import 是否正确（特别是 Mockito、JUnit 5、项目内部类）。
2. `@Mock` 注解的类型是否与被测类的依赖接口一致。
3. 构造函数参数是否完整。
4. 泛型类型是否匹配。

> finalize 时 `compile_check.py` 会自动执行 `mvn compile` 验证，编译失败会 BLOCKED。

### Step 5: 自检（提交前强制检查）

完成 Step 1-4 后，逐项核对以下清单，全部通过方可继续：

- [ ] EUT 矩阵覆盖了所有 REQ/BR/SE（逐条对照，无遗漏）
- [ ] 三种路径类型均衡：Happy/Exception/Boundary 都有覆盖
- [ ] T1 核心路径有 Happy + Exception 两类 EUT
- [ ] 单测代码使用强断言（非仅 assertNotNull/assertTrue(true)）
- [ ] 写库类测试断言了主键、时间字段、新增字段、副作用
- [ ] 异常路径有对应测试，且包含业务效果断言（不只是 assertThrows）
- [ ] Mock 返回值符合接口契约，非空对象/默认值
- [ ] 每个测试用例标注了关联的 SE/EUT ID
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出

### Step 6: Judge/Critique（提交前自我评审）

- **Judge**：对照 Phase Q01 产物验证 EUT 矩阵覆盖完整性，按 4 维度打分（EUT 覆盖/断言强度/可编译性/SE 追溯）
- **Critique**：假设有遗漏，重点检查：
  - 异常路径是否只有 Happy Path 没有 Exception/Boundary
  - 断言是否只有 assertNotNull 没有业务字段验证
  - 并发/幂等/超时场景是否被跳过
  - Mock 数据是否过于简化掩盖了真实问题
- 记录在报告末尾「自我评审记录」章节

### Step 7: 修正

根据 Step 5 自检和 Step 6 Judge/Critique 发现的问题，逐项修正后重新通过自检清单。

## 红线规则（违反即 FAIL）

1. EUT 全部是 Happy Path，无 Exception/Boundary → FAIL。
2. 存在 `assertNotNull` 冒充业务覆盖 → Phase Q06 会判 WRONG_TARGET。
3. 异常测试只有 `assertThrows` 无业务效果断言 → Phase Q06 会判 WRONG_TARGET。
4. Mock 返回空对象/默认值掩盖字段缺失 → 测试通过但实际会 NPE。
5. T1 核心路径的 SE 无对应 EUT → FAIL。
6. 编译不通过 → BLOCKED（compile_check gate 拦截）。
7. 无推理日志 → BLOCKED（finalize 硬性校验）。

## 输出模板

### EUT 矩阵

| EUT ID | 绑定 SE | 路径类型 | 风险等级 | Given | When | Then |
|--------|---------|---------|---------|-------|------|------|
| EUT-001 | SE-001 | Happy | T1 | 正常订单数据 | 调用创建订单 | 订单状态=CREATED, 金额正确 |
| EUT-002 | SE-001 | Exception | T1 | 重复订单号 | 调用创建订单 | 抛 DuplicateException, 状态未变更 |
| EUT-003 | SE-003 | Boundary | T2 | 金额=0.01(最小值) | 调用退款 | 退款成功, 精度正确 |

### 覆盖度统计

| 维度 | 总数 | 已覆盖 | 覆盖率 |
|------|------|--------|--------|
| SE → EUT | N | M | M/N |
| Happy Path | - | X | - |
| Exception | - | Y | - |
| Boundary | - | Z | - |
| T1 核心 | A | B | B/A |

## 禁止事项

1. 禁止从代码 `if-else` 反推用例（代码可能已写错）。
2. 禁止生成"空气单测"（只有执行流无断言）。
3. 禁止跳过自检和 Judge/Critique 直接 finalize。
4. 禁止重跑时从零重写（必须在旧版基线上增量修改）。
5. 禁止跳过难以 mock 的 SE（应上报重构需求）。
6. 禁止在 Phase Q05 输出审计结论（审计是 Phase Q06 的职责）。
