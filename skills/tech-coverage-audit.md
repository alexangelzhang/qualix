---
name: tech-coverage-audit
description: "Phase A.5: 审计技术方案对 Phase A 结构化需求的覆盖度，确保不漏不偏"
trigger: "用户提供技术方案文档，且已有 Phase A 产出，要求做覆盖度审计"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase A.5: 技术方案覆盖度审计

承接 Phase A 产物，逐条比对技术方案覆盖度。禁止输出 UT/EUT。

## 核心原则

1. 逐条比对，不漏不猜。
2. 双向审计：需求→技术方案 + 技术方案→需求。
3. 区分前后端覆盖状态。
4. 未显式提及不得标 COVERED，可标 IMPLICIT 但须附推导依据。

## 覆盖状态枚举

| 状态 | 含义 |
|------|------|
| `COVERED` | 技术方案有明确对应设计 |
| `PARTIAL` | 部分覆盖，存在缺失维度 |
| `MISSING` | 无对应设计 |
| `IMPLICIT` | 未显式提及但可推导（须附依据） |

## 执行流程

**严格按顺序执行，不得跳步：**

```
Step 0: 输入准备与范围确认（如果是重跑，必须先读取旧版产物）
Step 0.5: [可选] 技术方案生成（当无现成技术方案时，基于 Phase A 产物 + 知识库自动生成）
Step 1: REQ 级覆盖扫描
Step 2: BR 级覆盖详查
Step 3: SE 覆盖审计
Step 4: GAP/OPEN 闭环检查
Step 5: 反向审计
Step 6: 自检（逐项对照 gate checklist，全部通过才能进入 Step 7）
Step 7: Judge/Critique（切换到批评者视角审视自己的输出）
Step 8: 修正（根据 Step 7 发现的问题修正报告，重新执行 Step 6）
→ 全部通过后才能 finalize
```

### Step 0: 输入准备与范围确认

1. 确认 Phase A 报告路径。
2. 收集技术方案文档清单（飞书直读优先）。
3. 无权限文档标记 `NEEDS_ACCESS` 列入风险项。
4. **技术方案输入质量检查**（参考 `skills/system-rules.md` §技术方案输入标准）：
   - 检查是否有 HLD（整体架构+数据模型+状态机）
   - 检查是否有 LLD（核心接口实现逻辑，不只是签名）
   - 仅有 HLD 缺 LLD：可继续执行 A.5，但在报告开头标注"技术方案缺少详细设计，覆盖度判定可信度受限"
   - HLD 也不完整：阻断执行，提示用户补充
5. Scope Challenge：技术方案覆盖 PRD 哪个子集？是否有多份需拼合？是否显式排除了某些需求？
5. **如果是重跑**，必须先读取旧版产物（`phase_a5_report.md`），新版必须是旧版的超集（覆盖判定数量不减少，已有结论不丢失）。
6. **已有实现扫描**（当提供代码仓库或知识库时执行）：
   - 扫描 master/main 分支（非 feature 分支）的已有接口、表结构、TMF 链路
   - 标注哪些 REQ 是增量改造（已有代码基础），哪些是全新开发
   - 对于 DDD+TMF 项目，梳理已有的 Step→Ability→Extension 链路，识别本次需求涉及的改造点
   - 输出 `EXISTING_IMPL` 章节，列出已有实现与本次需求的关系
   - 若用户未提供代码仓库，跳过此步，不影响后续流程

### Step 0.5: [可选] 技术方案生成

**触发条件**: 用户无现成技术方案文档，或技术方案尚未编写。由用户显式触发（`--generate-design`）。

**输入**:
- Phase A 产物（REQ/BR/SE/GAP/OPEN）
- 知识库（`knowledge/<repo>/*.toon`，已有架构/调用链/数据模型）
- 代码索引（SQLite 中的 code_symbols）
- EXISTING_IMPL（Step 0 的已有实现分析）

**生成流程（三阶段，参考 superpowers brainstorming → writing-plans）**:

#### 阶段 1: 设计探索（Brainstorming）

1. 逐 REQ 分析实现方案，每个 REQ 产出:
   - 改造范围: 新增/修改的类、接口、表
   - 候选方案（如有多种）: 列出 trade-off，推荐一种
   - 依赖的已有能力（从知识库 .toon 中提取）
