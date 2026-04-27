---
name: unit-test-generation
description: "Phase Q05: TDD 需求驱动单测设计与代码生成。用户明确进入单测环节，要求从需求生成测试大纲和单测代码时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q05
  depends_on: [Q01]
  outputs: [eut_matrix.md, phase_b_structured.json, _reasoning_log.md]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q05: 单测生成

IRON LAW: 不写 assertTrue(true) 占位符。写不了的测试标记 TODO 并说明原因，不要用占位符假装覆盖。

从 Phase Q01 的结构化需求驱动单测设计，而非从代码反推。

## 前置依赖

- Phase Q01 产出（REQ/BR/SE）

## 技术栈基线

按项目 profile 选择：
- `java-ddd-tmf` → `../../profiles/java-ddd-tmf/baseline.md`
- `go-service` → `references/go-service-baseline.md`

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase Q01 结构化产物是唯一的需求基线，不要回溯飞书原文。

## 核心指导思想

1. **以审带写**：生成的测试必须 100% 满足 Phase Q06 的单测覆盖审计基线（断言强度、异常覆盖、分层职责）。
2. **脱离伪覆盖**：禁止从代码 `if-else` 反推用例（代码可能已写错）。强制基于 `REQ/BR/SE` 生成 EUT。
3. **断言约束**：禁止"空气单测"。必须断言：状态变更、副作用交互次数（Mockito.verify）、数据库核心字段写入。
4. **Phase Q06 对齐**：生成的每个测试都要能通过 Phase Q06 的审计标准。

## 执行流程

### Step 0: 输入确认与上下文加载

1. 确认 Phase Q01 产物存在（`phase_a_structured.json`）。
2. 确认代码仓库路径——**支持多仓库**，逐个列出所有涉及的仓库路径。
3. 读取 `_upstream_context.md`（不回读原始 PRD）。
4. 读取 `_business_mutations.md`（如存在）。
5. 识别架构类型：`DDD / TMF / DDD+TMF`。
6. 输出改动清单、影响模块与涉及层。

> **多仓库规则**：如果需求涉及多个代码仓库（如主服务+客诉管理+网关），必须对每个仓库都执行 Step 0.5~Step 3，不能只取一个。

### Step 0.5: 目标模块确定（三层驱动，不可跳过）

目标模块由三个视角合并确定，缺一不可：

**0.5a: REQ/BR→类映射（需求功能视角）**

1. 逐条读取 Phase Q01 的 REQ 和 BR 列表
2. 对每条 REQ/BR，在代码仓库中搜索对应的实现类
3. 输出映射表：

| REQ/BR ID | 描述 | 仓库 | 实现类 | 实现方法 | 映射依据 |
|-----------|------|------|--------|---------|---------|

4. 未找到实现类的 REQ/BR 标记为 UNCOVERED + 原因

**0.5b: SE→类映射（业务规则视角）**

1. 逐条读取 Phase Q01 的 SE 列表
2. 对每条 SE，在代码仓库中搜索对应的校验/规则类
3. 未找到的 SE 标记为 GAP（不可静默跳过）
4. 不能盲信 Phase Q03 的结论——必须实际搜索代码验证

**0.5c: git diff→变更文件列表（代码变更视角）**

1. 对每个仓库执行 `git diff --name-only origin/master...HEAD`
2. 筛选本次修改的 .java 文件（排除 test/target/pom）
3. 按 DDD 分层标注优先级：
   - P0：domain 层 Service/Checker + api 层枚举/常量
   - P1：app 层 ProviderImpl/Convert
   - P2：infrastructure 层 GatewayImpl + app 层 Job

**0.5d: 合并三个列表，取并集**

| 来源 | 仓库 | 文件 | 关联 REQ/BR/SE | 测试类型 | 优先级 |
|------|------|------|---------------|---------|--------|

> 三层驱动的关系：REQ/BR 回答"哪些功能需要测试"，SE 回答"哪些业务规则需要验证"，git diff 回答"哪些代码被修改了"。只有三者合并才是完整的目标模块。

### Step 1: 单测设计（先算清楚需要什么，再写代码）

**在写任何测试代码之前，必须先完成单测设计矩阵（`_test_design_matrix.json`）。这是 finalize 的硬性 gate——没有设计矩阵不能 finalize。**

**1.1 需求→用例设计（无代码也能做）**

逐条 REQ/BR 设计测试用例：

| REQ/BR | 用例 ID | 用例描述 | 路径类型 | 绑定 SE | 被测类.方法 | 仓库 |
|--------|---------|---------|---------|---------|-----------|------|

