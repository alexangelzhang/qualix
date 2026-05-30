# Phase-Level Evaluation Protocol Design

> 给 7 个 Phase 的 Judge 和 Critique 配备专属评估协议，替代通用人设。
> 基于研究结论：具体检查清单 + 行为约束 >> 身份标签。

## 背景

### 问题

Qualix 有 7 个 Phase × 3 个角色 = 21 个 agent 实例，但只有 3 套人格。
Worker 通过 skill 文件获得 Phase 专属指令，但 Judge 和 Critique 共享通用 prompt。

Q01 Judge（审需求）和 Q07 Judge（审代码）用同一个"10 年质量负责人"视角。
Q03 Judge 发现的"技术方案缺少降级策略"这类经验，下次审同类方案时没有被复用。

### 研究结论

三篇独立研究一致确认（PRISM/USC 2026, EMNLP 2024, Wharton 2025）：

| 机制 | 对知识/推理任务的效果 |
|------|---------------------|
| 身份标签（"你是 10 年专家"） | 无效甚至负面（MMLU -3.6%） |
| 具体检查清单 | 有效（核心驱动力） |
| 行为约束/红线 | 有效（+17.7% alignment） |
| 领域词汇表 | 中等有效 |
| 结构化输出契约 | 有效（MetaGPT 核心发现） |

## 设计

### 数据模型

```python
@dataclass
class AgentProtocol:
    """单个角色（Judge/Critique）的评估协议."""
    role_label: str           # 路由标签（不注入 prompt，仅日志/路由）
    checklist: list[str]      # 必须逐条检查的清单
    red_lines: list[str]      # 行为红线（绝对不能做的事）
    domain_vocab: dict[str, str]  # 领域词汇表
    focus_areas: list[str]    # 重点检查方向
    not_applicable: str       # 何时返回 NOT_APPLICABLE

@dataclass
class PhaseProtocol:
    """一个 Phase 的完整评估协议."""
    phase_id: str
    judge: AgentProtocol
    critique: AgentProtocol
```

存储位置：`src/qualix/quality/evaluation_protocols.py`

### 两层架构

```
PhaseProtocol
├── static: AgentProtocol（人工维护，低频更新）
│   ├── checklist: 基础检查清单
│   ├── red_lines: 行为红线
│   └── domain_vocab: 领域词汇
└── dynamic: auto-accumulated（自动积累，零维护）
    ├── phase_genes: 该 Phase 历史 Critique Gene（按 phase_id 过滤）
    ├── phase_lessons: 该 Phase 历史 bug case lessons（按 phase_id 过滤）
    └── phase_patterns: 该 Phase 高频失败模式
```

static 层是领域知识结晶，变化很慢。dynamic 层从执行历史自动积累。

### 7 Phase Judge Protocol

**Q01 需求结构化**
- role_label: 需求完整性审查员
- checklist:
  - PRD 每个功能点是否提取为 REQ
  - 隐式业务规则是否显式化为 BR
  - 关键语义是否提取为可验证 SE
  - 模糊点是否标记为 GAP/OPEN
  - 边界约定（必须做/需确认/禁止做）是否完整
- red_lines:
  - 不评估技术可行性
  - 不补充 PRD 未提及的需求
  - 不把正常业务流程当 GAP
- focus: 并发幂等隐式语义、金额精度隐式约束、状态机边界条件

**Q02 技术方案生成**
- role_label: 方案完整性审查员
- checklist:
  - 方案是否包含 HLD + LLD + DTO + 流程图 + 伪代码
  - 是否满足 AI 亲和性标准（完整到 AI 可直接编码）
  - 接口协议清单是否完整
  - 部署灰度方案是否明确
- red_lines:
  - 不评估需求合理性
  - 不替代架构师做技术选型
- focus: AI 亲和性、接口完整性

**Q03 技术方案质量评审**
- role_label: 技术方案质量审查员
- checklist:
  - 每个写操作是否有 Failure Mode 分析
  - 9 类异常分支是否逐类检查
  - RPC 调用是否有超时重试降级
  - 数据一致性方案是否明确（事务/补偿/最终一致）
  - SE 是否可直接转化为测试用例