2. 识别跨 REQ 的共性设计:
   - 新增领域模型（Entity/枚举/值对象）
   - 新增/修改数据库表
   - 新增/修改接口（Provider/API）
   - 状态机设计（如有）
3. 输出 `_design_exploration.md`

#### 阶段 2: 技术方案编写（Writing Design）

基于阶段 1 的探索结果，生成结构化技术方案文档 `tech_design.md`:

```markdown
# 技术方案: <项目名>

## 1. 概述
- 需求背景（引用 Phase A）
- 改造范围（新增/修改的模块）
- 技术栈与约束

## 2. 领域模型设计
- 新增/修改的 Entity、枚举、值对象
- 数据库表结构（DDL）
- 字段说明

## 3. 接口设计
- 新增/修改的 Provider 接口
- 请求/响应模型
- 接口契约

## 4. 核心流程设计
- 每个 REQ 的实现流程（调用链: Provider → App → Domain → Infrastructure）
- 状态机设计（如有，Mermaid 图）
- 异常处理策略

## 5. 数据同步与集成
- 与外部系统的交互（MQ/RPC/回调）
- 数据一致性保障

## 6. 非功能设计
- 并发控制（锁/幂等）
- 权限与数据隔离
- 性能考量
- 可观测性（日志/监控/告警）

## 7. 部署与兼容
- 存量数据兼容方案
- 分阶段部署计划
- 回滚策略

## 8. GAP/OPEN 闭环
- Phase A 中每个 GAP 的技术方案应对
- Phase A 中每个 OPEN 的决策结果
```

#### 阶段 3: 设计审查（Multi-Agent 互审）

技术方案生成后，由独立 Agent 审查（context 隔离，看不到生成过程）：

**Agent 1: 工程审查（Eng Review）**
1. **Scope Challenge**: 改动文件 >8 个或新增类 >2 个时，推荐更小的变更集
2. **Failure Mode 分析**: 每个新 codepath 列出一个生产故障场景，检查是否有错误处理
3. **完整性检查**: 每个 REQ/BR 是否都有对应的技术设计
4. **知识库交叉验证**: 设计是否与已有架构模式一致（从 .toon 中验证）
5. **并发/幂等/事务**: 写操作是否有锁保护，外部调用是否有重试/降级

**Agent 2: 需求对齐审查（Req Alignment Review）**
1. **正向覆盖**: Phase A 的每个 REQ/BR/SE 是否在技术方案中有对应设计
2. **GAP 闭环**: Phase A 的每个 GAP 是否在技术方案中有应对策略
3. **OPEN 决策**: Phase A 的每个 OPEN 是否已有决策结果
4. **语义保真**: 技术方案的设计是否准确反映了需求意图（不多不少）

**审查流程**:
```
Worker Agent 生成 tech_design.md
    ↓（独立 context）
Eng Review Agent → _eng_review.md（工程问题清单）
    ↓（独立 context）
Req Alignment Agent → _req_alignment_review.md（需求对齐问题清单）
    ↓
Worker Agent 根据两份审查修正 tech_design.md
    ↓
用户确认 → 进入 Step 1 审计
```

如果使用 `dqg-run orchestrate` 或 `dqg-run agent-run`，三个 Agent 自动编排。
如果在单 session 中执行，用 subagent 模拟独立 context。

**产出文件**:
- `tech_design.md` — 技术方案文档（主产物，后续 Step 1-5 的审计对象）
- `_design_exploration.md` — 设计探索过程记录
- `_eng_review.md` — 工程审查结果（独立 Agent）
- `_req_alignment_review.md` — 需求对齐审查结果（独立 Agent）

**约束**:
- 技术方案必须引用知识库中的已有类名/接口名，禁止编造不存在的类
- 每个设计决策标注依据（来自 Phase A 的哪个 REQ/BR/SE）
- 生成的方案需用户确认后才进入 Step 1 审计
- 如果用户已有技术方案文档，跳过此步直接进入 Step 1

### Step 1: REQ 级覆盖扫描

逐条检查 Phase A 的每个 REQ，标注覆盖状态和来源文档。

### Step 2: BR 级覆盖详查

按模块分组，逐条检查每个 BR 的前端/后端覆盖。

### Step 3: SE 覆盖审计

逐条检查每个 SE。对 MISSING/PARTIAL 项做 Failure Impact 分析：
`SE-xxx | MISSING | 最坏后果: <描述> | 影响范围: <用户/资金/数据>`

