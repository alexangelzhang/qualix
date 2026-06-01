# Test Generation Rules

Q05b 单测代码生成规则参考。供 `skills/unit-test-codegen/SKILL.md` 在 Step 2 中引用。

---

## Layered Responsibility

单测代码遵循分层职责界限：

| 层次 | 职责 | 禁止 |
|------|------|------|
| **Given** | 构造测试数据、Mock 行为 | 不得在 given 中断言 |
| **When** | 调用被测方法一次 | 不得调用多次；不得在 when 中断言 |
| **Then** | 精确断言：assertEquals/assertThrows/verify 等 | 不得用 assertTrue(true)；不得仅捕获 NPE |

---

## Assertion Strength Rules

1. **强断言优先**：使用 `assertEquals(expected, actual)`、`assertThrows(ExceptionClass.class, () -> ...)`、`verify(mock, times(N)).method(...)` 等具体断言
2. **禁止弱断言**：`assertTrue(true)`、`assertNotNull(result)` 仅在 EUT `then` 字段明确说明时允许
3. **异常测试**：必须断言具体异常类型；禁止 `try { ... } catch (Exception e) { assertTrue(!(e instanceof NullPointerException)); }`
4. **EUT 追溯注释**：每个 @Test 方法第一行必须有 `// EUT-xxx` 注释（C9 精确模式依赖此）

---

## Skeleton Contract

Q05b 采用 **Skeleton Preamble** 机制，在每批 @Test 代码生成前注入目标类的真实方法签名，防止 Agent 幻觉方法名导致编译失败。

### 工作原理

1. **Agent 在 Step 2.0 中调用 `extract_skeleton_for_files(file_paths)`**，获取当前批次目标类的骨架文本（`SkeletonResult.skeleton_text`）
2. **骨架以 fenced block 方式前置呈现**，标题为 `## Available Methods (do not invent others)`
3. 骨架包含：package 声明、import 列表、类签名、字段声明、方法签名（省略方法体，显示 `{ ... }`）

### 硬性约束

| 约束 | 说明 |
|------|------|
| **只调用骨架中的方法** | Agent 生成的 @Test 代码只允许调用 preamble 骨架中已列出的方法签名 |
| **禁止发明方法名** | 若 EUT 的 `when`/`then` 所需方法在骨架中不存在，**不得凭空发明** |
| **缺失方法 → 标注 OPEN** | 将该 EUT 的 `passes` 保持 `false`，`failure_reason` 写 `"需要方法 <method_name> 但在骨架中未找到"`，等待人工确认 |
| **骨架 = 唯一真相** | 不得依赖 LLM 训练数据中对该类方法的"记忆"；骨架来自实际源代码 AST，优先级高于任何先验知识 |

### 典型错误场景

```java
// 错误：Agent 发明了 isLogisticExchange() 但实际方法名是 isLogisticExchangeService()
logisticExchangeIdentifyManager.isLogisticExchange("SVC001");  // 编译失败

// 正确：从骨架中确认方法签名后调用
logisticExchangeIdentifyManager.isLogisticExchangeService("SVC001");
```

### Compile Error Feedback 机制

当 `mvn test-compile` 失败时，SKILL.md Step 3.2 会：
1. 解析 stderr 中的 `cannot find symbol` 错误
2. 将每条错误以 `C-N. [compile] <symbol> not found in <class> — known methods: [...]` 格式追加到 `_handoff_iter{N}.md`
3. Fixer 在下一轮读取这些 `C-N` 条目，对照 `known methods` 列表选择正确方法名

此机制与 `handoff_builder.py` 的 `S-N. [schema]` schema 错误注入模式一致，Fixer 可统一处理。

---

## Mock Setup Rules

1. **Mock 最小化**：只 Mock 当前 EUT 的 `given` 字段明确列出的行为
2. **静态 Mock 谨慎**：`MockedStatic` 需要 try-with-resources；避免在同一测试类中对同一静态类多次 Mock
3. **Mock 作用域**：`@Mock` 字段在 `@BeforeEach` 中初始化，不在单个 @Test 内重复 init
4. **verify 精度**：`verify(mock, times(1))` 优于 `verify(mock)`（后者等价于 `times(1)` 但明确意图更清晰）

---

## Naming Conventions

| 元素 | 规范 |
|------|------|
| 测试类名 | `<被测类名>Test.java`，放在 `src/test/java/` 对应包路径下 |
| @Test 方法名 | `<被测方法>_<场景描述>_<期望结果>()`，中文描述用下划线分隔 |
| EUT 注释 | `// EUT-xxx SE-yyy <Happy/Exception/Boundary> Path: <场景简述>` |

---

## DDD+TMF Mock Templates

以下模板为各 DDD 层级定义正确的 `@ExtendWith(MockitoExtension.class)` + `@InjectMocks` + `@Mock`
setup block。根据被测类所属层级选择对应模板。

### 1. Domain Service

Domain Service 持有业务逻辑，依赖 Repository/Port 接口。

