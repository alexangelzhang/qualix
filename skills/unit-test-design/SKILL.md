---
name: unit-test-design
description: "Phase Q05a: EUT 矩阵设计——三层驱动确定目标模块，设计覆盖 REQ/BR/SE + git diff 的完整测试矩阵，人工 approve 后锁定为 Q05b 的代码生成规格。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q05a
  depends_on: [Q01]
  outputs: [eut_matrix.md, phase_b_structured.json, _reasoning_log.md]
  applies_to: [Java, TypeScript]
  hard_checks:
    - 每条 EUT 的 then 字段必须包含具体断言（assertEquals/assertNotNull/verify 等）
    - bound_se 必须指向真实存在的 SE-id（SE-001 格式）
    - 每条 EUT 必须对应一个可执行的 Java/@Test 方法
  evidence:
    bad: "then: 验证接口正确返回"
    good: "then: assertEquals(200, response.getStatus()) && assertNotNull(response.getOrderId())"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q05a: EUT 矩阵设计

> **Q05a 的唯一职责：设计完整、正确的 EUT 矩阵并让人工 approve。**
> 不写任何 @Test 代码——那是 Q05b 的工作。

**DQG 核心价值观：质量！质量！质量！**

> 测试是为了保证软件质量，防止线上 bug，让代码可信赖。REQ+BR+SE 是质量的需求来源，代码路径（Happy/Exception/Boundary/并发幂等）是质量的验证维度，两者叉积才是完整的质量证据。

IRON LAW: Q05a 只产出设计矩阵，禁止产出任何 Java 测试代码。

---

## EUT 矩阵设计核心原则（不可违反）

**两个维度必须同时满足：**

**维度 A（覆盖源）：需求维度 + 代码维度，缺一不可**

需求维度（Q01 产物）：
- 每条 REQ 必须有对应 EUT（`bound_item = "REQ-XXX"`）
- 每条 BR 必须有对应 EUT（`bound_item = "BR-XXX"`）
- 每条 SE 必须有对应 EUT（`bound_item = "SE-XXX"`）——SE 是 REQ/BR 的语义补充

代码维度（git diff 变更事实）：
- feature branch 相对 master 新增/修改的每个 Java 实现类，必须在某条 EUT 的 `when` 字段里出现
- git diff 中未被 REQ/BR/SE 引用的变更方法，也必须有 EUT——代码改了就必须证明它是对的
- gate 检查：`_check_q05_git_diff_coverage` 自动扫描 code_repo 的 `git diff origin/master...HEAD`

**维度 B（代码路径）：从实现代码视角分解执行路径**

| 路径类型 | 含义 | 要求 |
|---------|------|------|
| Happy Path | 代码主成功路径 | 每条 REQ/BR/SE ≥1 个，全局 ≥80% |
| Exception | 代码异常/错误分支 | 每条 REQ/BR/SE 100% 覆盖 |
| Boundary | 代码边界条件（null/空/最大值） | 有边界语义的条目 100% |
| Concurrent | 并发/幂等/多线程竞态 | 有并发/幂等语义时 100% |

**维度 C（覆盖率投影覆盖率 = 100%（公司硬性指标）**

Q05a 设计阶段必须对每个目标类做静态覆盖率投影：
- 扫描生产代码，统计每个方法的 `if/else/switch/ternary` 分支总数和 `try/catch` 路径
- 对每个分支，检查至少有 1 条 EUT 的 `when` 条件能触发它
- 投影行覆盖率 = 有 EUT 覆盖的行 / 总行数 = 100%（公司硬性指标）
- 投影分支覆盖率 = 有 EUT 覆盖的分支 / 总分支数 = 100%（公司硬性指标）

> 投影 < 100% 的 EUT 矩阵不允许 finalize。必须补充 EUT，直到每个被测类的投影覆盖率满足门限。

---

## 前置依赖

- Phase Q01 产出（REQ/BR/SE）

## 技术栈基线

按项目 profile 选择：
- `java-ddd-tmf` → `../../profiles/java-ddd-tmf/baseline.md`
- `go-service` → `references/go-service-baseline.md`

## 上下文加载原则

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档。
2. Phase Q01 结构化产物是唯一的需求基线。

---

## 执行流程

### Step 0: 输入确认与上下文加载

1. 确认 Phase Q01 产物存在（`phase_a_structured.json`）。
2. 确认代码仓库路径——**支持多仓库**。
3. 读取 `_upstream_context.md`。
4. 识别架构类型：`DDD / TMF / DDD+TMF`。

### Step 0.5: 目标模块确定（三层驱动，不可跳过）

**0.5a: BR/REQ→类映射（需求功能视角）**

1. 逐条读取 Phase Q01 的 REQ 和 BR 列表
2. 对每条 REQ/BR，在代码仓库中搜索对应实现类
3. 输出 `br_mappings`：

| BR/REQ ID | 描述 | 仓库 | 实现类 | 映射依据 |
|-----------|------|------|--------|---------|

**0.5b: SE→类映射（业务规则视角）**

1. 逐条读取 Phase Q01 的 SE 列表
2. 在代码仓库中搜索对应校验/规则类
3. 未找到的 SE 标记为 GAP

**0.5c: git diff→变更文件列表（代码变更视角）**

1. 对每个仓库执行 `git diff --name-only origin/master...HEAD`
2. 筛选本次修改的 .java 文件（排除 test/target/pom）
3. 按 DDD 分层标注优先级：P0 domain/P1 application/P2 infrastructure

**0.5d: 合并三个列表，取并集**

**0.5e: 必须输出 `_internal/_q05_target_modules.json`（finalize BLOCKED gate）**