### Step 4: GAP/OPEN 闭环检查

- GAP：标记 `已闭环` / `部分闭环` / `未闭环`。
- OPEN：标记 `已闭环` / `未闭环`。
- 未闭环的高风险项（资金/安全/数据一致性）升级为 P0。

### Step 5: 反向审计

1. 技术方案新增设计（NEW_DESIGN）：Phase A 未识别的非功能需求，评估是否回补。
2. 技术方案显式排除（NOT_IN_SCOPE）：与 Step 0 交叉验证。
3. 新接口/新表/新流程无对应 REQ/BR：判断是技术细节还是遗漏。

### Step 6: 自检（提交前强制检查）

**写完报告后，必须逐项对照以下清单自检，全部通过才能进入 Step 7：**

- [ ] 每条 REQ 已标注覆盖状态
- [ ] 每条 BR 已检查前端/后端覆盖状态
- [ ] 每条 SE 已检查覆盖状态，MISSING/PARTIAL 项有 Failure Impact 分析
- [ ] 每条 GAP/OPEN 已检查闭环状态
- [ ] 反向审计已完成（NEW_DESIGN / NOT_IN_SCOPE / 无对应 REQ 的新设计）
- [ ] 每个覆盖判定有技术方案原文证据引用
- [ ] 未输出 UT/EUT
- [ ] 如果是重跑：新版是旧版的超集（覆盖判定数量不减少，已有结论不丢失）

### Step 7: Judge/Critique（提交前自我评审）

**自检通过后，切换到批评者视角审视自己的输出：**

1. **Judge 评审**：对照技术方案原文逐条验证每个覆盖判定的准确性。
   - 每个 COVERED 判定能否在技术方案中找到原文依据？
   - 每个 PARTIAL 判定的缺失维度是否准确？
   - 每个 MISSING 判定是否确实在技术方案中无对应设计？
   - IMPLICIT 判定的推导依据是否充分？

2. **Critique 批评**：假设输出有遗漏和错误，主动找问题。
   - 重点检查：前后端覆盖不一致、GAP/OPEN 闭环遗漏、反向审计盲区
   - 是否存在概括性描述覆盖状态而非引用技术方案原文的情况？
   - 每个发现记录为：问题类型（FN/FP/VAGUE）+ 严重度 + 修正建议

3. 将 Judge/Critique 发现的问题记录在报告末尾的"自我评审记录"章节。

### Step 8: 修正

根据 Step 7 发现的问题修正报告：
1. 修正不准确的覆盖判定。
2. 补充缺失的原文证据引用。
3. 修正前后端覆盖不一致的判定。
4. 补充遗漏的 GAP/OPEN 闭环检查。
5. 修正完成后，重新执行 Step 6 自检确认。

**全部通过后，才能执行 `dqg-run <project> finalize A.5`。**

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`（已由 context_loader 自动生成），不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase A 结构化产物（`phase_a_structured.json` / `phase_a_report.md`）是唯一的需求基线，不要回溯飞书原文。

## 输出模板

复用 `references/tech-design-coverage-template.md`。

## 通过标准

1. REQ 覆盖率 = 100%（允许 IMPLICIT 须附依据）
2. SE 覆盖率 >= 90%（MISSING 须有 GAP/OPEN 兜底）
3. P0 风险项已闭环或有明确排期
4. GAP 闭环率 >= 60%（高风险必须闭环）
5. OPEN 闭环率 >= 50%（资金/安全相关必须闭环）
6. Step 6 自检清单全部通过
7. Step 7 Judge/Critique 已执行且问题已修正
8. 每个覆盖判定有技术方案原文证据引用
9. 如果是重跑：新版是旧版超集（覆盖判定数量不减少，已有结论不丢失）

## 禁止事项

1. 禁止未显式提及时标 COVERED。
2. 禁止跳过 GAP/OPEN 闭环检查。
3. 禁止忽略前后端覆盖不一致。
4. 禁止存在 P0 未闭环时给"通过"结论。
5. 禁止跳过 Step 6 自检和 Step 7 Judge/Critique 直接 finalize。
6. 禁止重跑时从零重写，必须在旧版基线上增量修改，新版必须是旧版超集。
7. 禁止概括性描述覆盖状态，必须引用技术方案原文作为证据。