```java
@ExtendWith(MockitoExtension.class)
class OrderDomainServiceTest {

    @InjectMocks
    private OrderDomainService orderDomainService;   // 被测类

    @Mock
    private OrderRepository orderRepository;         // 持久化端口（接口）

    @Mock
    private InventoryPort inventoryPort;             // 出站端口（接口）

    @Test
    // SE-001 / EUT-001
    void shouldReserveInventoryWhenOrderPlaced() {
        // given
        when(inventoryPort.reserve(anyString(), anyInt())).thenReturn(true);
        // when
        orderDomainService.placeOrder(new Order("SKU-1", 2));
        // then
        verify(inventoryPort, times(1)).reserve("SKU-1", 2);
    }
}
```

**规则：**
- `@InjectMocks` 目标为 DomainService 本身。
- `@Mock` 字段为 Repository 或 Port **接口**，不得 Mock 具体基础设施实现类。
- 不得通过 ApplicationService 来测试 DomainService 逻辑，应直接测试领域层。

---

### 2. Application Service

Application Service 编排 Domain Service，**不得直接依赖 Repository**。

```java
@ExtendWith(MockitoExtension.class)
class OrderApplicationServiceTest {

    @InjectMocks
    private OrderApplicationService orderApplicationService;

    @Mock
    private OrderDomainService orderDomainService;           // 领域层依赖 ✓

    @Mock
    private NotificationDomainService notificationDomainService;

    // 禁止：@Mock OrderRepository orderRepository;
    // 原因：直接 Mock Repository 会绕过领域层，破坏 DDD 层级边界

    @Test
    // SE-002 / EUT-002
    void shouldNotifyCustomerAfterOrderConfirmed() {
        // given
        Order order = new Order("ORD-1");
        when(orderDomainService.confirmOrder("ORD-1")).thenReturn(order);
        // when
        orderApplicationService.confirmAndNotify("ORD-1");
        // then
        verify(notificationDomainService).sendConfirmation(order);
    }
}
```

**规则：**
- `@InjectMocks` 目标为 ApplicationService。
- `@Mock` 字段必须是 DomainService，**绝对不允许直接 Mock Repository 或 Mapper**。
- Application Service 直接 Mock Repository 是层级违规：绕过领域层，把测试耦合到基础设施关注点。
  `check_mock_consistency` 会自动检测此问题并产生 WARNING。

---

### 3. Infrastructure Adapter

适配器（持久化适配器、REST 客户端、消息发布者）通常依赖框架管理的构造器。
`@InjectMocks` 在此**不可靠**——改用构造器注入。

```java
@ExtendWith(MockitoExtension.class)
class JpaOrderAdapterTest {

    // 禁止：@InjectMocks JpaOrderAdapter adapter;
    // 原因：适配器通常没有无参构造器，Mockito 注入会静默失败
    private JpaOrderAdapter adapter;

    @Mock
    private OrderJpaRepository jpaRepository;   // Spring Data 仓库（基础设施）

    @BeforeEach
    void setUp() {
        adapter = new JpaOrderAdapter(jpaRepository);   // 显式构造
    }

    @Test
    // SE-003 / EUT-003
    void shouldPersistOrderEntity() {
        // given
        OrderEntity entity = new OrderEntity("ORD-1");
        when(jpaRepository.save(entity)).thenReturn(entity);
        // when
        adapter.save(new Order("ORD-1"));
        // then
        verify(jpaRepository).save(any(OrderEntity.class));
    }
}
```

**规则：**
- 适配器常无无参构造器，`@InjectMocks` 注入可能静默失败。
- 始终在 `@BeforeEach` 中使用 `new Adapter(mockDep)` 显式构造。
- 此层的 `@Mock` 字段可以是底层框架仓库或 HTTP 客户端——基础设施依赖在此层是合法的。

---

### @InjectMocks 使用限制

| 场景 | 行为 | 推荐修复 |
|------|------|---------|
| 内部类（`Outer$Inner`） | `@InjectMocks` 无效 | 改用构造器注入 |
| `final` 类 | Mockito 无法生成子类 | 使用 `MockMaker.INLINE` 或重构为接口 |
| 无无参构造器 | 注入静默失败 | 在 `@BeforeEach` 中显式调用构造器 |

### verify() 调用次数

| 表达式 | 含义 |
|--------|------|
| `verify(mock)` | 恰好 1 次调用（等同于 `verify(mock, times(1))`） |
| `verify(mock, times(N))` | 恰好 N 次调用，N > 1 时必须显式写出 |
| `verify(mock, never())` | 零次调用 |
| `verify(mock, atLeastOnce())` | 至少 1 次调用 |

**常见错误：** 期望调用 2 次时忘写 `times(2)`，导致测试在只调用 1 次时也通过，是覆盖缺口。

### 层级边界速查