```json
{
  "target_repos": ["maf-srv-service"],
  "git_diff_files": ["...LogisticExchangeIdentifyManager.java"],
  "se_mappings": [
    {"se_id": "SE-001", "impl_class": "LogisticExchangeIdentifyManager", "found": true, "gap_reason": null}
  ],
  "br_mappings": [
    {"br_id": "BR-001", "impl_class": "LogisticExchangeIdentifyManager", "repo": "maf-srv-service", "found": true, "gap_reason": null}
  ]
}
```

规则：
- `se_mappings` 必须覆盖 Q01 的所有 SE（未找到的填 `found: false` + `gap_reason`）
- `br_mappings` 必须覆盖 Q01 的所有后端可测 BR（**新增强制要求，旧 Q05 仅要求 se_mappings**）
- `git_diff_files` 必须非空（证明执行了 `git diff`，不能是 LLM 凭记忆填写）
- git diff 里的每个实现类必须出现在某条 EUT 的 `when` 字段（C10 BLOCKED gate）

### Step 1: EUT 矩阵设计（先算清楚需要什么）

**1.1 需求→用例设计（无代码也能做）**

逐条 REQ/BR/SE 设计测试用例（REQ/BR 是主体，SE 是补充验证）：

| bound_item | EUT ID | 用例描述 | 路径类型 | 被测类.方法 | 仓库 |
|-----------|--------|---------|---------|-----------|------|

规则：
- 每条 REQ ≥1 个 Happy Path EUT
- 每条 BR ≥1 个 Happy Path EUT + ≥1 个 Exception EUT
- 每条 SE 必须有对应 EUT
- 每条 EUT 的 `then` 必须包含具体断言（非模糊描述），参见 `phase_b_structured.json` schema 要求

**1.2 代码→用例补充（有分支代码时）**

对 Step 0.5c 中每个变更文件，扫描代码分支逻辑，自动补充用例：
- 每个 if/else/switch 分支至少 1 个用例
- 每个 try/catch 至少 1 个 Exception 用例
- null 检查、边界条件必须有 Boundary 用例

**1.3 设计矩阵自检（硬性 gate）**

| 指标 | 要求 |
|------|------|
| REQ 覆盖率 | 100% |
| 后端 BR 覆盖率 | 100% |
| SE 覆盖率 | 100% |
| git diff 实现类覆盖 | 100%（C10 gate） |
| Exception 路径 | 100% |
| then 字段具体性 | 100%（含具体断言/值/状态码） |
| **投影行覆盖率** | **= 100%（公司硬性指标）** |
| **投影分支覆盖率** | **= 100%（公司硬性指标）** |

**1.4 输出产物**

- `eut_matrix.md`：人类可读的 EUT 测试大纲
- `phase_b_structured.json`：机器可读的结构化 EUT 矩阵（遵循 phase_b schema）

```json
{
  "project_id": "maf-srv-service",
  "eut_items": [
    {
      "eut_id": "EUT-001",
      "bound_se": "SE-001",
      "bound_item": "SE-001",
      "route_type": "Happy Path",
      "given": "标准创建工单 DTO 传入",
      "when": "LogisticExchangeIdentifyManager.identify(dto)",
      "then": "assertEquals(IdentifyResult.MATCHED, result.getStatus())",
      "risk_tier": "T1"
    }
  ]
}
```

- `_internal/_q05_target_modules.json`：三层驱动产物

### Step 2: 自检（提交前强制检查）

- [ ] `_q05_target_modules.json` 存在，`br_mappings` + `se_mappings` + `git_diff_files` 全部非空
- [ ] 每条 REQ/BR/SE 都有对应 EUT（bound_item 非空）
- [ ] git diff 每个实现类都出现在某条 EUT 的 when 字段
- [ ] then 字段无模糊描述（无"验证成功"、"返回正确结果"等）
- [ ] 异常路径 100% 覆盖（每个 catch 分支有 Exception EUT）
- [ ] **每个被测类投影行覆盖率 = 100%**（静态分支枚举，不低于此门限不 finalize）
- [ ] **每个被测类投影覆盖率 = 100%（公司硬性指标）**（if/else/switch/catch 两侧各有 EUT）
- [ ] 推理日志 `_reasoning_log.md` 已输出

### Step 3: Judge/Critique

- **Judge**：对照 Q01 产物逐条验证 EUT 覆盖完整性
- **Critique**：假设有遗漏，重点检查 BR/git diff 覆盖
- 结果记录在报告末尾"自我评审记录"章节

---

## 关键门禁

| 检查 | 级别 |
|------|------|
| `_q05_target_modules.json` 存在且覆盖全部 SE | BLOCKED |
| `br_mappings` 覆盖全部后端 BR | BLOCKED |
| `git_diff_not_covered`（C10） | BLOCKED |
| then 字段模糊 | BLOCKED |
| **投影行覆盖率 < 100%（任一被测类）** | **BLOCKED** |
| **投影分支覆盖率 < 100%（任一被测类）** | **BLOCKED** |
| 推理日志存在 | BLOCKED |

## 通过标准

- 三层驱动产物完整（se_mappings + br_mappings + git_diff_files 全部非空）
- 每条 REQ/BR/SE 有直接 EUT，bound_item 非空
- git diff 每个实现类在某条 EUT 的 when 字段中有引用
- then 字段包含具体断言
- 人工 approve 后，`phase_b_structured.json` 锁定为 Q05b 代码生成规格

## 禁止事项

- 禁止产出任何 Java 测试代码（那是 Q05b 的工作）
- 禁止只按 SE 驱动——BR 和 git diff 同等重要
- 禁止模糊 then 字段（"验证成功"、"正常返回"等）
- 禁止 `br_mappings` 为空
