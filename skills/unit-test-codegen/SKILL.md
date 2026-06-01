---
name: unit-test-codegen
description: "Phase Q05b: 单测代码生成——以 Q05a approved 的 EUT 矩阵为规格，按 Ralph Loop 模式逐批生成 @Test 方法，每批后跑 C9/C10 deterministic gate，直到所有 EUT passes:true。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q05b
  depends_on: [Q05a]
  outputs: [codegen_progress.md, phase_b_code_status.json, "@Test 代码文件"]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q05b: 单测代码生成（Ralph Loop）

> **Q05b 的唯一职责：把 Q05a approved 的 EUT 矩阵，逐条实现为编译通过、断言有效的 @Test 方法。**

IRON LAW: Q05b 不修改 EUT 矩阵。若发现 EUT 设计有问题，标注并上报，等人工决策后回到 Q05a 修正。

---

## Ralph Loop 模式

Q05b 的执行遵循 Ralph Loop（来源：github.com/snarktank/ralph）：

```
读取 phase_b_code_status.json
→ 取一批 passes:false 的 EUT（按被测类分组，每次 3-5 条）
→ 为这批 EUT 写 @Test 方法
→ 验证：C9 check + mvn test-compile
→ 通过 → 更新 passes:true → 取下一批
→ 所有 passes:true → 完成
```

**关键原则：**
- 每批独立，不混批（一批失败不影响其他批）
- 不通过不 commit，保持 git history 干净
- Exit condition 是确定性的（C9 + 编译），不是 LLM 主观判断

---

## 前置依赖

- Phase Q05a 产物：`output/<project>/Q05a/phase_b_structured.json`（approved EUT 矩阵）
- 代码仓库（含 src/test/java 目录）

## 上下文加载

1. 读取 `output/<project>/Q05a/phase_b_structured.json`——这是锁定的规格，不得修改
2. 读取或初始化 `phase_b_code_status.json`（每条 EUT 的 `passes` 状态）
3. 读取 `_upstream_context.md`（技术栈基线）
4. 读取 `_internal/_q05_target_modules.json`（目标类清单）

---

## 执行流程

### Step 0: 初始化进度追踪

读取或创建 `phase_b_code_status.json`：

```json
{
  "project_id": "maf-srv-service",
  "total": 67,
  "done": 0,
  "tasks": [
    {
      "eut_id": "EUT-007",
      "class": "Cn3cProcessMethodValidateExt",
      "method": "validateMethod",
      "passes": false,
      "test_file": null,
      "test_method": null,
      "failure_reason": null
    }
  ]
}
```

规则：
- 首次执行：从 `phase_b_structured.json` 的 `eut_items` 初始化所有 EUT 为 `passes: false`
- 续跑：直接读取现有 `phase_b_code_status.json`，跳过已 `passes: true` 的条目

### Step 1: 按类分组，选取一批

1. 从 `phase_b_code_status.json` 找所有 `passes: false` 的 EUT
2. 按 `class`（被测类名）分组
3. 选取一个类的全部 EUT（该类所有 EUT 一次写完，避免测试文件多次修改）
4. 若某个类有超过 8 条 EUT，拆成两批（先 Happy/Exception，后 Boundary/Concurrent）

### Step 2: 写 @Test 方法

严格遵照分层职责界限，详见 `references/test-generation-rules.md`。

#### Step 2.0: Skeleton 前置注入（每批必须先做）

**在为每批 EUT 写代码之前**，必须先提取目标类的方法骨架，生成 Skeleton Preamble：

```python
from pathlib import Path
from qualix.context.analysis.code_skeleton import extract_skeleton_for_files

# 从 _q05_target_modules.json 找出当前批次目标类对应的文件路径
# file_paths 是当前批次目标类的 Path 对象列表
skeleton_results = extract_skeleton_for_files(file_paths)

# 拼接 preamble
preamble_parts = []
for file_path_str, result in skeleton_results.items():
    preamble_parts.append(result.skeleton_text)
skeleton_preamble = "\n\n".join(preamble_parts)
```

将 skeleton_preamble 以如下格式前置在写 @Test 方法前呈现：

