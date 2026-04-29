---
name: unit-test-audit
description: "Phase Q06: 需求驱动的单测覆盖审计，验证测试与需求真实匹配，而非仅追求覆盖率数字。当用户要求审计单测覆盖质量，或 Phase Q05 完成后进入时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q06
  depends_on: [Q01, Q05]
  outputs: [phase_c_structured.json, phase_c_report.md, _reasoning_log.md]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q06: 单测覆盖审计

IRON LAW: 测试通过 ≠ 测对了。每个 COVERED 判定必须验证期望值来源（来自需求还是猜测），无法确认来源的判定降级为 PARTIAL。

IRON LAW: 每条 audit_item 的 evidence 字段必须引用具体代码位置（格式：`[文件名:行号]`），空 evidence 的 COVERED 判定会被 finalize gate 降级为 PARTIAL。报告中每条结论行必须有 `[来源: 文件名:行号]` 标注。

验证单测是否真正测对了业务场景，而非仅追求覆盖率数字。

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
4. 若存在 `_internal/_weak_assert_context.md`，必须优先读取；它是基于 diff 测试文件生成的 weak assert 候选 sidecar，可作为 `WRONG_TARGET` 的优先复核清单。
5. weak assert sidecar 只是候选清单，不能直接照抄结论；必须回到测试代码逐条核实。

## 审计原则

1. 需求优先，代码次之：先还原需求，再映射代码与测试。
2. 覆盖率是门槛，不是结论：coverage 只能证明"测到"，不能证明"测对"。
3. 防止"代码导向自证"：不能只根据当前实现去设计并证明测试充分。
4. 审计范围 = 本次改动 + 相邻高风险影响面。
5. 分层职责必须可验证：测试要证明"代码在正确层做了正确事"。
6. 只做审计与建议：不自动改代码、不自动补测试。
7. 语义防漏：明确规则必须显式建模为 `SEM` 并可追踪到 `UT/EUT`。

## 覆盖状态枚举

| 状态 | 含义 |
|------|------|
| `COVERED` | 有测试，且验证业务结果 |
| `PARTIAL` | 有测试，但断言不充分或仅覆盖子路径 |
| `MISSING` | 无对应测试 |
| `WRONG_TARGET` | 有测试，但验证目标错误（过度 mock、仅验调用次数、仅非空断言） |
| `CONFLICT` | 有测试，断言模式与审计标准不一致，但可能是团队有意的设计决策，交人工裁决 |

## 执行流程

### Phase Q06 的定位（与 Phase Q05 的分工）

Phase Q05 保障质量下限（按规则写出合格单测），Phase Q06 保障质量上限（发现按规则写了仍然遗漏的深层问题）。

**Phase Q06 的核心目标不是"打分"，而是保证单测质量能防住线上 bug。** 审计报告必须回答四个问题：
1. **有没有？**（定性）— 每个方法/分支/边界是否有测试
2. **全不全？**（定量）— 覆盖率是否达到 Phase Q05 定义的 100% 标准
3. **好不好？**（质量）— 断言是否验证了正确的业务语义，Mock 是否贴近真实场景
4. **准不准？**（正确性）— 测试断言的期望值是否和需求/代码一致，测试本身是否正确

### 四层审计标准（递进关系，每层都必须通过）

**第一层：有没有（定性 — 存在性检查）**

逐条检查每个需求映射方法和 git diff 变更方法是否有对应测试。不能概括说"大概覆盖了"，必须逐条列出。

审计范围 = REQ/BR/SE 映射到的后端方法 ∪ git diff 变更的方法。未变更且未被需求映射的方法不在范围内。

**第二层：全不全（定量 — 与 Phase Q05 硬标准对齐）**

Phase Q06 必须按 Phase Q05 的硬标准逐条验证，不能降级：

| 指标 | Phase Q05 标准 | Phase Q06 审计方式 |
|------|-------------|-----------------|
| Happy Path | ≥80% 方法 | 逐个方法检查是否有正常链路测试，列出缺失方法 |
| Exception | 100% | 逐个 throw/catch 检查是否有对应测试，列出未覆盖的异常分支 |
| Boundary | 100% | 逐个边界条件检查（0/null/MAX/时间临界/空集合vs null），列出未覆盖的边界值 |
| Defense | 100% | 逐个 if null return/if blank skip 检查，列出未覆盖的防御判断 |
| 后端 BR | 100% | 排除前端 BR 后，逐条检查后端可测 BR 是否有测试 |
| SE 覆盖率 | 100% | 逐条 SE 列出覆盖状态、测试方法、验证逻辑 |
| 状态机 | 100% 转移边 | 逐条状态转移检查是否有测试（含反向/非法跳转） |
| 变更文件覆盖 | P0 100% / P1 ≥80% | 检查 git diff 变更的核心类是否全部有测试 |
| 并发场景 | 必须覆盖 | check-then-act 竞态窗口必须有测试验证 |

