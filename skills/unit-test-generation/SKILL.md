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

**DQG 核心价值观：质量！质量！质量！**

> DQG 的测试不是为了"凑覆盖率"，也不是为了"验证业务语义 SE"这种有限目标——测试是为了保证软件质量，防止线上 bug，让代码可信赖。REQ+BR+SE 是质量的需求来源，代码路径（Happy/Exception/Boundary/并发幂等）是质量的验证维度，两者叉积才是完整的质量证据。

IRON LAW: 不写 assertTrue(true) 占位符。写不了的测试标记 TODO 并说明原因，不要用占位符假装覆盖。

---

## EUT 矩阵设计核心原则（不可违反）

**两个维度必须同时满足：**

**维度 A（覆盖源）：需求维度 + 代码维度，缺一不可**

需求维度（Q01 产物）：
- 每条 REQ 必须有对应 EUT（`bound_item = "REQ-XXX"`）
- 每条 BR 必须有对应 EUT（`bound_item = "BR-XXX"`）
- 每条 SE 必须有对应 EUT（`bound_item = "SE-XXX"`）——SE 是 REQ/BR 的语义补充

代码维度（git diff 变更事实）：
- feature branch 相对 master 新增/修改的每个 Java 类，必须在某条 EUT 的 `when` 字段里出现
- git diff 中未被 REQ/BR/SE 引用的变更方法，也必须有 EUT——代码改了就必须证明它是对的
- gate 检查：`_check_q05_git_diff_coverage` 自动扫描 code_repo 的 `git diff origin/master...HEAD`

**维度 B（代码路径）：从实现代码视角分解执行路径**
> **重要：Happy / Exception / Boundary 是代码实现视角的路径分类，不是需求分类。**
> 对同一条 REQ/BR/SE，要分析其实现代码，识别出哪些是正常执行路径（Happy）、哪些是异常处理路径（Exception）、哪些是边界条件（Boundary），每种路径都要有对应 EUT。

| 路径类型 | 含义 | 来源 | 要求 |
|---------|------|------|------|
| Happy Path | 代码主成功路径（正常输入→正确输出）| 代码 if 主干、正常 return | 每条 REQ/BR/SE ≥1 个，全局 ≥80% |
| Exception | 代码异常/错误分支（catch、if-else 的拒绝路径）| throw/catch、条件拒绝、降级 | 每条 REQ/BR/SE 100% 覆盖 |
| Boundary | 代码边界条件（null/空/最大值/最小值）| null 检查、空集合、数值上下限 | 有边界语义的条目 100% |
| Concurrent | 并发/幂等/多线程竞态（CountDownLatch 多线程验证）| 幂等键、锁、check-then-act | 有并发/幂等语义时 100% |

**叉积示例（SE-001 品类短路）：**
```
SE-001 × Happy Path  → EUT-002: 品类在白名单+商品允许 → assertEquals(true, result)
SE-001 × Exception   → EUT-001: 品类不在白名单 → assertEquals(false, result); verify(fulfillment, never())
SE-001 × Boundary    → EUT-021: 批量商品含黑名单 → assertEquals(false, result)
```

**错误示范（SE 视角≠REQ/BR 视角）：**
```
✗ 只写 SE-001 到 SE-011 的 EUT，BR-001 到 BR-024 无任何测试
✗ "品类白名单配置"(BR-001) 的配置操作逻辑完全没有测试
✗ "1仓/7仓不支持"(BR-006) 的代码分支没有 Exception EUT
```

---

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

## 三步生成范式（T6 — 强制，防 no-exception-test）

在 **Step 1 设计矩阵** 与 **Step 2/3 写代码** 之间，必须完成 **分支 → 后果 → EUT** 三步；细节与 JSON 模板见 [references/q05-three-step-paradigm.md](references/q05-three-step-paradigm.md)。

| 步骤 | 产物路径 | 要点 |
|------|-----------|------|
| **A 分支清单** | `_internal/_q05_branch_inventory.json` | 列出 happy / boundary / **exception** / concurrency；含异常类分支时后续必须有 Exception EUT |
| **B 业务后果** | `_internal/_q05_business_outcomes.json` | 每条分支 `outcome_id` + 可验证 `expected`（返回值/状态/异常类型） |
| **C 写 EUT** | `phase_b_structured.json` 的 `eut_items` | `then` 必须能关联回 **B** 的 `outcome_id`；异常用 `route_type: "Exception"` |