规则：
- 每条 REQ 至少 1 个 Happy Path 用例
- 每条 BR 中包含"校验/限制/必须/不能"关键词的，必须有 Exception 用例
- 每条 SE 至少 1 个用例（Happy 或 Exception），**绑定 SE 列必填，不允许留空**
- 涉及金额/状态/枚举的 BR，必须有 Boundary 用例
- 未覆盖的 REQ/BR 必须标注原因（前端逻辑/BPM 配置/不在代码范围）
- **每条用例必须标注归属仓库名**

**1.2 代码→用例补充（有分支代码时）**

对 Step 0.5c 中每个变更文件，扫描代码中的分支逻辑，自动补充用例：

| 代码模式 | 必须生成的测试 | 示例 |
|---------|-------------|------|
| `if (xxx == null) { xxx = defaultValue }` | null 入参→验证默认值生效 | pageNum=null→默认1 |
| `try { ... } catch (XxxException e) { return fail/降级 }` | 依赖抛异常→验证降级返回值 | Service 抛异常→返回 code!=0 |
| `BeanUtils.copy / @Mapping / 手动 set` | 每个字段映射→验证转换正确 | DTO.amount = entity.amount/100 |
| `if (str.startsWith("ST"))` / `switch` / `if-else 链` | 每个分支条件→验证路由正确 | "ST001"→stNo, "1234"→phoneSubfix |
| `param.setPageNum(pageNum != null ? pageNum : 1)` | null/0/负数/超大值→验证边界 | pageNum=-1→不崩溃 |
| `list.stream().filter().collect()` | 空列表/null 元素→验证不崩溃 | 空列表→返回空结果 |
| `BigDecimal.divide(xxx, 2, HALF_UP)` | 精度边界→验证小数位正确 | 10050分→100.50元 |

规则：
- 每个变更文件的**每个公开方法**，至少 1 个 Happy Path + 1 个防御性测试
- 代码中的**每个 if/else/switch 分支**，每个分支至少 1 个用例
- 代码中的**每个 try/catch**，每个 catch 至少 1 个用例
- Convert 类的**每个字段映射**，至少 1 个用例验证映射正确性
- ProviderImpl 的**每个接口方法**，至少测 Happy + 异常降级 + null 入参

**1.3 设计矩阵产出（`_test_design_matrix.json`）**

Step 1.1 + 1.2 的结果必须输出为结构化 JSON：

```json
{
  "req_coverage": [
    {
      "req_id": "REQ-001",
      "br_list": ["BR-001", "BR-002", ...],
      "test_cases": [
        {"case_id": "TC-001", "br_id": "BR-001", "description": "...", "path_type": "Happy", "se_id": "SE-001", "target_class": "...", "target_method": "...", "repo": "car-mrs"}
      ],
      "uncovered_brs": ["BR-005"],
      "uncovered_reasons": ["前端逻辑"]
    }
  ],
  "code_branch_coverage": [
    {
      "file": "RightsDistributionProviderImpl.java",
      "method": "findRightsDistributionList",
      "branches": [
        {"condition": "pageNum == null", "test_case": "TC-015", "covered": true},
        {"condition": "service throws", "test_case": "TC-016", "covered": true}
      ]
    }
  ],
  "summary": {
    "total_req": 10, "covered_req": 10,
    "total_br": 42, "covered_br": 38, "uncovered_br_reasons": "...",
    "total_se": 8, "covered_se": 8,
    "total_branches": 50, "covered_branches": 45,
    "total_test_cases": 120
  }
}
```

**1.4 设计矩阵自检（硬性 gate）**

| 指标 | 要求 | 不达标则 |
|------|------|---------|
| REQ 覆盖率 | 100%（每条 REQ 至少 1 个用例） | BLOCKED |
| BR 覆盖率 | ≥ 80%（含校验/限制的 BR 100%） | BLOCKED |
| SE 覆盖率 | 100%（有效 SE） | BLOCKED |
| 变更文件覆盖率 | P0 100% / P1 ≥ 80% | WARNING |
| 代码分支覆盖率 | ≥ 70% | WARNING |
| 路径均衡 | Happy ≥ 40% / Exception ≥ 30% / Boundary+防御 ≥ 30% | WARNING |

> **设计矩阵是 Phase Q06 审计的基准**——Phase Q06 对照设计矩阵检查"设计了但没实现"和"实现了但没设计"。

### Step 2: 架构上下文（DDD+TMF）代码脚手架生成

严格遵照分层职责界限生成单测结构。详细分层测试要求、Mock 策略、DAMP 原则见 [references/test-generation-rules.md](references/test-generation-rules.md)。

### Step 3: 单测强断言约束代码实现

**3.1 写行为断言**：`assertEquals` 校验关键业务字段（金额、状态、ID、时间戳）。金额类断言必须精确到分。

