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

严格遵照分层职责界限，详见 `references/test-generation-rules.md`：

**必须遵守：**
- 每个 @Test 方法必须有 `// EUT-xxx` 追溯注释（C9 精确模式依赖此注释）
- then 字段描述的断言必须在代码里实现（assertEquals/assertThrows/verify 等）
- 禁止 try/catch 仅防 NPE 的弱断言（Q05 历史错误模式）
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
from dqg.quality.checks.q05_structure_checks import _check_eut_implementation_completeness
errors = _check_eut_implementation_completeness(phase_b_data, [test_file_path])
# 有 BLOCKED → 本批未完成，继续补充
```

**3.2 编译验证**

```bash
# Java: 确认测试代码能编译（offline 模式依赖本地 Maven cache）
mvn test-compile -pl <module> -am -o -q
```

### Step 4: 更新进度

验证通过后：
1. 更新 `phase_b_code_status.json`：本批 EUT 的 `passes: true`，填写 `test_file`、`test_method`
2. 记录到 `codegen_progress.md`：每批完成情况（几条 EUT / 测试文件 / 用时）
3. 继续 Step 1：取下一批

### Step 5: 完成条件

**所有 EUT `passes: true`** → Q05b 完成，可 finalize。

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