```
ApplicationService  →  @Mock DomainService          ✓  正确
ApplicationService  →  @Mock Repository              ✗  层级违规
DomainService       →  @Mock Repository/Port         ✓  正确
InfraAdapter        →  constructor(mockJpaRepo)       ✓  正确
InfraAdapter        →  @InjectMocks                  ✗  静默失败风险
Inner class         →  @InjectMocks                  ✗  不支持
```

---

## Runtime Failure Feedback Format

Q05b Ralph Loop 在每批 `mvn test` 失败时，将结构化运行时失败信息注入 `_handoff_iter{N}.md`，供下一轮 Fixer 定点修复。本节描述该格式规范。

### 前缀约定

| 前缀 | 来源 | 注入来源 |
|------|------|---------|
| `S-N. [schema]` | Q05a/Q05b JSON schema 校验失败 | `handoff_builder.py` |
| `C-N. [compile]` | `mvn test-compile` 编译失败 | SKILL.md Step 3.2 |
| `R-N. [runtime]` | `mvn test` 运行时测试失败 | SKILL.md Step 3.3 |

三类前缀统一注入同一个 `_handoff_iter{N}.md` 文件，Fixer 读取后统一处理。

### 如何定位 Surefire XML 报告

Maven Surefire 插件在每次 `mvn test` 后将测试结果写入 XML：

```
<module-root>/target/surefire-reports/<全限定类名>.xml
```

多模块项目中，每个子模块有各自的 `target/` 目录，例如：

```
maf-srv-service/target/surefire-reports/com.example.FooTest.xml
maf-service-provider/target/surefire-reports/com.example.BarTest.xml
maf-srv-aftersale/target/surefire-reports/com.example.BazTest.xml
```

遍历所有模块时，使用 glob 模式：`*/target/surefire-reports/*.xml`。

### 从 XML 中提取的信息

Surefire XML 的 `<testcase>` 元素示例：

```xml
<testcase classname="com.example.FooTest" name="testBar_正常路径" time="0.123">
  <failure message="expected:&lt;200&gt; but was:&lt;500&gt;" type="org.opentest4j.AssertionFailedError">
org.opentest4j.AssertionFailedError: expected:&lt;200&gt; but was:&lt;500&gt;
    at com.example.FooTest.testBar_正常路径(FooTest.java:42)
    at java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
  </failure>
</testcase>
```

对每个包含 `<failure>` 或 `<error>` 子元素的 `<testcase>`，提取：

| 字段 | 来源 | 说明 |
|------|------|------|
| `TestClass` | `classname` 属性 | 取简单类名（最后一段），去掉包名 |
| `method` | `name` 属性 | 完整方法名 |
| `failure_message_first_line` | `<failure>` 或 `<error>` 文本第一行 | 截断到换行符前 |
| `L`（行号） | `<failure>` body 中第一个含测试类名的 `at` 行 | 从括号内提取数字 |

### 格式模板

```
R-N. [runtime] {TestClass}#{method}: {failure_message_first_line} (line {L})
```

示例：

```
R-1. [runtime] FooTest#testBar_正常路径: expected:<200> but was:<500> (line 42)
R-2. [runtime] BazTest#testQux_异常场景: NullPointerException (line 87)
→ Likely layer mismatch — see DDD+TMF Mock Templates in references/test-generation-rules.md
```

- `R-N` 编号从 1 开始，在同一 handoff 文档内全局递增（跨测试类连续编号）
- 行号 `L` 不可用时写 `(line ?)`
- 提示行紧跟在触发 NPE 提示的 `R-N` 行之后，不单独编号

### NPE → 层级错误提示触发条件

当同时满足以下两个条件时，在对应 `R-N` 行之后追加提示：

1. 失败消息（`failure_message_first_line`）包含字符串 `NullPointerException`
2. 堆栈帧指向的行（行号 `L`）疑似 Mock 字段访问——即代码中该行形如 `mockField.someMethod(...)` 或字段名与测试类的 `@Mock` 声明一致

追加内容：
```
→ Likely layer mismatch — see DDD+TMF Mock Templates in references/test-generation-rules.md
```

**典型触发场景**：ApplicationService 测试中直接 `@Mock Repository` 而非 `@Mock DomainService`，导致领域层调用 null 而抛出 NPE。此提示引导 Fixer 参照 DDD+TMF 模板（本文件 `## DDD+TMF Mock Templates` 章节）检查层级边界。

### handoff 文档结构（多类错误并存时）

同一迭代中，`_handoff_iter{N}.md` 可同时包含多类错误块，各块独立：

```markdown
## Compile Errors

C-1. [compile] fooBar not found in MyService — known methods: [doFoo, doBar, validate]

## Runtime Failures (fix in next iteration)

R-1. [runtime] MyServiceTest#testFoo_正常路径: expected:<true> but was:<false> (line 55)
R-2. [runtime] MyServiceTest#testBar_异常场景: NullPointerException (line 88)
→ Likely layer mismatch — see DDD+TMF Mock Templates in references/test-generation-rules.md
```

Fixer 在下一轮先修 `C-N` 编译错误（优先级更高，运行时错误可能由此触发），再修 `R-N` 运行时错误。