**第三层：好不好（质量 — 超越 Phase Q05 的深度检查）**

Phase Q05 保证"按规则写了"，Phase Q06 检查"写得好不好"：

| 检查项 | 审计方式 |
|--------|---------|
| 断言强度 | 逐个测试方法检查：仅弱断言(assertNotNull/assertDoesNotThrow 作为唯一断言)=WRONG_TARGET |
| 断言叠加 | 弱断言必须叠加强断言，不能替换。assertNotNull+assertEquals=合格，仅assertNotNull=不合格 |
| Mock 真实性 | Mock 数据是否贴近真实业务（金额用分不用元、状态码用枚举不用魔数、门店ID用真实格式） |
| SE 交互场景 | 单条 SE 都有测试，但 SE 之间的组合场景有没有测？ |
| 数据一致性 | 主表更新了但快照表/明细表没同步的场景 |
| Mock 偏差 | Mock 返回正确数据但真实 Gateway 可能超时/返回 null/字段缺失 |
| 假阳性 | 测试通过但没有验证关键逻辑（verify 了调用但没验证参数值） |
| 占位符测试 | assertTrue(true) 等占位符必须标记为 WRONG_TARGET |
| private 方法 | 有业务逻辑的 private 方法必须通过反射或 public 方法间接覆盖，不能跳过 |

**第四层：准不准（正确性 — Phase Q06 独有的深度审计）**

测试通过 ≠ 测对了。Phase Q06 必须验证测试本身的正确性：

| 检查项 | 审计方式 | 示例 |
|--------|---------|------|
| 期望值正确性 | 断言的 expected 值是否和需求/代码一致 | `assertEquals(2, careTypes.size())` 验证的是列表大小，不是互斥逻辑本身 |
| 验证目标正确性 | 测试验证的是业务语义还是实现细节 | verify(mock, times(1)) 只验证调用次数，不验证参数是否正确 |
| 变异杀伤力 | 如果代码逻辑改错了，这个测试能发现吗 | 金额 HALF_UP→HALF_DOWN，现有断言能否检测到 |
| 需求对齐 | 测试的场景是否和 PRD/BR 描述一致 | BR-010 说"免费维修/退车/换车三选一互斥"，测试是否覆盖了所有三选一组合 |
| 边界值准确性 | 边界值是否取自需求而非猜测 | 30天/60天/90天 是需求定义的，不是随意选的数字 |
| 状态码准确性 | 断言中的状态码是否和枚举定义一致 | AUDIT_CANCEL=10 不是 5，测试中的期望值是否正确 |
| 异常消息准确性 | assertThrows 后的 getMessage 验证是否匹配实际异常消息 | 代码抛"不支持"，测试验证 contains("不支持") 而非 contains("错误") |

审计报告必须列出：
- 期望值可疑列表（哪个测试、哪个断言、为什么可疑）
- 验证目标偏移列表（测试验证的不是业务语义）
- 变异逃逸风险列表（哪些变异无法被现有断言杀死）

执行前先读取 `output/<project>/Q06/_internal/_weak_assert_context.md`（如存在），把其中命中的测试方法作为 Step 2 / Step 5 / Step 7.5 的重点核验对象。

详细审计规则（架构识别基线、断言正确性规则、异常场景覆盖、变异测试、DDD/TMF 分层基线）见 [references/audit-rules.md](references/audit-rules.md)。

### Step 0: 基线、架构与范围确认

1. 识别当前分支与基线分支（本地优先，不依赖外部平台 API）。
2. 识别架构类型：`DDD / TMF / DDD+TMF`。
3. 输出改动清单、影响模块与涉及层（Client/Application/Domain/Infrastructure/Spec/Step/Ability）。
4. 标记审计边界：哪些需求点属于本次审计，哪些不属于。

### Step 1: 需求场景建模（先于代码）

针对每个需求点，建立场景矩阵，至少包含：
1. 主成功路径
2. 关键业务变体路径
3. 边界值路径
4. 非法输入路径
5. 外部依赖异常路径（超时、失败、空响应、脏数据）
6. 并发与幂等路径（重复请求、乱序、重试）
7. 事务一致性路径（部分失败、回滚、补偿）
8. 权限与数据隔离路径（角色、租户、越权）
9. 配置与开关路径（缺配置、错误配置、降级）

