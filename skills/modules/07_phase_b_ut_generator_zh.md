# Phase B: TDD需求驱动单测生成 (测试大纲建模与实施)

# /ut-generator: 需求驱动的单测实施体系

本阶段负责承接 Phase A 输出的结构化需求，在功能代码写完进行提测或入库前，强制采用大模型按照架构规范生成单元测试场景大纲（EUT）与测试代码本体，实现真正的"TDD 左移"。

> **技术栈基线**：本阶段默认使用 Java + DDD + TMF 基线。
> 基线按项目 profile 选择：
> - `java-ddd-tmf`：`references/java-ddd-tmf-baseline.md`
> - `go-service`：`references/go-service-baseline.md`
> 未指定 profile 时回退 Java 默认基线。

## 核心指导思想 (遵守 TDD)

1. **以审带写**：这个阶段生成的测试思路，必须要能够 100% 满足下一阶段（Phase C）中严格的单测覆盖审计基线（重点照顾断言和异常检测）。
2. **脱离伪覆盖（EUT 建设）**：禁止直接根据源码里的 `if-else` 分支反推用例（由于代码可能已经写错，这会导致反推单测"测试了错误的实现"）。强制基于 `REQ/BR/SE` 生成测试用例大纲（Expected Unit Test, EUT）。
3. **断言约束**：生成代码时严禁出现只有执行流的"空气单测"。基于 DDD 与 TMF 模型，要求必须断言：状态机的改变、对外部的副作用交互次数（Mockito.verify）以及数据库核心字段的写入。

## 执行流程

### Step 1: 契约模型与场景树解构（EUT 建模）

在让大模型或研发编写 Java 单测前，基于 Phase A 的产物建立独立的 EUT 矩阵大纲：

1. **正常流（Happy Path）**：针对主需求 `REQ`/分支需求 `BR` 构建无错调用图景。
2. **边界流（Boundary）**：针对 `SE` 中定义的数值阈值、越权漏洞、临界时间戳做参数等价类组合。
3. **异常流（Exception）**：对于微服务和 TMF 架构，强制枚举：
  - TMF 中 `Extension` 缺失、`decideSteps` 判断失败或某一个 Ability 执行抛错降级的路径。
  - Infrastructure 层 RPC 调用引发超时、限流错误（模拟返回 5xx 等）。
  - Domain 并发情况下的乐观锁冲突及业务异常。

### Step 2: 架构上下文（DDD+TMF）代码脚手架生成

生成单测结构时，严格遵照您的分层职责界限：

1. 对 **Application / CmdExe**：主要运用 `Mockito` 编排下层服务，重在测试领域委托是否准确，**拒绝混入大量核心业务规则与事务测算**。
2. 对 **Domain Step / Service**：基于 TMF，遇到调用 Ability 必须 `mock TMF.findAbility()`；如果有 `@DomainStep` 回滚机制，必须强制生成触发 `process()` 失败进而走到 `rollback()` 的完整链路。
3. 对 **Infrastructure Gateway**：必须通过轻量级内存库句柄或数据层 Mock，明确断言数据持久化动作正确、时间戳（创建更新时间）和新增业务字段无少录错录。

*(参考随附的 TDD 架构测试骨架：`templates/DomainStepTest.java.tmpl` 与 `DomainAbilityTest.java.tmpl`)*

### Step 3: 单测强断言约束代码实现

要求 AI 在最终产出 `@Test` 代码时落实以下操作规程：

- **写行为断言**：测试最后必须包含 `assertEquals` 校验数据库提取出的某业务关键字段最新值。
- **副作用验证**：需在 `finally` 或方法末尾用 `Mockito.verify(client, times(1)).doAction(...)` 来严格测算副产物生成逻辑。
- **精确异常拦截**：捕获异常必须有对具体异常类型与错误码的检测，比如 `assertEquals(ExpectedBizCode.ILLEGAL_STATE, ex.getCode())`。不能使用无脑 `try{...}catch(Exception e){}` 将异常静默吞掉。

## 卡点约束（输出门禁要求）

1. 每在代码中输出一个 EUT 单测实现，必须在该方法的注释或 `@DisplayName` 里标注其关联哪一个需求点的语义（例如：`// 对应: SEM-014 当越权访问时拦截`）。
2. 如果存在难以 mock 或无法用标准断言提取的核心 `SE`，禁止随意跳过免测。这通常意味着业务代码本身的类结构过度耦合（可测性差），必须上报进行重构干预，保证其符合 TDD 基石属性。