> Guardrail `q05_branch_coverage`：若 Step A 登记了异常类分支，但 `eut_items` 中无任何 `Exception` 路由，则 finalize **BLOCKED**。

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

**0.5e: 必须输出 `_internal/_q05_target_modules.json`（finalize BLOCKED gate）**

Step 0.5 完成后，必须将三层驱动的结果写入此文件，否则 finalize 直接 BLOCKED：

```json
{
  "target_repos": ["maf-srv-service"],
  "git_diff_files": ["maf-srv-service/src/main/java/com/mi/maf/srv/manager/srv/LogisticExchangeIdentifyManager.java"],
  "se_mappings": [
    {"se_id": "SE-001", "impl_class": "LogisticExchangeIdentifyManager", "impl_method": "identifyByPrecheckAndFulfillment", "repo": "maf-srv-service", "found": true, "gap_reason": null},
    {"se_id": "SE-005", "impl_class": null, "impl_method": null, "repo": null, "found": false, "gap_reason": "实现类在前端，后端无对应逻辑"}
  ],
  "br_mappings": [
    {"br_id": "BR-001", "impl_class": "LogisticExchangeIdentifyManager", "repo": "maf-srv-service", "found": true, "gap_reason": null}
  ]
}
```

规则：
- `se_mappings` 必须覆盖 Q01 的所有 SE（未找到的填 `found: false` + `gap_reason`）
- `git_diff_files` 必须非空（证明执行了 `git diff`，不能是 LLM 凭记忆填写）
- `found: false` 的条目必须填写 `gap_reason`，说明为何无法找到对应实现

### Step 1: 单测设计（先算清楚需要什么，再写代码）

**在写任何测试代码之前，必须先完成单测设计矩阵（`_test_design_matrix.json`）。这是 finalize 的硬性 gate——没有设计矩阵不能 finalize。**

**1.1 需求→用例设计（无代码也能做）**

逐条 REQ/BR/SE 设计测试用例（REQ/BR 是主体，SE 是补充验证）：

| bound_item | 用例 ID | 用例描述 | 路径类型 | 被测类.方法 | 仓库 |
|-----------|---------|---------|---------|-----------|------|

规则：
- **REQ/BR 是测试设计的主体，SE 是补充验证**——先覆盖每条 REQ 和 BR，再用 SE 验证语义精度
- 每条 REQ 必须有 ≥1 个 Happy Path EUT（`bound_item = "REQ-XXX"`）
- 每条 BR 必须有 ≥1 个 Happy Path EUT + ≥1 个 Exception EUT（`bound_item = "BR-XXX"`）
- 涉及金额/状态/枚举/边界的 BR，必须有 Boundary EUT
- SE 对应的 EUT 是对 REQ/BR EUT 的语义精度补充，不能用 SE EUT 替代 BR EUT
- 未覆盖的 REQ/BR 必须标注原因（前端逻辑/BPM 配置/不在代码范围）
- **每条用例必须标注归属仓库名**
- **每条 REQ/BR/SE MUST 有直接 EUT，`bound_item` 必填，不允许留空，禁止仅靠"间接覆盖"**：直接 EUT 指测试方法直接调用被测条目对应的方法并断言其业务结果；间接覆盖在 Q06 审计时降级为 `PARTIAL`
- **通用方法测试 MUST NOT 替代特定 BR 测试**：每条 BR 必须在 `eut_items` 中找到至少一行 `bound_item = "BR-XXX"` 的记录
- **分层职责边界：集成测试范围内的 domain 层 MUST 仍有单测**：即使外层用集成测试（如 Spec/Step 层）覆盖了端到端流程，domain 层的状态变更、领域规则、聚合根不变式 MUST 有独立的 domain 层单测；禁止用"反正集成测试会覆盖"跳过 domain 层（Q06 cases #3/#4/#7 的反模式）
- **状态机每条迁移路径 MUST 有直接 EUT**：`状态 A → 状态 B` 的每条迁移边，必须有一个 EUT 直接断言 `targetState == B`；仅靠"间接被触发"不算覆盖（例：主状态机的 `WAIT_APPROVE → REJECTED` MUST 有 EUT 显式 `assertEquals(REJECTED, actual.getState())`，不能依赖其它 EUT 测试回退路径时顺带验证）

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