### Step 1.1: 关键语义（SEM）专项建模

1. 从需求文本与图片内容抽取所有"影响业务结果"的规则语义，编号 `SEM-xxx`。
2. 每个 `SEM` 必须绑定 `REQ/BR`，并在矩阵中可定位到 `CODE/UT/EUT`。
3. 对关键 `SEM` 至少检查两类用例：规则正确性 + 边界或稳定性。

### Step 2: 场景 → 代码 → 测试映射

执行本步骤前，先查看 `_weak_assert_context.md` 中命中的测试方法；对 sidecar 标记为 `ASSERT_NOT_NULL_ONLY`、`CONSTANT_BOOLEAN_ASSERT`、`VERIFY_ONLY_NO_BUSINESS_ASSERT`、`ASSERT_THROWS_NO_EFFECT_ASSERT` 的用例，优先回到源码核实是否应判为 `WRONG_TARGET` 或 `PARTIAL`。

对每个场景执行三段映射：
1. 场景对应代码点（类/方法/分支）
2. 场景对应测试用例（测试类/方法）
3. 断言质量检查：是否验证业务结果，而非仅验证实现细节

### Step 3: 分层职责一致性专项审计（DDD + TMF）

至少检查：
1. `Client` 是否仅承载契约，未混入业务分支
2. `Application/CmdExe` 是否只做编排转换，核心规则是否下沉 Domain
3. `Domain` 是否围绕聚合根与领域规则，且通过 Gateway 接口隔离外部依赖
4. `Infrastructure` 是否只承载技术实现与转换
5. `DomainStep` 是否通过 `TMF.findAbility()` 调能力，是否避免直接注入 Ability
6. `DomainAbility` 是否继承 `AbstractDomainAbility`，扩展点调用方式是否匹配业务

### Step 4: 异常分支专项审计（Java）

至少检查：参数校验异常、领域规则异常、持久层异常、第三方调用异常、事务语义、并发与幂等、时间与精度、配置容错、TMF 链路异常。

详细异常场景清单见 [references/audit-rules.md](references/audit-rules.md)。

### Step 5: 异常分支强制断言审计

若 `_weak_assert_context.md` 标出了 `ASSERT_THROWS_NO_EFFECT_ASSERT`，必须重点检查该异常用例是否只断言了异常对象/类型，而没有断言失败后的状态、数据、事务或外部副作用。

异常分支用例除了"执行到异常"，还必须检查：
1. 错误结果断言：异常类型、错误码、错误信息（至少其一可稳定断言）
2. 状态断言：失败后领域状态未被错误推进
3. 数据断言：数据库无脏写、无重复写、无部分提交
4. 事务断言：应回滚时必须回滚；需要补偿时有补偿结果
5. 外部调用断言：重试次数、降级路径、熔断/限流行为符合预期
6. 幂等断言：重复请求不产生额外副作用
7. TMF 断言：失败后链路中止正确、`rollback`/补偿行为正确

若异常分支仅断言"抛了异常"而无业务后果断言，标记为 `WRONG_TARGET`。

### Step 6: 覆盖率门禁与特殊规则检查

1. 校验增量行覆盖率、增量分支覆盖率是否均达到 `80%`
2. 校验核心领域异常分支是否达到 `100%`
3. 校验对外 API / 第三方格式依赖代码是否达到行+分支 `100%`
4. 校验是否有边界格式 mock 用例
5. 校验 TMF 关键编排节点是否覆盖正反路径

### Step 7: Mapper/Service 断言 checklist 审计

1. 必须使用模板：`templates/mapper_service_assertion_checklist.md`
2. 对本次改动涉及的 Mapper/Service/Step/Ability 填写 checklist
3. 未填写或关键项未勾选，标记 `MISSING_PROCESS` 并降级为 `FAIL` 候选

### Step 7.5: 变异测试（默认开启）

在 Step 6 覆盖率门禁全绿通过后自动触发。详细变异测试规则见 [references/mutation-testing.md](references/mutation-testing.md)。

**门禁规则：**
- 变异杀伤率（Mutation Score）门槛：T1 核心路径 >= 80%，T2 重要路径 >= 60%
- 存在 `MUTATION_SURVIVED_CRITICAL` 且未补强断言 → 判 `FAIL`

### Step 8: 审计结论与风险分级

