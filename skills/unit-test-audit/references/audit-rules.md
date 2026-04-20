# 单测审计详细规则

## 架构识别与分层职责基线

### 架构类型识别

每次审计必须先给出架构类型：
1. `DDD`：典型分层（Client/Application/Domain/Infrastructure）
2. `TMF`：基于 TMF runtime/ability/step/extension 的流程编排
3. `DDD+TMF`：DDD 分层 + TMF 扩展点机制并存（默认按最严格口径审计）

可用识别信号（至少命中一组）：
1. 注解与接口：`@DomainService`、`@DomainStep`、`@DomainAbility`、`IDomainService`、`AbstractDomainAbility`
2. 运行时调用：`TMF.findAbility(...)`、`TMF.execute(...)`、`invokeStep(...)`
3. 分层包结构：`client/application/domain/infrastructure/spec`

### DDD 分层职责审计基线

1. `Client`：只定义 API 契约与 DTO，不承载业务分支
2. `Application`：编排调用、模型转换、异常包装；不实现核心领域规则
3. `Domain`：聚合根、不变式、状态迁移、领域服务与领域规则
4. `Infrastructure`：Gateway/Mapper/RPC/DB 等技术实现

### TMF 分层职责审计基线

1. `Application`：`ApiImpl -> CmdExe`，负责委托与转换
2. `DomainService`：调用 `TMF.execute` 编排步骤链
3. `DomainStep`：通过 `getSlot()` 读模型、通过 `TMF.findAbility()` 调能力、必要时实现 `rollback()`
4. `DomainAbility`：继承 `AbstractDomainAbility<Model, Extension>`，通过 `firstExtension()` 或 `getExtension(..., Reducer.allOf())` 调扩展点
5. `Spec/Extension`：定义扩展点接口与步骤常量，BP 前台实现扩展点
6. `Infrastructure`：实现 Domain Gateway，承接外部依赖

## DDD/TMF 分层单测最小集合（强制）

### DDD 口径

1. `Client`：契约与校验注解测试（参数约束、返回结构），无业务断言
2. `Application`：
   - DTO -> Domain 映射正确
   - 异常包装策略正确（例如 BizException 包装/透传）
   - 仅编排不承载领域规则
3. `Domain`：
   - 聚合根不变式、状态迁移、幂等、并发语义
   - 通过 Gateway 接口隔离外部依赖
   - 事务语义与业务后果断言完整
4. `Infrastructure`：
   - Gateway/Mapper 持久化正确
   - 外部调用失败/超时/脏数据处理正确
   - DO <-> Domain 映射字段完整

### TMF 口径

1. `CmdExe`：
   - `Command -> Creator` 映射
   - 调用 DomainService 后 `Domain -> Response` 映射
   - 业务异常包装分支
   - `CustomModelAbility.render` 触发条件与结果
2. `DomainService`：
   - `decideSteps` 输出链路正确
   - `TMF.execute` 成功/失败分支
   - 锁获取失败、锁释放（finally）语义
   - `handleException` 后业务后果断言
3. `DomainStep`：
   - `process()` 主路径
   - `invokeStep(...)` 调用顺序/条件
   - `rollback()` 触发条件与补偿结果（如有）
   - 禁止通过 `@Resource/@Autowired` 直接注入 Ability
4. `DomainAbility`：
   - `firstExtension()` 与 `getExtension(..., Reducer.allOf())` 行为正确
   - `defaultExtension()` 有/无默认实现两类路径
   - 扩展点异常传播或降级策略正确

## 断言正确性与合理性（CR 强校验）

对写库类单测（Mapper/Repository/DAO/Service 写操作）必须检查：