**3.2 副作用验证**：`Mockito.verify(client, times(1)).doAction(...)` 验证外部调用。不应该被调用的方法用 `verify(mock, never())` 验证。

**3.3 精确异常拦截**：`assertThrows(SpecificException.class, () -> ...)` 捕获具体异常类型。异常后必须补充业务效果断言（状态未变更、数据未写入、事务已回滚）。禁止 `try{...}catch(Exception e){}` 静默吞异常。

**3.4 追溯性标注**：每个 `@Test` 方法必须在注释或 `@DisplayName` 中标注关联的 SE/EUT ID。格式：`// 对应: SE-014 当越权访问时拦截` 或 `@Tag("EUT-003")`。

### Step 3.5: 多仓库完整性自检（BLOCKED gate）

**在进入 Step 4 之前，必须通过此检查。**

对照 Step 0.5d 的合并目标模块列表，逐仓库核对：

| 仓库 | 设计 TC 数 | 生成 patch 数 | 缺失 |
|------|-----------|-------------|------|

规则：
- 每个有 MISSING TC 的仓库，必须有对应的 `supplemental_tests/` patch 文件
- 如果某仓库的 TC 全部 COVERED（已有测试），可以没有 patch，但必须在表格中标注"全部已覆盖"
- **任何仓库有 MISSING TC 但无 patch → BLOCKED，不能进入 Step 4**
- 禁止默默跳过某个仓库的测试生成

### Step 4: 自检（提交前强制检查）

- [ ] EUT 矩阵覆盖了所有 REQ/BR/SE
- [ ] 单测代码使用强断言（非仅执行流程）
- [ ] 异常路径有对应测试
- [ ] 每个测试用例标注了关联的 REQ/BR/SE ID
- [ ] **每条 TC 的 se_refs 非空（至少绑定一个 SE）**
- [ ] **每个有 MISSING TC 的仓库都有对应的 supplemental_tests patch**
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出

### Step 5: Judge/Critique（提交前自我评审）

- **Judge**：对照 Phase Q01 产物验证 EUT 矩阵覆盖完整性，按 4 维度打分（EUT 覆盖/断言强度/可编译性/SE 追溯）
- **Critique**：假设有遗漏，重点检查异常路径、边界值、并发场景的测试覆盖
- 记录在报告末尾「自我评审记录」章节

### Step 6: 修正

根据 Step 4 自检和 Step 5 Judge/Critique 发现的问题，逐项修正后重新通过自检清单。

## 产物

- EUT 矩阵（`eut_matrix.md`）
- 结构化产物（`phase_b_structured.json`）— 格式见下方
- 单测代码（基于 `templates/DomainStepTest.java.tmpl` 和 `templates/DomainAbilityTest.java.tmpl`）
- 建议以 `../../references/eut-matrix-template.md` 作为 EUT 报告骨架，并在报告头保留 `PROFILE_CONTEXT`

### `phase_b_structured.json` 格式（必须严格遵守）

```json
{
  "project_id": "项目ID",
  "test_cases": [
    {
      "id": "TC-001",
      "repo": "car-mrs",
      "status": "COVERED",
      "covered_by": "SomeTest#testMethod",
      "scenario": "测试场景描述",
      "se_refs": ["SE-001"],
      "method": "applyEarlyDelivery",
      "class_under_test": "MrOrderMainService",
      "requirement": "BR-001",
      "priority": "P0"
    }
  ]
}
```

**字段约束：**
- `id`: 必填，格式 `TC-xxx`
- `repo`: 必填，归属仓库名
- `se_refs`: 必填，至少包含一个 SE ID
- `status`: COVERED / MISSING / PARTIAL
- `covered_by`: COVERED 时必填，格式 `TestClass#testMethod`

产物必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **SE→被测类映射表** — 表格（SE ID/描述/被测类/被测方法/映射依据）
3. **变更文件覆盖表** — 表格（文件/DDD层/测试类型/优先级/是否覆盖）
4. **EUT 矩阵** — 表格（EUT ID/被测类/方法/路径类型/绑定SE/描述/风险等级）
5. **测试文件清单** — 文件路径 + 测试数量
6. **自检清单** — SE 覆盖率/变更文件覆盖率/路径均衡/断言强度
7. **统计** — 总 EUT / Happy / Exception / Boundary / SE 覆盖数 / 变更文件覆盖数

## 通过标准

- EUT 矩阵完整覆盖 Phase Q01 产出的所有 REQ/BR/SE
- 单测代码编译通过、断言有效
- 自检清单全部通过
- Judge/Critique 已执行且问题已修正
- 推理日志已输出