**1.4 设计矩阵自检（硬性 gate — 必须对齐 Phase Q06 审计标准）**

| 指标 | 要求 | 不达标则 |
|------|------|---------|
| REQ 覆盖率 | 100%（每条 REQ 至少 1 个用例） | BLOCKED |
| 后端 BR 覆盖率 | 100%（排除前端 BR 后，后端可测 BR 全覆盖） | BLOCKED |
| SE 覆盖率 | 100%（有效 SE） | BLOCKED |
| Happy Path | ≥ 80% 方法（逐个公开方法检查是否有正常链路用例） | BLOCKED |
| Exception | 100%（逐个 throw/catch 必须有对应用例） | BLOCKED |
| Boundary | 100%（逐个边界条件：0/null/MAX/时间临界/空集合 vs null） | BLOCKED |
| Defense | 100%（逐个 if null return/if blank skip 必须有对应用例） | BLOCKED |
| 状态机 | 100% 转移边（含反向/非法跳转） | BLOCKED |
| 并发场景 | check-then-act 竞态窗口必须有用例 | BLOCKED |

> 并发测试必须使用 CountDownLatch 模式验证竞态窗口，具体模板见 `references/test-generation-rules.md`。仅 `assertThrows` 验证重复提交不算并发测试，必须多线程同时触发。触发条件（满足任一即触发）：
> - SE 描述包含"幂等"、"重复提交"、"并发"、"同时操作"、"锁"关键词
> - 代码中存在 check-then-act 模式：`synchronized`、`@Transactional` + 状态检查、分布式锁（`RedissonClient`/`@DistributedLock`）、`SELECT ... FOR UPDATE`
> - 即使 Q01 未识别并发 SE，读代码时发现上述模式也必须生成并发测试
| 变更文件覆盖率 | P0 100% / P1 ≥ 80% | WARNING |
| 代码分支覆盖率 | **100%**（有矩阵读矩阵，无矩阵用分支清单+EUT类型推断） | FAIL |

> **设计矩阵是 Phase Q06 审计的基准**——Phase Q06 对照设计矩阵检查"设计了但没实现"和"实现了但没设计"。

### Step 2: 架构上下文（DDD+TMF）代码脚手架生成

严格遵照分层职责界限生成单测结构。详细分层测试要求、Mock 策略、DAMP 原则见 [references/test-generation-rules.md](references/test-generation-rules.md)。

### Step 3: 单测强断言约束代码实现

**产出位置：直接写到业务仓库的 `src/test/java` 对应包目录下，不生成 patch 文件。**

每个测试类放在被测类同一 Maven 模块的 `src/test/java` 下，包路径与被测类一致。例如：
- 被测类: `car-mrs-domain/src/main/java/com/xiaomi/.../service/MrOrderMainService.java`
- 测试类: `car-mrs-domain/src/test/java/com/xiaomi/.../service/MrOrderMainServiceTest.java`

**3.1 写行为断言**：`assertEquals` 校验关键业务字段（金额、状态、ID、时间戳）。金额类断言必须精确到分。

**3.2 副作用验证**：`Mockito.verify(client, times(1)).doAction(...)` 验证外部调用。不应该被调用的方法用 `verify(mock, never())` 验证。

**3.3 精确异常拦截**：`assertThrows(SpecificException.class, () -> ...)` 捕获具体异常类型。异常后必须补充业务效果断言（状态未变更、数据未写入、事务已回滚）。禁止 `try{...}catch(Exception e){}` 静默吞异常。

**3.4 追溯性标注**：每个 `@Test` 方法必须在注释或 `@DisplayName` 中标注关联的 SE/EUT ID。格式：`// 对应: SE-014 当越权访问时拦截` 或 `@Tag("EUT-003")`。