1. 结果断言不能停留在 `assertNotNull`
2. 必须断言主键（生成与回填正确，或插入后可准确查询）
3. 必须断言时间字段（创建/更新时间是否符合预期语义）
4. 必须断言新增字段（本次新增列、新增业务字段写入与读取一致）
5. 必须断言关键业务字段值而非仅对象存在
6. 必须断言副作用（写条数、状态迁移、事件/消息触发或未触发）
7. 对编排层（Application/CmdExe/Step）不能只断言"被调用"，需断言业务结果或后果

若仅做"非空断言"或"调用次数断言"而未验证业务结果，标记 `WRONG_TARGET`。

## 异常场景强制覆盖（最低要求）

单测规范必须覆盖以下异常输入与分支：

1. 字段长度溢出
2. 必填字段为空（null/blank）
3. 枚举非法值
4. 数值越界（负值、超上限、精度异常）
5. 状态非法迁移
6. 外部依赖超时/失败/脏数据返回
7. 并发冲突（锁竞争、重复请求）
8. 配置缺失/错误（开关、路由、步骤链配置）
9. TMF 扩展点缺失、扩展点抛错、步骤执行失败

对核心业务写操作，上述非法/边界输入必须全覆盖并有断言。

## 覆盖率基线（增量口径）

以下为基础门槛，未达标默认 `FAIL`：

1. 增量行覆盖率 `>= 80%`
2. 增量分支覆盖率 `>= 80%`
3. 核心领域异常分支单测覆盖 `= 100%`
4. 对外 API 及依赖第三方格式解析/转换代码：行覆盖 `= 100%` 且分支覆盖 `= 100%`
5. 单测必须 mock 边界格式输入（例如异常时间格式、非法时区、格式截断）
6. TMF 关键编排节点（`decideSteps` / `TMF.execute` / `firstExtension|allOf`）必须有正反两类用例

覆盖率达标仅代表"门槛通过"，不代表质量结论自动通过。

## 风险分级（用于审计优先级）

1. `T1-核心`：资金、订单、库存、计费、状态机迁移、关键幂等路径
2. `T2-重要`：核心链路旁路、高频查询、关键聚合逻辑
3. `T3-一般`：低风险工具函数、简单转换、展示辅助

## 红线规则

1. 无需求依据，不得给"覆盖完整"结论
2. 无架构依据（无法判断 DDD/TMF 分层职责），不得给"分层充分"结论
3. 仅有 happy path，异常分支缺失，不得判通过
4. 仅验证调用关系、不验证业务结果，不得判通过
5. 新增业务分支无对应场景测试，至少判 `HIGH`
6. 测试建立在错误需求假设上，判 `CRITICAL`
7. `T1-核心` 的异常分支存在 `MISSING/WRONG_TARGET`，直接判 `FAIL`
8. 写库类单测若缺少主键/时间/新增字段断言，直接判 `FAIL` 候选
9. TMF Step 直接注入 Ability（未用 `TMF.findAbility`）且无拦截测试，至少判 `HIGH`
10. TMF 关键编排节点（`decideSteps` / `TMF.execute` / 扩展点调用）无失败路径用例，`T1` 场景直接判 `FAIL`
11. 存在图片语义但未纳入 `SEM -> UT/EUT` 映射，至少判 `HIGH`；关键路径判 `CRITICAL`
12. T1 核心路径存在 `MUTATION_SURVIVED_CRITICAL` 且未补强断言，直接判 `FAIL`

## 输入要求

至少收集以下信息：

1. 需求依据（至少一项）：需求文档、需求单、缺陷单、PR 描述、验收标准
2. 架构依据（至少一项）：分层设计文档、模块结构、TMF/DDD 注解与接口证据
3. 改动范围：`git diff <base>...HEAD` 变更文件与关键函数
4. 测试资产：现有单测、本次新增/修改单测、历史回归说明
5. 覆盖率证据：增量覆盖率报告（例如 JaCoCo 增量报告或等价工具输出）

若缺少需求依据、架构依据或覆盖率证据，必须输出 `NEEDS_CONTEXT` 并向用户索取。
