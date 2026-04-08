---
name: dqg-system-rules
description: "所有 Phase Agent 必须遵守的通用规则"
---

# 通用系统规则

所有 Phase Agent 在执行任务时必须遵守以下规则。

## 语言规则

- 使用简体中文输出，技术术语保留英文（如 REQ、BR、SE、GAP、OPEN、EUT、DDD、TMF）
- ID 格式严格遵循定义（REQ-xxx、BR-xxx、SE-xxx 等），禁止自由命名

## 反幻觉公约

| 约束 | 要求 | 标注格式 |
|:---|:---|:---|
| 来源追溯 | 每条结论必须标注来源 | `[来源: 文件名:行号]` 或 `[来源: PRD 第X节]` |
| 置信度标注 | 区分事实与推断 | `High` / `Medium` / `Low` |
| 禁止行为 | 严禁编造不存在的接口、字段、逻辑 | — |

**置信度定义：**
- **High**: 直接来自需求文档/代码/技术方案的内容
- **Medium**: 基于 DDD/TMF 规范的合理推断
- **Low**: AI 补充内容，需人工确认，标注 `[待确认]`

## 思维规则

执行任何 Phase 任务时，遵循：
1. **理解** — 完整读取输入材料，不跳读不假设
2. **检索** — 从上游产物和参考文件中查找证据
3. **规划** — 按 skill 定义的 Step 顺序执行
4. **反思** — 完成后自检完整性 Gate + Judge/Critique

## 推理日志（所有 Phase 必须输出）

每个 Phase 执行时，必须同步输出 `_reasoning_log.md` 到 phase 目录，记录每一步的决策过程。

**推理日志是和报告同等重要的交付物，不是可选项。**

### 日志结构

```markdown
# Reasoning Log — Phase <ID>

## Step 0: [步骤名]
- 执行时间: ...
- 输入: 读取了什么文件/数据
- 决策: 做了什么判断，为什么
- 发现: 关键发现（如识别到状态机图、发现 PRD 矛盾点）
- 风险: 本步骤的不确定性

## Step N: ...
（每个 Step 都要记录）

## 自检记录
- [ ] 检查项1: 通过/未通过（原因）
- [ ] 检查项2: ...

## Judge/Critique 记录
- Judge 评分: X/5
- 发现的问题:
  1. [FN/FP/VAGUE] 描述 → 修正方案
- Critique 结论: 需要修正 / 无需修正

## 修正记录
- 修正1: 原内容 → 修正后内容（原因）
- 修正2: ...
```

### 日志要求

1. **每个 Step 必须记录**：输入了什么、做了什么决策、依据是什么、置信度多少
2. **关键决策必须记录理由**：为什么这个标 COVERED 不是 PARTIAL？为什么这个是 GAP 不是 OPEN？
3. **不确定的判断必须标注**：置信度 Low 的结论要记录为什么不确定
4. **Judge/Critique 的发现必须记录**：发现了什么问题、严重度、是否修正
5. **重跑时必须记录 diff**：和旧版对比，新增了什么、修改了什么、为什么

### 日志用途

- **复盘**：做对了什么（可复制的经验）、做错了什么（需要改进的规则）
- **迭代**：哪些 Step 的决策质量低 → 改进 skill prompt
- **追溯**：某个 GAP 是在哪个 Step 发现的？某个 BR 为什么写成概括性描述？
- **实验**：对比不同 prompt 版本的推理过程差异

## 通用执行流程（所有 Phase 适用）

所有 Phase 必须按以下流程执行，不得跳步：

```
证据采集 → 全量理解 → 结构化产出 → 自检 → Judge/Critique → 修正 → finalize
```

1. **证据采集**：获取所有输入材料（文档/图片/代码/上游产物）
2. **全量理解**：通读所有材料，建立完整业务理解，图片必须先解析
3. **结构化产出**：按 skill 定义的规则输出报告 + JSON
4. **自检**：逐项对照 gate checklist，如果是重跑必须 diff 旧版
5. **Judge/Critique**：切换到批评者视角审视自己的输出，记录发现
6. **修正**：根据 Judge/Critique 修正报告，重新自检
7. **finalize**：全部通过后才能执行 `dqg-run finalize`

**禁止跳过 Step 4-6 直接 finalize。**

## 重跑规则

重跑任何 Phase 时：
1. 必须先读取旧版产物作为基线
2. 新版必须是旧版的超集（数量不减少，内容不丢失）
3. 在 `_reasoning_log.md` 中记录 diff：新增了什么、修改了什么、为什么
4. 禁止从零重写

## 行动规则

1. **脚本优先** — 状态管理通过 `dqg-run` 执行，禁止手动修改状态文件
2. **证据优先** — 每条评审结论附具体证据，禁止"看起来合理"等无证据表述
3. **结构化输出** — 同时产出 markdown 报告 + JSON 结构化文件
4. **Confirm-first** — 所有产物修改须经人工确认，禁止自动 commit/push

## 技术方案输入标准（Phase A.5/A.6 强制要求）

Phase A.5/A.6 接收技术方案时，必须按以下标准检查输入质量。**不满足最低要求时，必须阻断执行并告知用户补充。**

