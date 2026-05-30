# RDT-Inspired Review Optimization Design

> 三个借鉴 Recurrent Depth Transformer 设计模式的 Qualix 审查优化。
> P1: ACT 审查深度自适应 | P2: 锚点注入防漂移 | P3: 共享+路由 Judge

## 背景

OpenMythos 的 RDT 架构在模型层有三个设计模式可翻译到 Qualix 应用层：

| RDT 概念 | Qualix 翻译 | 收益 |
|----------|---------|------|
| Adaptive Computation Time | 审查深度按 risk_tier 分级 | 直接省 token（LOW tier ~60-70%） |
| 循环块锚点注入 B·e | Adaptive Loop 每轮重注入原始需求 | 防多轮修正漂移 |
| MoE 路由+共享专家 | Judge rubric 分 shared/routed 两层 | 领域深度 + 通用底线 |

## P1: ACT 审查深度自适应

### 问题

Adaptive loop 对所有文件用相同深度（max_iterations=3, 全量 Judge + Critique）。
简单改动（改常量、改文案）和复杂改动（新增业务逻辑、改核心流程）消耗相同 token。

### 设计

复用 blast_radius 的 `risk_tier` 作为 complexity proxy，在 adaptive loop 启动时查表决定审查深度。

#### 深度配置表

```python
# constants.py
REVIEW_DEPTH_CONFIG = {
    "LOW":      {"max_iterations": 1, "force_secondary": False, "skip_critique": True},
    "MEDIUM":   {"max_iterations": 2, "force_secondary": False, "skip_critique": False},
    "HIGH":     {"max_iterations": 3, "force_secondary": True,  "skip_critique": False},
    "CRITICAL": {"max_iterations": 3, "force_secondary": True,  "skip_critique": False},
}
REVIEW_DEPTH_DEFAULT = "MEDIUM"  # 无 blast_radius 时的 fallback
```

| risk_tier | depth | max_iter | judge 策略 | critique |
|-----------|-------|----------|-----------|----------|
| LOW | light | 1 | primary only | 跳过 |
| MEDIUM | standard | 2 | primary + boundary secondary（现有逻辑） | 执行 |
| HIGH | deep | 3 | primary + 强制 secondary | 执行 |
| CRITICAL | deep | 3 | primary + 强制 secondary | 执行 |

#### 无 blast_radius 的 fallback

非代码审查 Phase（Q01/Q03 等）没有 `_blast_radius.json`，默认 `MEDIUM` 深度。

### 改动范围

| 文件 | 改动 |
|------|------|
| `constants.py` | 新增 `REVIEW_DEPTH_CONFIG` + `REVIEW_DEPTH_DEFAULT` |
| `adaptive_loop.py:AdaptiveLoop.run()` | 启动时读 `_blast_radius.json` → 取 risk_tier → 查表覆盖 max_iterations；skip_critique 控制 critique agent 是否执行 |
| `judge_vote.py:multi_judge_vote()` | 新增 `force_secondary: bool = False` 参数，True 时跳过 boundary 判断直接触发 secondary |

### Token 节省估算

- LOW tier: 3 轮 × (Worker + Judge + Critique) → 1 轮 × (Worker + Judge)，省 ~60-70%
- MEDIUM tier: 3 轮 → 2 轮，省 ~30%
- HIGH/CRITICAL: 不变，但 secondary 验证更充分

## P2: 锚点注入防漂移

### 问题

`handoff_builder.py` 当前只传 Judge issues + Critique findings + 通用 Goal。
多轮修正后 Worker 只在修 Judge 反馈，偏离原始需求（REQ/BR/SE）。

### 设计

两层锚点注入，对应 RDT 的 B·e 项（每轮循环重新注入原始 embedding）。

#### Layer 1: handoff 文档新增 Anchor section

在 handoff 文档的 Goal 和 Progress 之间插入 `## Anchor（原始需求锚点）`：

```markdown
## Anchor（原始需求锚点 — 修正时不可偏离）

以下是本 Phase 的原始需求事实，每轮修正必须对齐：

### 核心需求 (REQ)
- REQ-001: ...
- REQ-002: ...

### 关键业务规则 (BR)
- BR-001: ...

### 语义元素 (SE)
- SE-001: ...
```

- 从 `_upstream_context.md` 或 `_evidence_pack.json` 提取
- 限制 ~800 token（top-N REQ + 关键 BR + 核心 SE）
- 正则匹配已有的结构化格式（`REQ-\d+`, `BR-\d+`, `SE-\d+`）

#### Layer 2: context_files 保留完整上游产物

- iter 0 的 Worker 已经通过 context_files 看到 `_upstream_context.md`
- 改动：iter N>0 的 Fixer 也保留这个 context_file
- Worker 既有摘要锚点（handoff 里快速定位），又能回查完整上游（context_file 里深入验证）

### 改动范围

| 文件 | 改动 |
|------|------|
| `handoff_builder.py` | `build_handoff_document()` 新增 `anchor_facts: str \| None` 参数，插入 Anchor section |
| `handoff_builder.py` | 新增 `extract_anchor_summary(upstream_path: Path) -> str`，从上游产物提取 REQ/BR/SE 摘要 |
| `adaptive_loop.py:_execute_iteration()` | iter>0 时：(1) 读 `_upstream_context.md` 提取摘要传给 handoff_builder；(2) 把完整上游文件加入 Fixer 的 context_files |

### 锚点提取逻辑

```python
def extract_anchor_summary(upstream_path: Path, max_tokens: int = 800) -> str:
    """从 _upstream_context.md 提取 REQ/BR/SE 摘要作为锚点."""
    # 1. 正则匹配 REQ-\d+, BR-\d+, SE-\d+ 开头的行
    # 2. 按类型分组，每组取前 N 条
    # 3. 截断到 max_tokens
```