## Anti-Rationalization（禁止偷懒）

### 生成前强制检查（Simplicity First + Think Before Coding）

每个测试方法写之前必须回答三个问题，回答不了就不写：
1. **这个测试验证的是什么业务场景？** — 不能回答"验证方法能调用"
2. **这是最简单的验证方式吗？** — 能用 assertEquals 就不用 verify+assertNotNull 组合
3. **每个断言都能追溯到需求吗？** — 不能追溯的断言就是多余的

### 生成范围强制检查（Think Before Coding）

代码生成前必须列出以下假设并等用户确认：
1. 目标仓库列表（三层驱动合并后的完整列表）
2. 每个仓库要生成的测试文件清单
3. 排除的方法/类及排除原因

**禁止默默假设某个仓库"不需要测试"。**

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "这个方法太简单不需要测试" | 简单方法也有边界和异常，Phase Q06 会审 | 至少一个 Happy Path EUT |
| "异常测试后面再补" | Phase Q06 会判 FAIL，缺异常测试不可能通过审计 | 每个核心方法至少 1 个 Exception EUT |
| "assertNotNull 够了" | Phase Q06 会标 WRONG_TARGET，不算有效覆盖 | assertEquals 验证业务字段 |
| "Mock 返回 null/空对象就行" | 掩盖真实调用时的字段缺失，测试通过但实际 NPE | Mock 返回值必须符合接口契约 |
| "编译问题后面修" | compile_check gate 会 BLOCKED，不修过不了 finalize | 生成后立即自检 import 和类型 |
| "这个方法应该有 isSuccess" | LLM 常见幻觉：猜测方法名而非读取实际 API | Mock 前必须确认方法存在（grep/AST），禁止基于常见模式猜测 |
| "测试文件放这个模块就行" | 目录放错导致编译失败，找不到被测类依赖 | 单测文件必须放在被测类同一 Maven 模块的 src/test/java 下 |
| "EUT 覆盖主要的就行" | 必须逐条对照 SE 列表，遗漏即扣分 | 每条 SE 至少一个 EUT |
| "A.6 说 handler 缺失所以不测" | A.6 结论可能过时，必须搜索代码验证实际存在的类 | 先 grep 代码，找到就测 |
| "这个 SE 的被测类不在目标模块里" | 目标模块由 SE 驱动，不由人指定 | 扩展目标模块覆盖所有 SE 映射到的类 |
| "已知 bug 不需要测" | 已知 bug 更需要防御测试（预期 FAIL），防止回归 | 生成防御测试验证 bug 存在 |
| "这个文件改动很小不需要测" | git diff 中的每个文件都可能引入 bug，改动大小不等于风险大小 | 本次修改的文件都要有测试 |
| "Convert/Provider 层只是透传不需要测" | 透传也可能映射错字段、丢参数、NPE，研发测试证明这些场景真实存在 | 每层至少有防御性测试 |
| "infrastructure 层是数据访问不需要单测" | Gateway 的查询条件、分页参数、排序逻辑都可能出错 | P2 优先级但不能完全跳过 |
| "先写个 assertTrue(true) 占位" | 占位符测试 = 零覆盖，Phase Q06 会标 WRONG_TARGET | 写不了就不写，标记为 TODO 并说明原因 |
| "这个方法依赖太多 Mock 不了" | 依赖多不是跳过的理由，可以用反射测 private 或间接测 | 至少测核心分支，标记集成测试范围 |
| "SE 覆盖 100% 就完成了" | SE 只是业务规则，git diff 变更的方法也必须覆盖 | 范围 = REQ/BR/SE 映射 ∪ git diff 变更 |

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 编译通过 | compile_check: `mvn compile` / `gradle compileJava` / `go build` | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json` | REGRESSION |
| Schema 校验 | schemas/phase_b.py 验证 `phase_b_structured.json` | BLOCKED |
| EUT 覆盖 SE | 每条 SE 至少有一个 bound_se 匹配的 EUT | 人工确认 |
| 路径类型均衡 | Happy/Exception/Boundary 三种类型都有 | 人工确认 |

## 关键约束

- 测试从需求生成，不从代码反推
- 强断言：状态变更、副作用（Mockito.verify）、数据库写入
- 禁止"仅执行流程"的弱断言
- 每个 EUT 必须绑定 SE/REQ/BR

## 禁止事项

- 禁止跳过自检和 Judge/Critique 直接 finalize
- 禁止重跑时从零重写
- 禁止从代码 `if-else` 反推用例（代码可能已写错）
- 禁止生成"空气单测"（只有执行流无断言）
- 禁止在 Phase Q05 输出审计结论（审计是 Phase Q06 的职责）