- red_lines:
  - 不评估需求合理性（Q01 的事）
  - 不建议具体技术选型（只审方案完整性）
- focus: 跨服务调用失败路径、并发冲突处理、资金安全设计

**Q04 技术方案覆盖度审计**
- role_label: 覆盖度审计员
- checklist:
  - 每条 REQ/BR/SE 是否在技术方案中有对应设计
  - COVERED 判定是否有具体设计证据（不是仅提到接口名）
  - MISSING 是否真的缺失
  - 技术方案中超出 PRD 范围的设计是否标记为 NEW_DESIGN
- red_lines:
  - 不评估技术方案质量（Q03 的事）
  - 不把 PARTIAL 乐观判为 COVERED
- focus: 异常分支覆盖、反向审计

**Q05 单测生成**
- role_label: 单测质量审查员
- checklist:
  - 每条 REQ/BR/SE 是否有对应 EUT
  - Happy Path + Exception + Boundary 三种路径是否覆盖
  - 断言是否验证业务语义（不是 assertNotNull）
  - Mock 层级是否合理（Real > Fake > Stub > Mock）
  - 代码是否可编译
- red_lines:
  - 不评估被测代码质量
  - 不接受 assertNotNull 冒充覆盖
- focus: 断言强度、SE 追溯性、编译可行性

**Q06 单测覆盖审计**
- role_label: 覆盖审计员
- checklist:
  - 每条 EUT 的覆盖状态判定是否正确
  - 弱断言是否标记为 WRONG_TARGET
  - T1 核心异常分支是否有测试
  - 测试数据是否覆盖真实故障组合（多记录/边界值/枚举组合）
- red_lines:
  - 不评估测试代码风格
  - 不把 assertNotNull 判为 COVERED
  - 团队有意的模式冲突标记 CONFLICT 而非误判
- focus: 弱断言检测、场景覆盖质量、增量覆盖率

**Q07 代码评审**
- role_label: 代码审查员
- checklist:
  - 每个 finding 是否有具体文件:行号证据
  - REQ/BR/SE 在代码中的实现是否完整
  - 改动点的完整调用链是否追踪（Controller→Service→Domain→Gateway）
  - blast radius 内的 callers/tests 是否评估
  - 严重级别分级是否合理
- red_lines:
  - 不评估代码风格偏好
  - 不做影响评估（留给 approve 阶段）
  - 每轮独立评审不考虑历史改进
- focus: 需求-代码对齐、调用链路完整性、blast radius 感知

### 7 Phase Critique Protocol

Critique 的核心差异：假设 Worker 和 Judge 都有遗漏，主动找盲区。

每个 Phase 的 Critique focus_areas 与 Judge checklist 正交——Judge 检查"该做的做了没"，Critique 检查"没想到的有没有"：

| Phase | Judge 视角 | Critique 视角 |
|-------|-----------|-------------|
| Q01 | PRD 提取完整性 | 隐式需求挖掘（并发/幂等/安全/性能） |
| Q02 | 方案结构完整性 | 方案可落地性（依赖风险/技术债/运维成本） |
| Q03 | 异常覆盖完整性 | 跨服务级联失败、数据不一致窗口 |
| Q04 | 覆盖判定准确性 | 隐式覆盖（代码里有但方案没写）、过度设计 |
| Q05 | EUT 覆盖完备性 | 测试可维护性、Mock 真实性、数据模式缺口 |
| Q06 | 审计判定准确性 | 巧合正确（Mock 返回固定值恰好通过）、断言目标偏移 |
| Q07 | Finding 有效性 | 遗漏的安全风险、性能瓶颈、向后兼容破坏 |

### 经验沉淀机制

**积累**：现有 Gene 结构扩展 `phase_id` + `agent_role` 字段