```
## Available Methods (do not invent others)

```java
<skeleton_preamble 内容>
```
```

**Skeleton 契约（强制）：**
- Agent 只能调用 preamble 中列出的方法；禁止调用任何 preamble 未出现的方法名
- 若某个 EUT 的 `when` 或 `then` 需要调用 preamble 中不存在的方法，**不得凭空发明**——将该 EUT 标注为 `passes: false`（failure_reason: "需要方法 <method_name> 但在骨架中未找到"）并跳过，等待人工确认
- 详见 `references/test-generation-rules.md` 的 "Skeleton Contract" 章节

**必须遵守：**
- 每个 @Test 方法必须有 `// EUT-xxx` 追溯注释（C9 精确模式依赖此注释）
- then 字段描述的断言必须在代码里实现（assertEquals/assertThrows/verify 等）
- 禁止 try/catch 仅防 NPE 的弱断言（Q05a 历史错误模式）
- 禁止 `assertTrue(true)` 占位符

**@Test 方法模板：**
```java
/**
 * EUT-007 SE-003 Happy Path: 远程维修工单 → 跳过所有校验
 */
@Test
public void validateMethod_远程维修工单_跳过所有校验() throws Exception {
    // given - 按 EUT given 字段构造
    DetectionProcessSrvVo vo = new DetectionProcessSrvVo();
    vo.setRemoteMaintenance(true);

    // when - 按 EUT when 字段调用
    ext.validateMethod(mock(ServiceDomainModel.class), context);

    // then - 按 EUT then 字段断言（具体断言，非模糊）
    verify(logisticExchangeIdentifyManager, never()).isLogisticExchangeService("SVC001");
}
```

### Step 3: 验证（Deterministic Gate）

每批写完后必须验证：

**3.1 C9 检查（EUT 追溯覆盖）**

```python
# 检查刚写的 EUT 是否在测试代码里有 // EUT-xxx 注释
from qualix.quality.checks.q05_structure_checks import _check_eut_implementation_completeness
errors = _check_eut_implementation_completeness(phase_b_data, [test_file_path])
# 有 BLOCKED → 本批未完成，继续补充
```

**3.2 编译验证**

```bash
# Java: 确认测试代码能编译（offline 模式依赖本地 Maven cache）
# 捕获 stderr 用于错误解析
mvn test-compile -pl <module> -am -o 2>&1 | tee /tmp/mvn_compile_stderr.txt
```

**编译失败时——解析错误并注入 handoff（必须执行）：**

当 `mvn test-compile` 返回非零退出码时，执行以下解析和注入流程：

1. **解析 `cannot find symbol` 错误**：
   ```
   # 从编译输出中提取 cannot find symbol 错误
   # 匹配格式示例：
   #   error: cannot find symbol
   #     symbol: method fooBar(String)
   #     location: class com.example.MyClass
   ```
   对于每条 `cannot find symbol` 错误，提取：
   - `symbol_name`：`symbol: method/variable/class <name>` 中的 `<name>`
   - `class_name`：`location: class <ClassName>` 中的 `<ClassName>`（取简单类名）

2. **查询已提取的骨架（使用本批 Step 2.0 的 skeleton_results）**：
   对每个出错的 `class_name`，从 `skeleton_results` 中找到对应的 `SkeletonResult`，
   从 `skeleton_results[class_name].classes[0].methods` 提取各 `method.name`，以逗号连接作为已知方法列表。

3. **追加编译错误块到当前迭代的 handoff 文档**：
   在 `_handoff_iter{N}.md`（N = 当前轮次编号）末尾追加：
   ```markdown
   ## Compile Errors

   C-1. [compile] <symbol_name> not found in <class_name> — known methods: [<methods from skeleton>]
   C-2. [compile] <symbol_name2> not found in <class_name2> — known methods: [<methods from skeleton>]
   ```
   - `C-N` 编号从 1 开始，每条错误递增
   - `known methods` 列出该类骨架中所有方法名（以逗号分隔），供 Fixer 选择正确方法
   - 若某 class_name 不在 skeleton_results 中，`known methods` 写 `(unknown — check source file)`