### 技术方案分层定义

技术方案必须分为两个层次，可以是两个文档，也可以是同一文档的两个章节：

#### 概要设计（HLD — High Level Design）

面向架构师和 PM，回答"做什么、怎么组织"：

| 必须包含 | 说明 |
|---------|------|
| 整体架构图 | 模块边界、系统交互关系、数据流向 |
| 数据模型 | ER 图或核心表结构（字段+类型+索引） |
| 状态机设计 | 所有状态枚举、迁移条件、异常终结路径 |
| 系统交互时序图 | 关键流程的跨系统调用顺序（含保司回调） |
| 非功能性设计 | 并发控制、幂等设计、事务边界、资金安全（涉及资金必须包含） |
| GAP/OPEN 闭环 | Phase A 中每个 GAP/OPEN 的技术应对策略 |

#### 详细设计（LLD — Low Level Design）

面向开发，回答"怎么实现、每个类做什么"：

| 必须包含 | 说明 |
|---------|------|
| DDD 各层职责分配 | 每个模块在 Client/App/Domain/Infrastructure 层的类和职责 |
| 每个接口的实现逻辑 | 不只是签名，要有处理步骤（查询→校验→业务逻辑→写库→返回） |
| 关键方法的 happy path + error path | 正常流程和异常处理分别描述 |
| 数据库操作细节 | 事务边界、锁策略、SQL 关键条件 |
| 外部调用细节 | 超时配置、重试策略、降级方案 |

### 最低输入要求（不满足则阻断）

执行 Phase A.5/A.6 前，检查技术方案是否满足：

- [ ] **HLD 存在**：有整体架构说明和数据模型
- [ ] **状态机完整**：有状态枚举和迁移条件
- [ ] **LLD 存在**：至少有核心接口的实现逻辑描述（不只是签名）
- [ ] **非功能性设计存在**：有并发/幂等/事务说明

**不满足时的处理**：
- 仅有 HLD 缺 LLD → 可执行 A.5（覆盖度审计），但 A.6 必须阻断，提示"技术方案缺少详细设计，无法评审实现质量"
- HLD 也不完整 → A.5 和 A.6 均阻断，提示"技术方案不满足最低输入要求"

### 典型缺陷示例（避免接受此类方案）

❌ **只有接口签名，无实现逻辑**：
```
Result<DamageAssessmentDetailResp> getDetail(Long assessmentId);
// 缺少：查询哪些表、如何组装、脱敏规则、权限校验
```

❌ **只有表结构，无事务边界**：
```
CREATE TABLE damage_assessment (...);
CREATE TABLE damage_assessment_detail (...);
// 缺少：两张表的写入是否在同一事务、失败如何回滚
```

❌ **只有调用链名称，无处理细节**：
```
DamageAssessmentService.submit() → PingAnGateway.submitAssessment()
// 缺少：超时配置、失败处理、状态回退逻辑
```

✅ **合格的 LLD 示例**：
```
saveDraft(req):
  1. 校验：assessment.status == DRAFT（非草稿状态不允许编辑）
  2. 校验：操作人 == assessment.createdBy 或有管理员权限
  3. 更新主表：UPDATE damage_assessment SET ... WHERE id=? AND status=0
  4. 删除旧明细：DELETE FROM damage_assessment_detail WHERE assessment_id=? AND source='STORE'
  5. 批量插入新明细：INSERT INTO damage_assessment_detail (...)
  6. 删除旧附件（已删除的）：软删除 WHERE id NOT IN (req.attachmentIds)
  7. 插入新附件：INSERT INTO damage_assessment_attachment (...)
  8. 步骤 3-7 在同一 @Transactional 事务中
  9. 返回：Result.success()
```

---

## DDD+TMF 链路追踪规则

对于 DDD+TMF 架构的项目，所有涉及代码分析的 Phase（A.5/A.6/B/C/D）必须遵守：

1. **禁止孤立分析** — 不得仅看单个类就下结论。某个能力（幂等、并发控制、状态校验、事务保护）可能在调用链路的任意层实现
2. **完整链路追踪** — 分析任何功能点时，必须追踪完整的 TMF 链路：
   ```
   Provider → CmdExe → DomainService → TMF.execute
   → decideSteps → Step → Ability → Extension → Gateway/Mapper
   ```
3. **多入口检查** — 同一个 Ability/Step 可能被多个入口调用（用户操作、定时任务、MQ 消费、BPM 回调、RPC 调用）。不同入口的保护链路可能不同，需逐一确认
4. **保护点标注** — 每个发现必须标注该能力在链路的哪一层实现或缺失，格式：`[链路: Provider → ... → Step(XxxStep) → Ability(XxxAbility)]`
5. **上下层联动** — 如果某个类缺少某功能，先检查：
   - 上层是否已做？（如 Service 层加了分布式锁，Step 层不需要再加）
   - 下层是否已做？（如 Gateway 层的 SQL 有 WHERE 条件保护）
   - 是否有其他 Step 在同一链路中已处理？（如 DuplicateCheckStep 在 OrderRefundStep 之前执行）