```python
# 扩展后的 Gene
{
    "pattern": "技术方案缺少降级策略",
    "confidence": 0.85,
    "source_project": "rights-platform",
    "phase_id": "Q03",        # 新增
    "agent_role": "judge",     # 新增
}
```

触发点不变：adaptive loop 结束后 SkillReflector 提取，标注 phase_id 和 agent_role。

**注入**：`context_loader.py` 按 phase_id + agent_role 过滤，Q03 Judge 只看 Q03 Judge 的历史经验。

### 注入流程

```
adaptive_loop.run()
├── 1. 读 PhaseProtocol[phase_id]
│   ├── static.judge.checklist → 注入 Judge prompt
│   ├── static.judge.red_lines → 注入 Judge prompt
│   └── static.judge.domain_vocab → 注入 Judge prompt
├── 2. 查询 dynamic 经验（phase_id + "judge" 过滤）
│   ├── phase_genes → 追加到 checklist 末尾
│   └── phase_lessons → 追加到 checklist 末尾
├── 3. compose_rubric() 组合评审维度（已有）
├── 4. 执行 Judge
├── 5. finalize 时 handle_protocol_compliance 检查
│   ├── checklist 覆盖率 < 100% → BLOCKED (HARD)
│   └── dynamic 经验注入数 = 0 → WARNING (SOFT)
└── 6. 结果写入 _gate_verdict.json
```

### 门控机制

三层强制，与现有铁律执行体系一致：

| 层级 | 机制 | 级别 |
|------|------|------|
| 第一层 | `handle_protocol_compliance` finalize handler (required) | static checklist 未覆盖 → BLOCKED |
| 第二层 | GateVerdict 接入 | HARD violation，approve 无法绕过 |
| 第三层 | 可观测性 | `_adaptive_summary.json` 记录 protocol_context（static + dynamic 注入数），observe 追踪经验注入率 |

static checklist 是 HARD gate（缺失就阻断）。
dynamic 经验是 SOFT（缺失记录但不阻断，新项目初期可能为空）。

### 改动范围

| 文件 | 改动 |
|------|------|
| 新建 `quality/evaluation_protocols.py` | PhaseProtocol + AgentProtocol 数据结构 + 7 Phase 的 static 配置 |
| 修改 `quality/gene_store.py` | Gene 结构加 phase_id + agent_role 字段 |
| 修改 `context/context_loader.py` | Gene 注入按 phase_id + agent_role 过滤 |
| 修改 `agents/adaptive_loop.py` | 注入 protocol checklist/red_lines 到 Judge/Critique prompt |
| 新建 `runtime/handlers_protocol.py` | handle_protocol_compliance finalize handler (required) |
| 修改 `runtime/gate_verdict.py` | 接入 protocol compliance 检查结果 |
| 修改 `agents/judge_vote.py` | multi_judge_vote 接受 protocol context |

### 不做的事

- 不给 agent 写人设故事（研究证明无效）
- 不改 Worker（已有 skill 文件驱动）
- 不改 dynamic_rubric.py（SE 驱动的动态维度保持不变）
- 不改投票逻辑（共识机制与 protocol 正交）
- 不改 compose_rubric（rubric 维度和 protocol checklist 是互补关系，不是替代）

### 与 compose_rubric 的关系

两者互补：
- compose_rubric：定义评审维度和评分标准（"从哪些角度打分"）
- EvaluationProtocol：定义检查清单和行为约束（"具体检查什么、不能做什么"）

Judge prompt = compose_rubric 输出 + protocol checklist + protocol red_lines + dynamic 经验

### 风险

| 风险 | 缓解 |
|------|------|
| static checklist 过时 | checklist 基于领域知识，变化慢；skill 文件更新时同步检查 |
| dynamic 经验噪音 | 复用现有 Gene confidence 过滤（≥0.7 才注入） |
| checklist 覆盖率检测误报 | Judge 可以标记某项为 N/A（有理由即可），不要求每项都 PASS |
| 14 套协议维护成本 | static 层低频更新；dynamic 层零维护 |

*设计日期: 2026-04-25*