按严重级输出：
1. `CRITICAL`：关键需求场景缺失，或异常漏测可能导致生产事故
2. `HIGH`：核心路径仅部分覆盖，存在明显漏测
3. `MEDIUM`：次要路径漏测或断言质量不足
4. `LOW`：可改进项，不构成当前发布阻断

### Step 9: 自检（提交前强制检查）

- [ ] 每个审计判定（COVERED/MISSING/WRONG_TARGET/CONFLICT）有代码证据
- [ ] T1 核心异常分支 100% 覆盖检查
- [ ] 弱断言（assertNotNull/assertTrue(true)等）已识别为 WRONG_TARGET
- [ ] 覆盖率门禁达标（line >= 80%, branch >= 80%）
- [ ] 每个发现标注了来源和置信度
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号

### Step 10: Judge/Critique（提交前自我评审）

- **Judge**：对照代码逐条验证审计判定准确性
- **Critique**：假设有遗漏，重点检查异常分支、并发场景、事务回滚测试
- 记录在报告末尾"自我评审记录"章节

### Step 11: 修正

根据 Judge/Critique 发现的问题，修正审计判定和报告内容，修正后重新执行自检清单，确保全部通过。

## 关键门禁

| 指标 | 阈值 |
|------|------|
| 增量行覆盖率 | >= 80% |
| 增量分支覆盖率 | >= 80% |
| T1 核心异常分支 | 100% 覆盖 |
| 变异杀伤率 T1 | >= 80% |
| 变异杀伤率 T2 | >= 60% |

## 结论枚举

`PASS` / `PASS_WITH_RISKS` / `FAIL`

**PASS 条件：**
- 无 `CRITICAL`
- `T1-核心` 场景与异常分支无 `MISSING/WRONG_TARGET`
- 增量行/分支覆盖率均满足 `>= 80%`
- 分层职责一致性检查无阻断项

## 报告结构

复用 `../../references/ut-audit-template.md`。报告头必须包含 `PROFILE_CONTEXT`（来自 `output/<project>/Q06/_profile_context.md`）。

报告输出模板见 [references/report-template.md](references/report-template.md)。

报告必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **审计范围** — 被审计的测试文件和被测类
3. **8 维度审计结果** — ①SE覆盖率/②路径覆盖/③断言强度/④Mock真实性/⑤状态机覆盖/⑥可维护性/⑦边界场景/⑧防御性测试
4. **逐条审计明细** — 表格（测试方法/判定/问题/建议）
5. **未覆盖的关键场景** — P0/P1 列表
6. **改进建议** — 按优先级排序
7. **评审结论** — PASS / PASS_WITH_RISKS / FAIL
8. **自我评审记录** — Judge + Critique

## phase_c_structured.json 产出格式（强制）

```json
{
  "project_id": "xxx",
  "audit_items": [
    {
      "id": "AUDIT-001",
      "se_id": "SE-001",
      "eut_id": "EUT-001,EUT-002",
      "description": "SE 描述",
      "status": "COVERED|PARTIAL|MISSING|WRONG_TARGET",
      "test_class": "XxxTest [来源: XxxTest.java:45]",
      "test_method": "method1, method2",
      "evidence": "assertEquals('expected', actual) [XxxTest.java:52]; verify(mock).call() [XxxTest.java:58]",
      "recommendation": ""
    }
  ],
  "findings": [...],
  "coverage_gate": {"line_coverage": 85.0, "branch_coverage": 72.0},
  "conclusion": "PASS_WITH_RISKS",
  "summary": {...}
}
```

**evidence 字段铁律：**
- COVERED 判定必须有 `[文件名:行号]` 格式的证据引用，至少 1 处
- 空 evidence 的 COVERED 会被 finalize gate 自动降级为 PARTIAL
- PARTIAL/MISSING 的 recommendation 必须具体到要补什么断言

## 通过标准