4. **不标记 passes: true**：本批所有 EUT 保持 `passes: false`；下一轮 Fixer 读取 `_handoff_iter{N}.md` 中的 `C-N` 条目修正方法名后重试。

> **设计说明**：此错误注入格式与 `handoff_builder.py` 的 `S-N. [schema]` 模式一致（见该文件第 52-56 行）——`C-N. [compile]` 是其编译错误对应形式，Fixer 可以统一处理两类错误。

**3.3 运行时失败诊断（每批 mvn test 运行后执行）**

每批 EUT 编译通过后，运行测试并捕获 Surefire 报告：

```bash
# 运行当前批次的测试，不因失败中断
mvn test -pl <module> -am -o -Dmaven.test.failure.ignore=true 2>&1 | tee /tmp/mvn_test_stdout.txt
```

**When `mvn test` FAILS（有 `<failure>` 或 `<error>` 的 testcase）：**

1. **定位 Surefire XML 报告**：在每个 code repo 模块下的 `target/surefire-reports/*.xml`  
   多模块项目中每个子模块有各自的 `target/` 目录，例如：
   ```
   maf-srv-service/target/surefire-reports/com.example.FooTest.xml
   maf-service-provider/target/surefire-reports/com.example.BarTest.xml
   ```

2. **从 XML 中提取失败信息**：对每个包含 `<failure>` 或 `<error>` 子元素的 `<testcase>` 元素，提取：
   - `classname` 属性（测试类全限定名，取简单类名用于展示）
   - `name` 属性（测试方法名）
   - 失败消息：`<failure>` 或 `<error>` 元素文本内容的**第一行**
   - 堆栈帧：从 `<failure>` body 中找第一个指向测试文件的行（含测试类名的 `at` 行），提取行号 `L`

3. **格式化每条运行时失败**：
   ```
   R-N. [runtime] {TestClass}#{method}: {failure_message_first_line} (line {L})
   ```
   `R-N` 编号从 1 开始，每条失败递增；`N` 在同一 handoff 文档中全局连续。

4. **NPE → 层级错误提示**：若失败消息包含 `NullPointerException` **且**堆栈帧指向的行中有 Mock 字段访问（形如 `mockField.method(...)` 或字段名与 `@Mock` 声明一致），追加提示行：
   ```
   → Likely layer mismatch — see DDD+TMF Mock Templates in references/test-generation-rules.md
   ```

5. **追加运行时失败块到当前迭代的 handoff 文档**：在 `_handoff_iter{N}.md` 末尾追加（与 `## Compile Errors` 同文件，独立章节）：
   ```markdown
   ## Runtime Failures (fix in next iteration)

   R-1. [runtime] FooTest#testBar_正常路径: expected:<200> but was:<500> (line 42)
   R-2. [runtime] BazTest#testQux_异常场景: NullPointerException (line 87)
   → Likely layer mismatch — see DDD+TMF Mock Templates in references/test-generation-rules.md
   ```

6. **不标记 passes: true**：本批所有失败 EUT 保持 `passes: false`；回到 Step 2 进入 fixer 模式，读取 `_handoff_iter{N}.md` 中的 `R-N` 条目修正运行时问题后重试。

> **设计说明**：`R-N. [runtime]` 前缀与 `C-N. [compile]`（Step 3.2）和 `S-N. [schema]`（`handoff_builder.py`）保持同一命名约定，Fixer 可统一处理三类错误，无需区分来源。

**3.4 覆盖率验证（所有 EUT passes:true 后执行一次）**

当 `phase_b_code_status.json` 中所有 EUT `passes: true` 时，运行 JaCoCo 并验证覆盖率：

```bash
# 全模块运行，所有有变更的子模块都必须覆盖
mvn test -am -o -Dmaven.test.failure.ignore=true
mvn org.jacoco:jacoco-maven-plugin:0.8.12:report -am -o -q
```

> **注意**：不能只跑单个模块（如 `-pl maf-srv-service`），需要覆盖所有有变更的模块（包括 maf-service-provider、maf-srv-aftersale 等）。