### Step 3.5: 多仓库完整性自检（BLOCKED gate）

**在进入 Step 4 之前，必须通过此检查。**

对照 Step 0.5d 的合并目标模块列表，逐仓库核对：

| 仓库 | 设计 TC 数 | 已写入测试类数 | 缺失 |
|------|-----------|-------------|------|

规则：
- 每个有 MISSING TC 的仓库，必须有对应的测试文件写入 `src/test/java`
- 如果某仓库的 TC 全部 COVERED（已有测试），可以没有新增文件，但必须在表格中标注"全部已覆盖"
- **任何仓库有 MISSING TC 但无新增测试文件 → BLOCKED，不能进入 Step 4**
- 禁止默默跳过某个仓库的测试生成

### Step 4: 自检（提交前强制检查）

- [ ] EUT 矩阵覆盖了所有 REQ/BR/SE
- [ ] 单测代码使用强断言（非仅执行流程）
- [ ] 异常路径有对应测试
- [ ] 每个测试用例标注了关联的 REQ/BR/SE ID
- [ ] **每条 TC 的 se_refs 非空（至少绑定一个 SE）**
- [ ] **每个仓库的新增测试文件已写入 `src/test/java` 对应包目录**
- [ ] **`mvn test-compile` 编译通过（每个仓库）**
- [ ] **`mvn test -Dtest=<新增测试类>` 运行无错误（每个仓库）**
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号
- [ ] **COVERED 的 TC 已填写 `test_location`（`line_start` 指向断言行，非方法第一行）**

### Step 5: Judge/Critique（提交前自我评审）

- **Judge**：对照 Phase Q01 产物验证 EUT 矩阵覆盖完整性，按 4 维度打分（EUT 覆盖/断言强度/可编译性/SE 追溯）
- **Critique**：假设有遗漏，重点检查异常路径、边界值、并发场景的测试覆盖
- 记录在报告末尾「自我评审记录」章节

### Step 6: 修正

根据 Step 4 自检和 Step 5 Judge/Critique 发现的问题，逐项修正后重新通过自检清单。

## 产物

- EUT 矩阵（`eut_matrix.md`）
- 结构化产物（`phase_b_structured.json`）— 格式见下方
- 单测代码（直接写入业务仓库 `src/test/java` 对应包目录，基于 `templates/DomainStepTest.java.tmpl` 和 `templates/DomainAbilityTest.java.tmpl`）
- 建议以 `../../references/eut-matrix-template.md` 作为 EUT 报告骨架，并在报告头保留 `PROFILE_CONTEXT`

### `phase_b_structured.json` 格式（必须严格遵守）

**主字段：`eut_items`（EUT 设计矩阵，必填）**

```json
{
  "project_id": "项目ID",
  "eut_items": [
    {
      "eut_id": "EUT-001",
      "bound_se": "SE-002",
      "se_refs": ["SE-002", "SE-003"],
      "route_type": "Happy Path",
      "given": "同一 workOrderId，无已有审批中申请，授权店，工单状态=待申请结算",
      "when": "调用 applyEarlyDeliveryAuthStore(stNo, applyReason, mid)",
      "then": "返回非空 processInstanceId；verify(subProcessGateway).insert(any()) 调用 1 次；verify(mrApprovalLogGateway).insert(any()) 调用 1 次",
      "risk_tier": "T1",
      "repo": "car-mrs"
    },
    {
      "eut_id": "EUT-002",
      "bound_se": "SE-002",
      "se_refs": ["SE-002"],
      "route_type": "Exception",
      "given": "同一 workOrderId，DB 中已有 status=IN_REVIEW 的提前交车申请",
      "when": "调用 applyEarlyDeliveryAuthStore(stNo, applyReason, mid)",
      "then": "assertThrows(BusinessException.class, ...)；exception.getMessage() 含 '请勿重复提交'",
      "risk_tier": "T1",
      "repo": "car-mrs"
    }
  ],
  "test_cases": []
}
```

