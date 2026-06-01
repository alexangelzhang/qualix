# Java + DDD + TMF 技术栈基线

> 本文件是 Phase Q05a/Q06/Q07 的语言特定规则集，从主流程中解耦。
> 主流程（AGENTS.md）定义语言无关的审计框架，本文件提供 Java 生态的具体规则。
> 适配其他技术栈时，创建对应的 baseline 文件（如 `go-baseline.md`、`react-baseline.md`）即可。

---

## 1. 架构分层职责（DDD）

| 层 | 职责 | 禁止 |
|----|------|------|
| Client | API 契约、DTO、参数校验注解 | 业务分支、领域规则 |
| Application / CmdExe | 编排调用、模型转换、异常包装 | 核心领域规则、直接数据库操作 |
| Domain | 聚合根不变式、状态迁移、幂等、领域服务、领域规则 | 直接依赖 Infrastructure 实现类 |
| Infrastructure | Gateway/Mapper/RPC/DB 技术实现、DO↔Domain 映射 | 业务规则、状态判断 |

## 2. TMF 编排链路

### 标准调用链

```
ApiImpl → CmdExe → DomainService → TMF.execute → Step → Ability/Extension
```

### 强制规则

1. Step 调能力必须通过 `TMF.findAbility()`，禁止 `@Resource/@Autowired` 直接注入 Ability。
2. Ability 必须继承 `AbstractDomainAbility<Model, Extension>`。
3. 扩展点调用模式必须显式：`firstExtension` 或 `getExtension(..., Reducer.allOf())`。
4. `decideSteps`、`TMF.execute`、`rollback/补偿` 的规则语义要在 SE 中显式化。

### 识别信号（至少命中一组）

1. 注解与接口：`@DomainService`、`@DomainStep`、`@DomainAbility`、`IDomainService`、`AbstractDomainAbility`
2. 运行时调用：`TMF.findAbility(...)`、`TMF.execute(...)`、`invokeStep(...)`
3. 分层包结构：`client/application/domain/infrastructure/spec`

## 3. 单测分层最小集合

### DDD 口径

| 层 | 必测场景 |
|----|---------|
| Client | 契约与校验注解测试（参数约束、返回结构），无业务断言 |
| Application | DTO→Domain 映射正确；异常包装策略正确；仅编排不承载领域规则 |
| Domain | 聚合根不变式、状态迁移、幂等、并发语义；通过 Gateway 接口隔离外部依赖；事务语义与业务后果断言完整 |
| Infrastructure | Gateway/Mapper 持久化正确；外部调用失败/超时/脏数据处理正确；DO↔Domain 映射字段完整 |

### TMF 口径

| 层 | 必测场景 |
|----|---------|
| CmdExe | Command→Creator 映射；调用 DomainService 后 Domain→Response 映射；业务异常包装分支 |
| DomainService | `decideSteps` 输出链路正确；`TMF.execute` 成功/失败分支；锁获取失败、锁释放（finally）语义；`handleException` 后业务后果断言 |
| DomainStep | `process()` 主路径；`invokeStep(...)` 调用顺序/条件；`rollback()` 触发条件与补偿结果；禁止直接注入 Ability |
| DomainAbility | `firstExtension()` 与 `getExtension(..., Reducer.allOf())` 行为正确；`defaultExtension()` 有/无默认实现两类路径；扩展点异常传播或降级策略正确 |

## 4. 断言规则（Java 特定）

### 写库类单测强制断言

1. 结果断言不能停留在 `assertNotNull`。
2. 必须断言主键（生成与回填正确，或插入后可准确查询）。
3. 必须断言时间字段（创建/更新时间是否符合预期语义）。
4. 必须断言新增字段（本次新增列、新增业务字段写入与读取一致）。
5. 必须断言关键业务字段值而非仅对象存在。
6. 必须断言副作用（写条数、状态迁移、事件/消息触发或未触发）。
7. 对编排层（Application/CmdExe/Step）不能只断言"被调用"，需断言业务结果或后果。

### 异常断言

1. 错误结果断言：异常类型、错误码、错误信息（至少其一可稳定断言）。
2. 状态断言：失败后领域状态未被错误推进。
3. 数据断言：数据库无脏写、无重复写、无部分提交。
4. 事务断言：应回滚时必须回滚；需要补偿时有补偿结果。
5. 外部调用断言：重试次数、降级路径、熔断/限流行为符合预期。
6. 幂等断言：重复请求不产生额外副作用。
7. TMF 断言：失败后链路中止正确、`rollback`/补偿行为正确。

### Mock 规则

