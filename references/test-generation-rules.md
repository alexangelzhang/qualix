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