- 关键门禁全部达标
- 自检清单全部通过
- Judge/Critique 已执行且问题已修正
- 推理日志已输出

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "覆盖率达标了就行" | 覆盖率不等于断言质量，assertNotNull 也算覆盖 | 检查断言是否验证业务语义 |
| "这个 assertNotNull 是合理的" | 除非是纯存在性检查，否则必须有业务字段断言 | 标 WRONG_TARGET，建议补强断言 |
| "异常测试有 assertThrows 了" | 只校验抛异常不校验业务后果，Phase Q06 判 WRONG_TARGET | 检查是否有状态/数据/事务断言 |
| "这个模块不是核心路径" | T2/T3 也有最低覆盖要求，不能跳过 | 按风险分级给出覆盖要求 |
| "弱断言检测 sidecar 没标记" | sidecar 是辅助，最终结论以源码复核为准 | 即使 sidecar 未标记，源码有弱断言也要报 |
| "变异测试太重了" | 变异测试是终极验证，Step 7.5 默认开启 | 至少对 T1 核心路径做变异分析 |
| "测试通过了就是 COVERED" | 测试通过不等于测对了，期望值可能来自猜测 | 验证期望值来源（需求/代码/猜测） |
| "Mock 数据能跑通就行" | Mock 数据可能恰好掩盖 bug（如 key 不一致） | 构造 distributionId ≠ rightsBatchId 等不等场景 |
| "private 方法测不了" | 反射或间接调用都可以测 | ReflectionTestUtils.invokeMethod 或通过 public 方法触发 |
| "并发场景单测覆盖不了" | CountDownLatch + 多线程可以验证竞态窗口 | 至少验证 check-then-act 的竞态存在性 |
| "Mock 的方法名看着对" | LLM 常见幻觉：猜测方法名（如 isSuccess vs isOk），编译会失败 | 审计时验证 Mock 的方法签名在被测类中实际存在 |
| "测试文件在项目里就行" | 放错模块导致编译失败，找不到被测类依赖 | 检查单测 package 与被测类是否在同一 Maven 模块 |

## Question-Style 审计指令（用问题代替模糊指令）

审计每个测试方法时，逐条回答以下问题：

### 第一层：有没有
- 这个方法/分支/边界有对应的测试吗？

### 第二层：全不全
- 问自己：如果把这个方法的所有 if/else/switch/catch 列出来，每个分支都有测试吗？
- 问自己：如果把这个方法的入参设为 null/0/空字符串/MAX_VALUE，会怎样？有测试吗？

### 第三层：好不好
- 问自己：如果删掉这个测试的所有断言只留 assertNotNull，测试还能通过吗？如果能，说明断言太弱。
- 问自己：Mock 返回的数据和真实 Gateway 返回的数据一样吗？字段名、类型、null 可能性都一致吗？

### 第四层：准不准
- 问自己：这个 assertEquals 的 expected 值从哪来的？是需求定义的数字还是随便写的？
- 问自己：如果把被测代码的核心逻辑改错（如 HALF_UP→HALF_DOWN），这个测试能发现吗？
- 问自己：这个测试验证的是业务语义（"互斥规则生效"）还是实现细节（"调用了 1 次"）？

## Pre-Delivery Checklist（具体可验证）

### 正确性
- [ ] 每个 COVERED 判定有测试方法名 + 断言代码作为证据
- [ ] 每个 WRONG_TARGET 判定说明了"验证的是什么"和"应该验证什么"
- [ ] 每个 MISSING 判定说明了缺失的具体场景和风险级别
- [ ] 期望值可疑列表中每条都标注了来源（需求/代码/猜测）

### 完整性
- [ ] 11 个 SE 逐条列出覆盖状态（不能概括说"大概覆盖了"）
- [ ] 后端可测 BR 逐条检查（排除前端 BR 后 100%）
- [ ] git diff 变更的核心方法逐个检查
- [ ] 无效断言列表、未覆盖 Exception 列表、未覆盖 Boundary 列表、未覆盖防御场景列表全部输出

### 质量
- [ ] 无 "整体还行" "基本覆盖" 等模糊表述
- [ ] 每条发现有文件:行号 + 代码片段
- [ ] 变异测试至少对 T1 核心路径分析

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json` | REGRESSION |
| Schema 校验 | schemas/phase_c.py 验证 `phase_c_structured.json` | BLOCKED |
| 覆盖率门禁 | coverage_gate: JaCoCo XML line >= 80%, branch >= 80% | BLOCKED |
| T1 异常分支 | T1 核心异常无 MISSING/WRONG_TARGET | 人工确认 |
| 弱断言检测 | `_weak_assert_context.md` 中标记的方法已复核 | 人工确认 |

## 禁止事项

- 禁止在 Phase Q01/Q04/Q03 输出 UT/EUT
- 禁止自动 commit/push 代码
- 禁止编造不存在的接口、字段、逻辑
- 禁止跳过自检和 Judge/Critique 直接 finalize
- 禁止重跑时从零重写
- 禁止以覆盖率百分比替代场景覆盖结论
- 禁止仅凭代码推导需求并给出"覆盖完整"结论
- 禁止忽略图片中的规则语义（流程/状态/口径）并直接判定通过