解析 `target/site/jacoco/jacoco.xml`，对 git diff 变更的被测类汇总：
- **增量行覆盖率 = 100%**（公司硬性指标）
- **增量分支覆盖率 = 100%**（公司硬性指标）

若覆盖率不达标：
1. 识别 JaCoCo 报告中哪些方法/分支未被覆盖（missed > 0）
2. 针对每个未覆盖分支，在 `phase_b_code_status.json` 追加新 EUT 条目（`passes: false`）
3. 回到 Step 1，继续 Ralph Loop 补充覆盖
4. 直到覆盖率 ≥ 80% 且所有 passes:true

### Step 4: 更新进度

验证通过后：
1. 更新 `phase_b_code_status.json`：本批 EUT 的 `passes: true`，填写 `test_file`、`test_method`
2. 记录到 `codegen_progress.md`：每批完成情况（几条 EUT / 测试文件 / 用时）
3. 继续 Step 1：取下一批

### Step 5: 完成条件

**两个条件同时满足** → Q05b 完成，可 finalize：
1. 所有 EUT `passes: true`
2. **增量行覆盖率 ≥ 80% AND 增量分支覆盖率 ≥ 80%**（Step 3.4 验证通过）

若只满足条件 1 但覆盖率不足：按 Step 3.4 补充 EUT → 继续 Ralph Loop。

输出 `codegen_progress.md`：

```markdown
# Q05b 代码生成进度报告

## 总结
- 总 EUT 数: 67
- 已实现: 67 (100%)
- 测试文件: 6 个
- @Test 方法: 67 个

## 逐类明细
| 被测类 | EUT 数 | 测试文件 |
|--------|--------|---------|
| Cn3cProcessMethodValidateExt | 3 | Cn3cProcessMethodValidateExtTest.java |
...
```

---

## 关键门禁（finalize）

| 检查 | 级别 | 说明 |
|------|------|------|
| C9: 所有 EUT 有对应 @Test 方法（EUT-xxx 注释） | BLOCKED | 标注存在性 |
| **C1+C2: EUT then 字段关键词必须出现在 @Test 方法体内** | **WARNING** | **实现和设计一致性** |
| C10: git diff 实现类全部有 EUT 覆盖 | BLOCKED | 无漏网之鱼 |
| **增量行覆盖率 = 100%**（公司硬性指标） | **BLOCKED** | **JaCoCo 实测值** |
| **增量分支覆盖率 = 100%**（公司硬性指标） | **BLOCKED** | **JaCoCo 实测值** |
| 编译通过（mvn test-compile） | BLOCKED | 无幻觉方法名 |
| 推理日志存在 | BLOCKED | 执行记录 |
| 弱断言检测（try/catch 仅防 NPE） | WARNING | 断言强度 |

**C1+C2 的意义**：C9 只验证"有没有"，C1+C2 验证"对不对"。
EUT-012 的 then 说 `verify(orderService, times(1)).createOrder(any())`，
如果对应 @Test 只做 `assertNull(result)`，C9 通过但 C1+C2 会标记 WARNING。
这确保测试代码实现的是 EUT 矩阵设计的业务语义，而不是退化为防御性空壳测试。

---

## 典型错误模式（禁止）

| 错误模式 | 后果 | 正确做法 |
|---------|------|---------|
| try/catch 仅 `assert !(e instanceof NPE)` | C9 降级 WRONG_TARGET | 使用 `assertNull(result)` 或具体业务断言 |
| 无 `// EUT-xxx` 追溯注释 | C9 精确模式失败 | 每个 @Test 必须有注释 |
| 方法名使用不存在的 mock 方法 | 编译失败 | 先 Read 生产代码确认方法签名 |
| JSON 里写了 EUT 但没写 @Test | C9 BLOCKED | 按 Ralph Loop 一次写完一批 |
| 修改 phase_b_structured.json | 违反 IRON LAW | 标注问题，等 Q05a 修正 |

---

## 禁止事项

- 禁止修改 Q05a 产出的 `phase_b_structured.json`（EUT 矩阵是 approved 规格）
- 禁止 `assertTrue(true)` 占位符
- 禁止跳过 C9 验证直接标记 `passes: true`
- 禁止混批（一批多个类混写）
