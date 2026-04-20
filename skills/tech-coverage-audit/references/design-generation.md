# 技术方案生成流程（Step 0.5 详细规则）

## 触发条件

用户无现成技术方案文档，由用户显式触发（`--generate-design`）。

## 输入

- Phase Q01 产物（REQ/BR/SE/GAP/OPEN）
- 知识库（`knowledge/<repo>/*.toon`，已有架构/调用链/数据模型）
- 代码索引（SQLite 中的 code_symbols）
- EXISTING_IMPL（Step 0 的已有实现分析）

## 三阶段生成流程

### 阶段 1: 设计探索（Brainstorming）

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

### 阶段 2: 技术方案编写（Writing Design）

基于阶段 1 的探索结果，生成结构化技术方案文档 `tech_design.md`：

```markdown
# 技术方案: <项目名>

## 1. 概述
- 需求背景（引用 Phase Q01）
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
- Phase Q01 中每个 GAP 的技术方案应对
- Phase Q01 中每个 OPEN 的决策结果
```

### 阶段 3: 设计审查（Multi-Agent 互审）

技术方案生成后，由独立 Agent 审查（context 隔离，看不到生成过程）：

**Agent 1: 工程审查（Eng Review）**
1. Scope Challenge: 改动文件 >8 个或新增类 >2 个时，推荐更小的变更集
2. Failure Mode 分析: 每个新 codepath 列出一个生产故障场景，检查是否有错误处理
3. 完整性检查: 每个 REQ/BR 是否都有对应的技术设计
4. 知识库交叉验证: 设计是否与已有架构模式一致（从 .toon 中验证）
5. 并发/幂等/事务: 写操作是否有锁保护，外部调用是否有重试/降级

**Agent 2: 需求对齐审查（Req Alignment Review）**
1. 正向覆盖: Phase Q01 的每个 REQ/BR/SE 是否在技术方案中有对应设计
2. GAP 闭环: Phase Q01 的每个 GAP 是否在技术方案中有应对策略
3. OPEN 决策: Phase Q01 的每个 OPEN 是否已有决策结果
4. 语义保真: 技术方案的设计是否准确反映了需求意图（不多不少）

**审查流程：**
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

## 产出文件

- `tech_design.md` — 技术方案文档（主产物，后续 Step 1-5 的审计对象）
- `_design_exploration.md` — 设计探索过程记录
- `_eng_review.md` — 工程审查结果（独立 Agent）
- `_req_alignment_review.md` — 需求对齐审查结果（独立 Agent）

## 约束

- 技术方案必须引用知识库中的已有类名/接口名，禁止编造不存在的类
- 每个设计决策标注依据（来自 Phase Q01 的哪个 REQ/BR/SE）
- 生成的方案需用户确认后才进入 Step 1 审计