**字段约束（严格遵守，否则 Schema 校验 BLOCKED）：**
- `eut_id`：格式 `EUT-\d+`
- `bound_se`：**单个字符串**，主绑定 SE ID（如 `"SE-002"`），**不是 list**
- `se_refs`：list，关联的所有 SE ID（可包含多个）
- `route_type`：枚举 `Happy Path` / `Exception` / `Boundary` / `Concurrency`
- `given`：前置条件（系统状态、Mock 设置）
- `when`：触发动作（调用哪个方法，传什么参数）
- `then`：**必须包含具体断言**（assertEquals/assertThrows/verify 等），禁止模糊描述如"验证成功"
- `risk_tier`：`T1`（核心路径）或 `T2`（普通路径）
- `repo`：归属仓库名（多仓库场景必填）

**兼容字段：`test_cases`（已有单测映射，可选）**

```json
{
  "project_id": "项目ID",
  "eut_items": [...],
  "test_cases": [
    {
      "id": "TC-001",
      "repo": "car-mrs",
      "status": "COVERED",
      "covered_by": "MrOrderMainServiceTest#testApplyEarlyDelivery_success",
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
- `production_location`: 填写被测方法的实现起始行

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

> 注：所有 BLOCKED/FAIL 项均为自动 gate，finalize 阶段强制执行，已无"人工确认"项。

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 编译通过 | test_execution_gate: 对每个仓库 `mvn test-compile` | BLOCKED |
| 测试运行通过 | test_execution_gate: 对每个仓库 `mvn test -Dtest=<新增类>` | BLOCKED |
| 多仓库完整性 | test_execution_gate: 每个 code_repo 都必须有新增测试文件 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json` | REGRESSION |
| Schema 校验 | schemas/phase_b.py 验证 `phase_b_structured.json` | BLOCKED |
| Exception 后置断言 | phase_q05 schema: Exception EUT then 必须有 assertThrows + 状态/副作用验证 | BLOCKED |
| EUT 覆盖 SE | R-SE-BOUND: 每条 SE 逐条验证有对应 bound_se EUT（100%） | FAIL |
| 路径覆盖率 | R-HAPPY-EXCEPTION: SE+BR+REQ+代码四维度（Happy≥80%/Exception=100%/Boundary=100%） | FAIL |
| EUT 数量 | R-EUT-COUNT: ≥ Q01 的 REQ+BR+SE 总数（动态，无上限） | FAIL |
| BR 覆盖率 | R-BR-COVERAGE: 100%（通过 SE 链路验证） | FAIL |
| 代码分支覆盖率 | R-CODE-BRANCH: **100%**（有矩阵读矩阵，无矩阵读分支清单） | FAIL |
| 设计矩阵存在 | R-DESIGN-MATRIX: `_test_design_matrix.json` 必须存在 | FAIL |
| 设计矩阵一致性 | R-MATRIX-CONSISTENCY: summary 数字不能虚报（与数组实际内容交叉验证） | FAIL |
| T1 SE 三路径 | R-T1-THREE-PATHS: T1 SE 必须有 Happy+Exception+Boundary 各≥1 EUT | FAIL |
| 不应调用 never | R-NEVER-VERIFY: 含"不应调用"语义的 SE 对应 EUT 必须有 verify(never()) | FAIL |
| 方法级断言强度 | q05_structure_checks: >40% @Test 仅有弱断言 → BLOCKED | BLOCKED |
| 追溯标注 | q05_structure_checks: <60% @Test 方法有 SE/EUT 注释 → WARNING | WARNING |
| 并发测试多线程 | q05_structure_checks: Concurrency EUT 必须有 CountDownLatch/Thread | BLOCKED |
| 分支清单存在 | Q05BranchCoverageGuardrail: 无 Step A 清单 → WARNING | WARNING |
| 设计矩阵 branch 真实性 | q05_structure_checks: branch 文件名必须在 git diff 变更文件里 | WARNING |
| Step 0.5 三层驱动产物 | q05_structure_checks: _internal/_q05_target_modules.json 必须存在且覆盖全部 SE | BLOCKED |
| uncovered BR 理由合理性 | q05_structure_checks: 标注前端原因但描述含后端语义 → WARNING | WARNING |

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