- Application/CmdExe：主要运用 `Mockito` 编排下层服务，重在测试领域委托是否准确。
- Domain Step/Service：遇到调用 Ability 必须 `mock TMF.findAbility()`；有 `@DomainStep` 回滚机制时，必须生成触发 `process()` 失败进而走到 `rollback()` 的完整链路。
- Infrastructure Gateway：通过轻量级内存库句柄或数据层 Mock，明确断言数据持久化动作正确。

## 5. 代码评审 Checklist（Java 特定）

### Critical

1. 需求语义与实现一致性：`REQ/BR/SEM` 是否能在代码中找到对应实现证据。
2. DDD/TMF 分层职责：Application 是否承载了 Domain 规则（违规）；TMF Step 是否通过 `TMF.findAbility()` 调用能力。
3. SQL 与数据安全：SQL 是否参数化；MyBatis/JPA 是否存在拼接注入风险。
4. 事务边界：`@Transactional` 边界是否覆盖关键写路径；异常回滚语义是否正确。
5. 并发安全：并发写是否具备幂等或乐观锁/版本控制；共享状态是否线程安全。
6. 信任边界：外部输入是否做 schema/字段校验。
7. 枚举与状态完整性：新增枚举值是否覆盖 `switch/if` 所有分支。

### Informational

1. 条件副作用：同条件下是否有重复或遗漏副作用。
2. 魔法值与字符串耦合：硬编码值是否应抽常量。
3. 异常一致性：错误码、日志、异常映射是否一致。
4. 测试缺口：新逻辑是否缺单测/集成测试。

## 6. 异常场景目录（Java 生态）

1. 参数校验异常（null、blank、非法枚举、越界）
2. 领域规则异常（状态机非法迁移、前置条件不满足）
3. 持久层异常（唯一键冲突、乐观锁失败、死锁重试）
4. 第三方调用异常（timeout、5xx、降级、重试上限）
5. 事务语义（回滚是否生效，是否产生半成功）
6. 并发与幂等（重复提交、并发覆盖）
7. 时间与精度（时区、舍入、临界时间点）
8. 配置容错（缺失、错误、默认值路径）
9. TMF 链路异常（`decideSteps` 异常、`TMF.execute` 失败、扩展点缺失/异常）

## 7. 覆盖率门禁（Java 项目）

1. 增量行覆盖率 >= 80%
2. 增量分支覆盖率 >= 80%
3. 核心领域异常分支单测覆盖 = 100%
4. 对外 API 及依赖第三方格式解析/转换代码：行覆盖 = 100% 且分支覆盖 = 100%
5. 单测必须 mock 边界格式输入（如异常时间格式、非法时区、格式截断）
6. TMF 关键编排节点（`decideSteps` / `TMF.execute` / `firstExtension|allOf`）必须有正反两类用例

## 8. 变异测试（Java + PITest）

> 详细设计背景见：`FEATURE-MUTATION-TESTING.md`

### 推荐工具

- PITest（Java 生态主流变异测试框架）
- 增量模式：`scmMutationCoverage`（仅针对 git diff 修改的类生成变异体）

### 变异算子（PITest 默认 + 推荐）

| 算子 | 说明 | 示例 |
|------|------|------|
| CONDITIONALS_BOUNDARY | 条件边界翻转 | `>` → `>=` |
| NEGATE_CONDITIONALS | 条件取反 | `==` → `!=` |
| RETURN_VALS | 返回值篡改 | `return true` → `return false` |
| VOID_METHOD_CALLS | 方法调用删除 | 删除 `notify()` 调用 |
| MATH | 算术运算替换 | `+` → `-` |

### 门禁阈值

| 路径级别 | 变异杀伤率门槛 |
|---------|-------------|
| T1 核心 | >= 80% |
| T2 重要 | >= 60% |
| T3 一般 | 不强制 |

### 存活变异体分类规则

1. 比对 Phase Q01 的 `REQ/BR/SE` 契约
2. 被篡改代码行承载关键业务语义（SE 关联）→ `MUTATION_SURVIVED_CRITICAL`，必须补强断言
3. 被篡改代码行不承载契约语义（日志、无关返回值）→ `MUTATION_SURVIVED_EXEMPT`，允许豁免

### Maven 配置参考

```xml
<plugin>
    <groupId>org.pitest</groupId>
    <artifactId>pitest-maven</artifactId>
    <version>1.15.0</version>
    <configuration>
        <targetClasses>
            <param>com.example.domain.*</param>
        </targetClasses>
        <targetTests>
            <param>com.example.domain.*Test</param>
        </targetTests>
        <mutators>
            <mutator>DEFAULTS</mutator>
        </mutators>
        <features>
            <feature>+auto_threads</feature>
        </features>
    </configuration>
</plugin>
```

## 9. 模板文件

- 单测骨架：`templates/DomainStepTest.java.tmpl`、`templates/DomainAbilityTest.java.tmpl`
- 断言 checklist：`templates/mapper_service_assertion_checklist.md`