## P3: 共享 Judge + 路由 Judge

### 问题

所有 Judge 用同一份 rubric，模型异构但评审维度同构。
Q03（技术方案质量）和 Q07（代码审查）用完全相同的评分框架，缺乏领域深度。

### 设计

拆分 rubric 为 shared + routed 两层，对应 MoE 的共享专家 + 路由专家。

#### Shared rubric（通用质量底线，权重 40%）

每个 Phase 都评估的 4 个维度：

| 维度 | 说明 |
|------|------|
| source_citation | 来源标注完整性（`[来源: 文件名:行号]`） |
| confidence_tagging | 置信度标注（High/Medium/Low） |
| structural_completeness | 必要章节齐全 |
| reasoning_quality | 推理日志质量（决策过程可追溯） |

#### Routed rubric（Phase-specific，权重 60%）

按 Phase ID 路由到专属评审维度：

| Phase | 路由维度 |
|-------|---------|
| Q01 | 需求完整性、边界约定清晰度、SE 可追溯性 |
| Q03 | 架构合理性、风险识别、AI 亲和性 |
| Q04 | 覆盖率准确性、GAP 有效性、需求对齐 |
| Q05 | EUT 覆盖、断言强度、Mock 层级、可编译性 |
| Q06 | 场景覆盖质量、弱断言检测、增量覆盖率 |
| Q07 | 发现有效率、blast radius 感知、代码模式、需求对齐 |

#### 与 dynamic_rubric 的关系

三层 rubric 叠加，权重归一化：
1. **Shared** (40% 基础) — 通用质量底线
2. **Routed** (60% 基础) — Phase 领域深度
3. **Dynamic** (追加 15%×N, max 3) — SE 类型分布微调（现有 `dynamic_rubric.py` 不变）

权重归一化策略：shared + routed 始终按 40:60 比例分配。dynamic 维度追加后，所有维度权重等比缩放使总和 = 100%。例如有 2 个 dynamic 维度时：shared 34% + routed 51% + dynamic 15%（比例 40:60:15:15 归一化）。

#### compose_rubric 组合逻辑

```python
def compose_rubric(phase_id: str, dynamic_dimensions: list | None = None) -> str:
    """组合 shared + routed + dynamic rubric."""
    shared = SHARED_RUBRIC_DIMENSIONS  # 4 维度, 40%
    routed = PHASE_ROUTED_RUBRICS.get(phase_id, [])  # Phase-specific, 60%
    dynamic = dynamic_dimensions or []  # SE-driven, 追加

    # 渲染为 Judge 可消费的 rubric 文本
    return _render_rubric(shared, routed, dynamic)
```

### 改动范围

| 文件 | 改动 |
|------|------|
| `constants.py` | 新增 `SHARED_RUBRIC_DIMENSIONS` 常量 |
| `judge_rubrics.py` | 新增 `PHASE_ROUTED_RUBRICS` 字典 + `compose_rubric()` 函数 |
| `judge_vote.py:multi_judge_vote()` | 接受 `phase_id` 参数，内部调用 `compose_rubric()` |
| `adaptive_loop.py` | 传 `phase_id` 给 `multi_judge_vote()`（当前只传 rubric 字符串） |

## 数据流总览

```
blast_radius.json ──→ risk_tier ──→ REVIEW_DEPTH_CONFIG ──→ adaptive_loop
                                         │
                                         ├─ max_iterations
                                         ├─ force_secondary
                                         └─ skip_critique

_upstream_context.md ──→ extract_anchor_summary() ──→ handoff Anchor section
         │                                                    │
         └─────────────── context_files ──────────────→ Fixer Worker

phase_id ──→ compose_rubric() ──→ shared + routed + dynamic ──→ Judge
```

## 测试策略

| 改动 | 测试 |
|------|------|
| P1 REVIEW_DEPTH_CONFIG | 单测：risk_tier → depth config 映射正确；无 blast_radius 时 fallback 到 MEDIUM |
| P1 force_secondary | 单测：force_secondary=True 时跳过 boundary 判断 |
| P2 extract_anchor_summary | 单测：从样例 upstream_context 提取 REQ/BR/SE；空文件返回空字符串；超长截断 |
| P2 handoff Anchor section | 单测：anchor_facts 非空时 handoff 包含 Anchor section；为空时不包含 |
| P3 compose_rubric | 单测：每个 Phase 组合结果包含 shared + routed 维度；未知 Phase fallback 只有 shared |
| 集成 | adaptive_loop 端到端：mock blast_radius + upstream_context，验证深度/锚点/rubric 三者联动 |

## 不做的事

- 不新建 ReviewPolicy 抽象层（YAGNI，三个改进本质独立）
- 不改 LoopHealthMonitor（早停逻辑与深度分级正交）
- 不改 dynamic_rubric.py（第三层微调保持不变）
- 不改 risk_score.py 的评分算法（复用现有 tier）
- 不做文件级 cyclomatic complexity（risk_tier 已足够，YAGNI）

## 风险

| 风险 | 缓解 |
|------|------|
| LOW tier 跳过 critique 可能漏掉问题 | LOW tier 仍有 Judge 兜底；risk_tier 本身经过 5 因子加权，LOW 意味着改动确实简单 |
| 锚点摘要提取不准（正则匹配） | fallback：提取失败时不注入锚点，退化为现有行为 |
| routed rubric 维度权重不合理 | 初始权重基于现有 PHASE_RUBRICS，后续通过 score_calibration 监控漂移 |

*设计日期: 2026-04-25*
