# P0 Design: Skill Evolution 全自动闭环 + Anti-Rationalization 运行时强制

> Date: 2026-04-15
> Status: Approved
> Source: qualix-new-knowledge-crossref-2026-04-15.md (Memento Reflect-Write + AgentSpec DSL)

---

## Feature 1: Skill Evolution 全自动闭环

### Problem

Skill Evolution 是半自动的：`skill_factory.py` 生成 suggestions → 人工审核 → 手动合并。
Memento 模式证明全自动闭环可行：失败 → 反思 → 重写 skill → 写回 → 下次自动生效。

### Design

#### Trigger

触发条件需要区分语义性质量失败和 Judge 基础设施失败：

```
Adaptive Loop (max 3 iters)
  └─ All FAIL
       ├─ judge_health_check()
       │    ├─ INFRA_FAILURE (JSON parse fail / model refuse / tool_call hallucination)
       │    │    → 降级为手动 judge 模式，不触发 Reflect
       │    └─ SEMANTIC_FAIL (有效 Judge 票，失败类型为质量问题)
       │         → SkillReflector.reflect_and_write()
       └─ Manual judge/critique 结果导入（fallback 入口）
            → 同样可触发 Reflect（不绑死在 adaptive 链路上）
```

**Judge Health Gate**（新增前置检查）：
- 检查 3 轮 judge results 中有效票数（valid_votes >= 2）
- 有效票 = JSON 解析成功 + 包含 overall_score + dimensions 完整
- 有效票不足 → `INFRA_FAILURE`，记录到 `_adaptive_summary.json`，不进入 reflect
- 有效票充足 → `SEMANTIC_FAIL`，允许进入 reflect

**Manual Judge Fallback 入口**：
- 当 adaptive Judge 不可靠时，用户可通过手动 judge/critique 产出结果
- 手动结果写入标准 `_judge_result.json`（canonical schema，见下文 JudgeRunner）
- SkillReflector 同时接受 adaptive judge_results 和 manual judge_result 作为输入

> 设计决策：adaptive Judge 当前仍有基础设施噪声（JSON parse 失败、tool_call 幻觉等），
> 如果不区分失败类型，Reflect 会把基础设施噪声误学成 skill 缺陷。
> 同时不能把 Skill Evolution 绑死在 adaptive 链路上，手动 judge 也应能触发。

#### Root Cause → Write Strategy

v1 只允许 `SKILL_RULE` 自动进化，其他类型一律降级为 `HUMAN_REVIEW`：

| root_cause | Write Target | v1 Action |
|------------|-------------|-----------|
| SKILL_RULE | Skill 文件规则段落（markdown） | 自动合并（通过 confidence gate + verify） |
| KNOWLEDGE | Knowledge network | HUMAN_REVIEW（生成建议文件） |
| CONTEXT | `constants.py` token budget | HUMAN_REVIEW（影响全局框架行为） |
| SCHEMA | Phase contract hard_checks | HUMAN_REVIEW（影响全局框架行为） |

> 设计决策：CONTEXT/SCHEMA 影响的是全局 runtime 行为，不是单个 Phase 的 skill 文本。
> 单项目失败不应直接升级为共享 runtime 自动改写，golden verify 无法兜住框架级回归。

#### Confidence Gate

support count 基于 fingerprint 去重的历史 bug case 聚类：

1. reflect() 从 judge results 提取失败模式
2. 计算 case fingerprint = `hash(phase + error_type + root_cause + normalized_lesson_text)`
3. 持久化为 bug case（写入 `regression/failure-library/cases/`），附带 fingerprint
4. 按 fingerprint 去重，且 support 必须来自不同 source signature
5. source signature = `project_id + input_signature`（input_signature = 输入 artifact 文件的 content hash）
6. 按 distinct source signatures 计算 support count

> 注意：不复用 `analyze_failure_patterns()`（它只做 tags/error_type 计数，不是语义聚类器）。
> 新增 `match_by_fingerprint()` 方法在 `skill_reflector.py` 中实现。

> source signature 设计决策：不用 `project_id + run_date`（同项目隔天重跑会刷高 support）。
> 改用 `project_id + input_signature`，只有输入 artifact 真正不同才算新 support。
> input_signature 计算：对 Phase 输入文件（upstream context + profile + SE list）取 SHA256。

> Legacy case 迁移规则：
> - 旧 case 无 input_signature 字段时，不参与 auto-merge support 统计
> - 仅标记为 `legacy_unverified`，可参与 HUMAN_REVIEW 建议但不计入高置信度阈值
> - 后续通过一次性 migration 脚本补充 input_signature（从 case.json 的 source 元数据 derive）
> - migration 前的 legacy case 对 auto-merge 是透明的，不会污染置信度判定
>
> 设计决策：现有 failure-library 的 source 结构不统一（有 JSON 字符串、缺 file_hash 等），
> derive-on-load 会大量退回弱 fallback，导致 support 统计不可靠。
> 宁可让 auto-merge 初期只基于新格式 case 积累，也不让脏数据参与高置信度判定。

阈值判定（复用 `skill_evolution.py` 的 `HIGH_CONFIDENCE_THRESHOLD = 3`）：
- distinct source support >= 3 → 自动合并，跑 verify
- distinct source support < 3 → 生成 `_skill_suggestions_{phase}.md` 等人审

> 设计决策：单次 run 的 3 轮 judge 不够算 support。必须跨 run、跨项目积累，
> 且同一输入重复重跑不会刷高 support count（按 input_signature 去重）。

#### Regression Verify（两层）

**Layer 1: Report Structure Contract Check**（升级）

当前 golden sample 只是历史样本 profile，不是 machine-readable 的章节规范。
升级为 phase_registry 中的 `required_report_sections` 字段，并纳入 phase contract：

```python
# In phase_registry.py, add to each PHASE_DEFS entry:
"A": {
    ...
    "required_report_sections": [
        {"canonical": "需求清单", "aliases": ["REQ/BR 需求清单", "需求列表", "需求点"]},
        {"canonical": "SE 列表", "aliases": ["SE 关键语义清单", "关键语义", "SE List"]},
        {"canonical": "业务规则", "aliases": ["BR 业务规则", "Business Rules"]},
        {"canonical": "Gap 分析", "aliases": ["GAP 缺口清单", "缺口分析", "Gap Analysis"]},
    ],
},
"B": {
    ...
    "required_report_sections": [
        {"canonical": "测试用例清单", "aliases": ["单测用例", "Test Cases"]},
        {"canonical": "覆盖率矩阵", "aliases": ["Coverage Matrix", "覆盖率"]},
        {"canonical": "Mock 策略", "aliases": ["Mock Strategy", "Mock 方案"]},
    ],
},
# ... other phases
```

**Section 匹配规则**（别名归一化）：
- 扫描报告 markdown 的 H2/H3 标题
- 对每个 required section，检查标题是否匹配 canonical 或任一 alias（模糊匹配：包含即可）
- 缺失章节 → FAIL，多余章节 → PASS（允许扩展）

**纳入 Phase Contract**：
- `phase_contract.py` 的 `render_contract_for_judge()` 自动从 PHASE_DEFS 提取
  `required_report_sections` 并写入 `_phase_contract.json` 的 `structure_contract` 字段
- replay/finalize/manual judge 共用同一份 contract 做校验
- 校验逻辑抽为独立函数 `check_report_structure(report_path, phase)` 供三方调用

- golden sample 保留为参考，但不再是 Layer 1 的唯一校验源
- 校验逻辑：扫描报告 markdown 的 H2/H3 标题，匹配 required sections
- 缺失章节 → FAIL，多余章节 → PASS（允许扩展）
- golden sample 保留为参考，但不再是 Layer 1 的唯一校验源

**Layer 2: Holdout Replay Eval**（新增）

当前缺口：仓库没有"带着新 skill 重跑 case"的能力。regression runner（`regression.py`）
只做 actual_dir vs expected snapshot 比对，不会执行 Qualix pipeline。

需要新增 Replay Executor：

```python
# New: src/qualix/tracking/replay_executor.py
class ReplayExecutor:
    """Execute Qualix pipeline on holdout cases with skill override.

    Hard constraints:
    - All output goes to a temporary directory (tempfile.mkdtemp), never to real output/
    - Runs in safe-finalize mode (whitelist), not skip-all-finalize:
      ALLOWED (read-only): schema check, hard_checks, golden compare
      BLOCKED (side-effect): skill_factory, skill_evolution, memory_index,
                             quality_tracking, bug case generation
    - Temp dir is cleaned up after verify completes (success or failure)
    """

    def replay(self, case_dir: str, skill_override: str | None = None) -> ReplayResult:
        """Run a single holdout case through the pipeline in isolation.

        Args:
            case_dir: Path to holdout case (contains input artifacts + expected output)
            skill_override: Path to modified skill file (None = use current)

        Skill override injection:
            Uses resolve_worker_prompt(phase, override) — a new unified entry point
            shared by both ReplayExecutor and production adaptive_loop/dag_scheduler.
            This ensures holdout verification uses the exact same prompt construction
            path as production execution.

            Current gap: cmd_adaptive/cmd_agent_run use read_text() directly,
            dag_scheduler uses load_skill_progressive(). resolve_worker_prompt()
            consolidates both paths and accepts an optional override.

        Isolation guarantees:
            - output_dir = tempfile.mkdtemp(prefix="qualix_holdout_")
            - task_store writes disabled (no _judge_iter*.json, no _adaptive_summary.json)
            - safe-finalize whitelist: only read-only checks run
            - no bug case generation from holdout runs

        Returns:
            ReplayResult with actual output + diff against expected + quality score
        """
        ...
```

Holdout case 格式（新增，存放在 `regression/holdout/`）：
```
regression/holdout/
  phaseA/
    case_001/
      input/          # 输入 artifact（upstream context, profile, SE list）
      expected/       # 期望输出 snapshot
      case.json       # 元数据（phase, description, quality_baseline）
```

**Scoring Contract（质量分数契约）：**

**前置依赖：统一 JudgeRunner**（新增）

当前 Judge 有两套产出路径，schema 不一致：
- `quality/judge.py` → 生成 prompt 等人工执行 → `_judge_result.json`（有 `overall_score`）
- `adaptive_loop.py` → 自动执行 → `JudgeVote` / `_judge_iter*.json`（有 `overall`）

需要新增统一的 JudgeRunner：

```python
# New: src/qualix/quality/judge_runner.py
class JudgeRunner:
    """Unified Judge execution with canonical output schema.

    Serves all three execution modes:
    - manual: generate prompt + accept human result → normalize to canonical schema
    - adaptive: direct backend call → normalize to canonical schema
    - holdout: replay execution → normalize to canonical schema

    Hard constraint: Judge MUST use structured output channel (JSON mode /
    response_format / schema-enforced) when calling LLM directly.
    Prompt-only JSON formatting is insufficient — model can return tool_call-like
    or non-JSON content on long reports.
    """

    # Canonical output schema — wire-compatible with existing _judge_result.json
    # dimensions 保持数组形态（与现有消费方兼容）：
    #   phase.py 遍历维度列表回写 state
    #   bug_case_generator.py 依赖每个维度的 id/score/issues
    #   judge.py 人工结果模板也是数组
    CANONICAL_SCHEMA = {
        "overall_score": float,      # 1-5 Likert, normalized (兼容 overall → overall_score)
        "dimensions": list,          # [{id, name, score, weight, rationale, issues}]
        "issues": list,              # [{severity, description, evidence}] — 从 dimensions 聚合
        "verdict": str,              # PASS | FAIL | PASS_WITH_CONCERNS
        "raw_output": str,           # preserved for guard layer
        "_schema_version": int,      # 1 = current, for future migration
    }

    # normalize() 负责：
    # - overall → overall_score 归一化
    # - dimensions dict → list 转换（如果 adaptive 输出是 dict 形态）
    # - 保持 dimensions[].id/score/issues 结构不变（兼容 bug_case_generator）
    # - 聚合 dimensions[].issues → 顶层 issues（新增，不破坏旧字段）

    def run(self, phase, report_path, output_dir, model, *,
            warning_override=None, structured_output=True) -> JudgeResult:
        """Execute Judge with structured output enforcement."""
        ...

    def normalize(self, raw_result: dict) -> JudgeResult:
        """Normalize any Judge output variant to canonical schema.

        Wire-compatible: existing consumers of _judge_result.json
        (phase.py, bug_case_generator.py) can read normalized output
        without any code changes.
        """
        ...
```

> 设计决策：canonical schema 保持对现有 `_judge_result.json` 的线兼容。
> dimensions 保持数组形态（不改为 dict），issues 作为新增聚合字段追加。
> 现有消费方（phase.py / bug_case_generator.py / judge.py 人工模板）无需修改。
> 新增 `_schema_version` 字段为未来 migration 预留。

**Judge 结构化输出硬约束**（新增设计约束）：

当前 adaptive 的 direct backend 调用是普通 chat，靠正则 + 花括号切片做 JSON 解析。
这是 Judge 基础设施不可靠的根因。

**Backend 扩展点**（新增）：

当前 `src/qualix/agents/llm_backends.py` 暴露的是通用 `chat(messages, **kwargs)`，
Anthropic/OpenAI/Gemini 实现都没有承接 response_format / JSON mode 参数。

需要扩展 backend 接口：

```python
# Modified: src/qualix/agents/llm_backends.py

@dataclass
class StructuredChatResult:
    """Return type for chat_structured — preserves raw text for guard/audit."""
    parsed: dict           # schema-validated parsed result
    raw_text: str          # original provider response text (for RationalizationGuard)
    provider_meta: dict    # model, latency, token counts, etc.

class LLMBackend:
    def chat(self, messages, **kwargs) -> str:
        """Existing: general chat completion."""
        ...

    def chat_structured(self, messages, response_schema: dict, **kwargs) -> StructuredChatResult:
        """New: structured output with schema enforcement.

        Implementation per backend:
        - OpenAI-compatible: response_format={"type": "json_object"} + schema
        - Anthropic: tool_use with single tool matching schema
        - Fallback: prompt JSON + strict validation + 1 retry
        """
        ...
```

JudgeRunner 通过 `chat_structured()` 调用 backend，不绕开现有抽象层。

设计硬约束：
- JudgeRunner 调用 LLM 时必须使用 `chat_structured()` 通道
- 优先级：`response_format=json_object` > `tool_use` with schema > prompt-only JSON
- 如果 backend 不支持 structured output（如某些 deepseek 版本），fallback 为
  prompt JSON + 严格 JSON 校验 + 最多 1 次 retry with "请只输出 JSON" 追加提示
- 解析失败不再折叠为 FAIL/0 分，而是标记为 `INFRA_FAILURE`（与 Judge Health Gate 对齐）

单 case 质量分数：
- score producer = JudgeRunner（统一入口，canonical schema）
- 取 canonical schema 的 `overall_score` 字段（1-5 Likert scale）
- JudgeRunner.normalize() 负责处理 `overall` vs `overall_score` 等变体

Suite 聚合：
- suite_score = mean(所有 holdout case 的 overall_score)
- 回归判定：suite_score < baseline_suite_score * 0.95（下降超 5%）
- 单 case 回归判定：任一 case 的 overall_score < case.quality_baseline * 0.90（下降超 10%）
- 两个条件任一触发 → 视为回归

Baseline 来源：
- 每条 holdout case 的 `case.json` 中记录 `quality_baseline`（首次创建时用 JudgeRunner 跑一次得到）
- `regression/holdout/suite_baseline.json` 记录 suite 级 baseline_suite_score

- 预置 3-5 条 holdout case（从历史高质量执行中提取）
- 每条 case 包含完整输入 + 期望输出 snapshot + 质量基线分数
- Replay Executor 通过 resolve_worker_prompt(phase, override) 注入修改后的 skill
- 质量分数下降超过阈值 → 视为回归

> 设计决策：不复用 regression/golden（只有 profile，没有 runnable input）。
> 不复用 failure-library（知识库条目，不可回放）。
> 新建 regression/holdout 目录，专门存放可回放的 holdout case。

> 数据质量注意：现有 case 库中 holdout 字段有 bool 和字符串 "False" 混用
> （如 phaseB/FEISHU-d654afbc/case.json），load 时需统一规范化为 bool。

**新增统一入口：`resolve_worker_prompt()`**

```python
# New function in src/qualix/context/skill_loader.py
def resolve_worker_prompt(phase: str, skill_override: str | None = None) -> str:
    """Unified skill resolution for ALL execution paths.

    Consolidates (all callers must migrate to this function):
    - src/qualix/commands/agents.py (cmd_agent_run): currently read_text() directly
    - src/qualix/commands/adaptive.py (cmd_adaptive): currently read_text() directly
    - src/qualix/agents/agent_orchestrator.py (dag_scheduler): currently load_skill_progressive()
    - src/qualix/tracking/replay_executor.py (holdout): new caller

    Args:
        phase: Phase identifier (e.g., "A", "B", "C")
        skill_override: Optional path to override skill file (Path or str)

    Returns:
        Resolved skill content string
    """
    # Step 1: resolve phase → skill_path from PHASE_DEFS (authoritative source)
    # PHASE_DEFS[phase]["skill"] is the canonical path, SKILL_FILE_MAP is fallback only
    from qualix.core.phase_registry import PHASE_DEFS
    skill_path = Path(PHASE_DEFS[phase]["skill"])

    # Step 2: override replaces SKILL.md path but still goes through progressive loader
    if skill_override:
        skill_path = Path(skill_override)

    # Step 3: load through progressive loader (handles SKILL.md + references/)
    # load_skill_progressive() expects Path and calls .exists() internally
    return load_skill_progressive(skill_path, phase)
```

> 设计决策：
> - 以 `PHASE_DEFS[phase]["skill"]` 为主（authoritative），`SKILL_FILE_MAP` 仅作 fallback
> - override 不能直接 read_text()（会绕过 progressive skill 解析，
>   导致 references/ 不加载，replay 与 production prompt 不一致）
> - override 只替换 SKILL.md 路径，仍走 load_skill_progressive() 完整流程
> - skill_path 统一为 Path 类型（load_skill_progressive 内部调用 .exists()）

**生产调用方迁移清单**（必须全部切到 resolve_worker_prompt）：

| 文件 | 当前调用方式 | 迁移动作 |
|------|-------------|---------|
| `src/qualix/commands/agents.py` | `read_text()` 直接读 skill（含 cmd_adaptive） | 替换为 `resolve_worker_prompt(phase)` |
| `src/qualix/agents/dag_scheduler.py` | `load_skill_progressive(path, phase)` | 替换为 `resolve_worker_prompt(phase)` |
| `src/qualix/tracking/replay_executor.py` | 新代码 | 直接用 `resolve_worker_prompt(phase, override)` |

> 注意：`src/qualix/commands/adaptive.py` 不存在，cmd_adaptive 实际在 `commands/agents.py` 中。
> `src/qualix/agents/agent_orchestrator.py` 不是 DAG 调用点，真实调用在 `dag_scheduler.py`。

**Rollback 策略：Patch-Level Transactional Rollback**
- 写入前对目标文件做 `git stash`-style 快照（保存 original content + file path）
- verify 失败时精确还原每个被修改的文件（不影响并发修改的其他文件）
- rollback 后记录 revert 原因到 evolution lineage，降级为人审

#### New File: `src/qualix/tracking/skill_reflector.py`

```python
"""Reflect→Write→Verify loop for automatic skill evolution."""

class SkillReflector:
    """Analyzes adaptive loop failures and auto-evolves skill rules."""

    def __init__(self, phase: str, project_id: str):
        self.phase = phase
        self.project_id = project_id

    def reflect(self, judge_results: list[dict]) -> ReflectResult:
        """Analyze 3 rounds of judge results, extract repeated failure patterns.

        Returns:
            ReflectResult with root_cause, failure_patterns, suggested_changes
        """
        ...

    def write(self, reflect_result: ReflectResult) -> WriteResult:
        """Apply changes based on root_cause type and confidence level.

        High confidence (case_support >= 3): auto-apply
        Low confidence: generate suggestion file for human review
        """
        ...

    def verify(self, write_result: WriteResult) -> VerifyResult:
        """Run regression eval against golden cases.

        PASS: commit changes, record evolution lineage
        FAIL: revert changes, downgrade to human review
        """
        ...

    def reflect_and_write(self, judge_results: list[dict]) -> EvolutionOutcome:
        """Full Reflect→Persist→Cluster→Write→Verify pipeline."""
        reflect_result = self.reflect(judge_results)
        if not reflect_result.actionable:
            return EvolutionOutcome(action="SKIP", reason="No actionable pattern found")

        # Persist failure as bug case first, then cluster with history
        case_id = self.persist_as_bug_case(reflect_result)
        support_count = self.cluster_and_count_support(case_id)

        write_result = self.write(reflect_result, support_count)
        if write_result.mode == "HUMAN_REVIEW":
            return EvolutionOutcome(action="HUMAN_REVIEW", suggestion_path=write_result.path)

        # Patch-level transactional rollback: snapshot before write
        snapshot = self.snapshot_targets(write_result.target_files)
        self.apply_changes(write_result)

        verify_result = self.verify(write_result)
        if verify_result.regressed:
            self.rollback(snapshot)
            return EvolutionOutcome(action="REVERTED", reason=verify_result.revert_reason)

        return EvolutionOutcome(action="AUTO_MERGED", changes=write_result.changes)
```

#### Modified: `src/qualix/agents/adaptive_loop.py`

在 `run_adaptive_loop()` 的 max_iterations 耗尽分支中新增：

```python
# After all iterations exhausted with FAIL
if all_failed and iteration == max_iterations:
    reflector = SkillReflector(phase=self.phase, project_id=self.project_id)
    evolution_outcome = reflector.reflect_and_write(judge_results=all_judge_results)
    summary["skill_evolution"] = evolution_outcome.to_dict()
```

#### Modified: `src/qualix/tracking/skill_evolution.py`

新增 `auto_apply_suggestions()` 方法：

```python
def auto_apply_suggestions(self, suggestions: list[SkillSuggestion], skill_path: str) -> ApplyResult:
    """Apply high-confidence suggestions directly to skill file.

    Reads current skill content, applies changes at correct insertion points,
    writes back. Returns ApplyResult with before/after diff.
    """
    ...
```

---

## Feature 2: Anti-Rationalization 运行时强制

### Problem

Anti-Rationalization Table（8 条放水借口 + 反驳）嵌入 Judge prompt，靠 LLM 自觉遵守。
AgentSpec 证明运行时约束可达 90%+ 阻止率。Qualix 需要从"劝说型"升级为"强制型"。

### Design

#### Two-Layer Detection

```
Judge Output
  └─ Layer 1: Keyword Scan (regex, 0 cost)
       ├─ No match → PASS (accept judge output)
       └─ Match → Layer 2: LLM Confirmation (haiku-level model)
            ├─ false_positive → PASS
            └─ confirmed → BLOCK (reject + re-judge)
```

#### Layer 1: Keyword Patterns

从现有 8 条放水借口提取核心模式，存入 `constants.py`：

```python
RATIONALIZATION_PATTERNS = [
    r"虽然.{0,20}但.{0,20}(可以接受|尚可|足够)",
    r"(基本|整体|总体).{0,10}(清晰|达标|合格|可接受)",
    r"考虑到.{0,15}(时间|复杂度|限制)",
    r"影响不大",
    r"已经(有了?|存在).{0,10}(改进|提升)",
    r"覆盖率.{0,5}达标",
    r"(不需要|没必要).{0,10}(边界|并发|异常)",
    r"上一轮已经",
]
```

#### Layer 2: LLM Confirmation

仅在 Layer 1 命中时触发，用轻量模型判定：

```python
RATIONALIZATION_CONFIRM_PROMPT = """
你是质量审计员。以下是 Judge 评审中被标记的段落：

{matched_text}

上下文：
{surrounding_context}

判断这段话是否在"放水"（降低标准、找借口通过、回避问题）：
- 如果是合理的上下文描述或客观陈述，回答 FALSE_POSITIVE
- 如果是在降低标准或找借口，回答 CONFIRMED

只回答 FALSE_POSITIVE 或 CONFIRMED，不要解释。
"""
```

#### Block Action

confirmed 时：
1. 拒绝该 Judge 输出
2. 不消耗 adaptive loop 迭代预算（重审是 guard 层子循环，不占用 worker 改进机会）
3. 最多重审 `RATIONALIZATION_MAX_REJUDGE = 1` 次（防止无限循环）
4. 重新调用 Judge，prompt 中注入警告：

```python
REJUDGE_WARNING = """
⚠️ 你上一轮的评审被检测到以下放水信号：
{detected_patterns}

请严格按照评审标准重新评估，不要降低标准。
宁可多报不可漏报（FN 比 FP 更严重）。
"""
```

#### New File: `src/qualix/quality/rationalization_guard.py`

```python
"""Runtime anti-rationalization enforcement layer."""

@dataclass
class GuardResult:
    passed: bool
    detected_patterns: list[str]  # matched keyword patterns
    confirmed_rationalizations: list[str]  # LLM-confirmed segments
    action: str  # "PASS" | "BLOCK_AND_REJUDGE"

class RationalizationGuard:
    """Two-layer detection: keyword scan + LLM confirmation."""

    def __init__(self, confirm_model: str = None):
        self.patterns = [re.compile(p) for p in RATIONALIZATION_PATTERNS]
        self.confirm_model = confirm_model or DEFAULT_RATIONALIZATION_CONFIRM_MODEL

    def scan_keywords(self, judge_output: str) -> list[KeywordMatch]:
        """Layer 1: Zero-cost regex scan against known patterns."""
        ...

    def confirm_with_llm(self, matches: list[KeywordMatch], judge_output: str) -> list[ConfirmResult]:
        """Layer 2: Lightweight LLM confirmation for keyword hits."""
        ...

    def check(self, judge_output: str) -> GuardResult:
        """Full two-layer check pipeline."""
        matches = self.scan_keywords(judge_output)
        if not matches:
            return GuardResult(passed=True, detected_patterns=[], confirmed_rationalizations=[], action="PASS")

        confirmations = self.confirm_with_llm(matches, judge_output)
        confirmed = [c for c in confirmations if c.verdict == "CONFIRMED"]

        if not confirmed:
            return GuardResult(passed=True, detected_patterns=[m.pattern for m in matches],
                             confirmed_rationalizations=[], action="PASS")

        return GuardResult(passed=False, detected_patterns=[m.pattern for m in matches],
                          confirmed_rationalizations=[c.text for c in confirmed],
                          action="BLOCK_AND_REJUDGE")
```

#### Modified: `src/qualix/agents/adaptive_loop.py`

变更点 1 — `_run_single_judge()` 收口为 JudgeRunner 的 thin wrapper：

```python
# _run_single_judge() becomes a thin wrapper around JudgeRunner
def _run_single_judge(self, output_dir, report_path, rubric, model, fallback,
                      warning_override=None) -> JudgeVote:
    """Thin wrapper: delegates to JudgeRunner, handles round orchestration."""
    runner = JudgeRunner()
    result = runner.run(
        phase=self.phase, report_path=report_path,
        output_dir=output_dir, model=model, fallback=fallback,
        warning_override=warning_override,
    )
    # result is JudgeResult (canonical schema)
    # result.raw_output comes from StructuredChatResult.raw_text
    vote = JudgeVote(
        score=result.overall_score,
        verdict=result.verdict,
        dimensions=result.dimensions,
        raw_output=result.raw_output,  # preserved for guard layer
        health=result.health,          # HEALTHY | INFRA_FAILURE
    )
    return vote
```

> 设计决策：`_run_single_judge()` 不再自己拼 prompt 和解析 JSON。
> 所有 Judge 执行统一走 JudgeRunner → chat_structured() → canonical schema。
> 本地 helper 只保留 warning 注入和 round orchestration 职责。
> 这样 structured output、INFRA_FAILURE 归类、canonical schema 都真正落到运行链路。

**JudgeRunner.run() fallback 契约**：

```python
def run(self, phase, report_path, output_dir, model, fallback=None, *,
        warning_override=None) -> JudgeResult:
    """Execute Judge with primary→fallback model chain.

    Fallback semantics (preserving existing adaptive behavior):
    - Try primary model first via chat_structured()
    - If primary returns INFRA_FAILURE (parse fail, model refuse, timeout):
      retry with fallback model (if provided)
    - Only if BOTH primary and fallback fail → result.health = INFRA_FAILURE
    - If primary succeeds → result.health = HEALTHY (regardless of score)
    """
    ...
```

> 设计决策：fallback 是 JudgeRunner 的正式契约参数，不由调用方各自补。
> INFRA_FAILURE 只在 primary + fallback 都失败时才标记。

变更点 2 — Guard 插入点（按 round 生效，不是按 vote）：

Guard 在 primary judge 输出后、进入 secondary validation 前触发。

```python
# After primary judge produces output, before secondary validation
guard = RationalizationGuard()
guard_result = guard.check(primary_vote.raw_output)  # raw_output from StructuredChatResult

if not guard_result.passed:
    # Does NOT consume adaptive loop iteration budget
    # Guard re-judge is a sub-loop, max RATIONALIZATION_MAX_REJUDGE times
    warning_text = format_rejudge_warning(guard_result)
    # Re-invoke through same JudgeRunner path
    primary_vote = self._run_single_judge(
        output_dir=output_dir, report_path=report_path,
        rubric=rubric, model=model, fallback=fallback,
        warning_override=warning_text,
    )
    # Check re-judged output again
    guard_result_2 = guard.check(primary_vote.raw_output)
    if not guard_result_2.passed:
        # Guard budget exhausted, still rationalization detected
        # Mark as GUARD_EXHAUSTED — do NOT send to secondary validation
        primary_vote.health = "GUARD_EXHAUSTED"
        primary_vote.verdict = "INVALID"
        # This vote is excluded from valid_votes in consensus
        # Falls through to judge_health_check → triggers manual judge fallback

# Only proceed to secondary validation if primary vote is valid
if primary_vote.health == "HEALTHY":
    # Then proceed to secondary validation as normal
    ...
```

**Guard 预算耗尽终态**（显式定义）：

| 场景 | 终态 | 后续动作 |
|------|------|---------|
| 重审通过 guard | HEALTHY | 正常进入 secondary validation |
| 重审仍命中 guard（预算耗尽） | GUARD_EXHAUSTED | 该票标记 INVALID，不计入 valid_votes |
| GUARD_EXHAUSTED 导致 valid_votes 不足 | → INFRA_FAILURE | 触发 manual judge fallback（不进入 reflect） |

> 设计决策：guard 预算耗尽后绝不 fail-open（不把已知放水的票送去 consensus）。
> 也不折叠为 FAIL/0 分（会污染 judge_health 和 skill evolution）。
> 而是标记为 GUARD_EXHAUSTED/INVALID，让 judge_health_check 自然降级为 manual judge。

> 设计决策：guard 按 round 生效，拦截 primary judge output。
> 通过 guard 后才进入 secondary validation + consensus 流程。
> 不对每个 secondary vote 单独 guard（secondary 是独立评审，不受 primary 放水影响）。

#### Modified: `src/qualix/quality/judge.py`

新增重审 prompt 模板 `REJUDGE_WARNING`（见上文）。

#### Modified: `src/qualix/constants.py`

新增：
```python
# Anti-Rationalization Runtime Enforcement
RATIONALIZATION_PATTERNS = [...]  # 8+ regex patterns
DEFAULT_RATIONALIZATION_CONFIRM_MODEL = "claude-haiku-4-5-20251001"
RATIONALIZATION_MAX_REJUDGE = 1  # 最多因放水重审 1 次（防止无限循环）
```

---

## File Change Summary

| File | Action | Feature | Review 修正 |
|------|--------|---------|------------|
| `src/qualix/tracking/skill_reflector.py` | NEW | Skill Evolution | persist→cluster→write + patch rollback + fingerprint + judge health gate |
| `src/qualix/tracking/replay_executor.py` | NEW | Skill Evolution | holdout replay with isolation + safe-finalize whitelist |
| `src/qualix/quality/rationalization_guard.py` | NEW | Anti-Rationalization | — |
| `src/qualix/quality/judge_runner.py` | NEW | Both | 统一 Judge 执行 + canonical schema + structured output |
| `src/qualix/agents/adaptive_loop.py` | MODIFY | Both | _run_single_judge 收口为 JudgeRunner wrapper + guard |
| `src/qualix/agents/llm_backends.py` | MODIFY | Both | 新增 chat_structured() → StructuredChatResult |
| `src/qualix/tracking/skill_evolution.py` | MODIFY | Skill Evolution | — |
| `src/qualix/quality/judge.py` | MODIFY | Anti-Rationalization | — |
| `src/qualix/constants.py` | MODIFY | Both | CONTEXT/SCHEMA 不纳入 auto-merge |
| `src/qualix/context/skill_loader.py` | MODIFY | Skill Evolution | 新增 resolve_worker_prompt() 统一入口 |
| `src/qualix/core/phase_registry.py` | MODIFY | Skill Evolution | required_report_sections（含别名） |
| `src/qualix/runtime/phase_contract.py` | MODIFY | Skill Evolution | 纳入 structure_contract 字段 |
| `src/qualix/commands/agents.py` | MODIFY | Skill Evolution | 迁移到 resolve_worker_prompt()（含 cmd_adaptive） |
| `src/qualix/agents/dag_scheduler.py` | MODIFY | Skill Evolution | 迁移到 resolve_worker_prompt() |
| `regression/holdout/` | NEW DIR | Skill Evolution | 可回放 holdout case + suite_baseline.json |

## Review 决策记录

| Round | Issue | Severity | Resolution |
|-------|-------|----------|------------|
| R1 | CONTEXT/SCHEMA 不能 auto-merge | P0 | v1 只允许 SKILL_RULE 自动进化 |
| R1 | golden verify 不验语义 | P1 | 新增 holdout semantic eval 层 |
| R1 | support count 来源不明 | P1 | 先持久化为 bug case → 跨 run 聚类 → 按 distinct cases 算 |
| R1 | raw judge output 被丢弃 | P1 | adaptive_loop 在 parse 前保存 raw_output |
| R1 | guard 按 vote 还是 round | P2 | 按 round，拦截 primary judge，通过后才进 secondary |
| R2 | holdout 没有可回放载体 | P1 | 改用 golden cases 做固定 holdout suite |
| R2 | confidence gate 被重复重跑刷高 | P1 | fingerprint dedupe + source signature 去重 |
| R2 | re-judge API 不对齐 | P2 | `_run_single_judge()` 新增 `warning_override` 参数 |
| R2 | holdout 字段 bool/str 混用 | data | load 时统一规范化为 bool |
| R3 | holdout 仍无 replay engine | P1 | 新增 `replay_executor.py` + `regression/holdout/` 目录 |
| R3 | source signature 太弱 | P1 | 改为 `project_id + input_signature`（artifact content hash） |
| R4 | holdout replay 缺隔离执行 | P1 | 临时 output_dir + no-side-effect mode（禁用学习/沉淀 handler） |
| R4 | legacy case 迁移不可靠 | P2 | legacy case 不参与 auto-merge support，标记 `legacy_unverified` |
| R5 | no-side-effect 跳过了 Layer 1 校验 | P1 | 改为 safe-finalize whitelist（保留只读 check，禁用副作用 handler） |
| R5 | skill_override 没对齐现有解析入口 | P1 | 新增 `resolve_worker_prompt()` 统一入口，所有路径共用 |
| R5 | 质量分数契约未定义 | P2 | 补 scoring contract：overall_score 字段 + suite/case 双阈值 |
| R6 | FAIL 不区分语义失败和基础设施失败 | P1 | 新增 Judge Health Gate + manual judge fallback 入口 |
| R6 | holdout 没有统一 Judge producer | P1 | 新增 JudgeRunner 统一 manual/adaptive/holdout 三条路径 |
| R6 | Judge 缺结构化输出硬约束 | P1 | JudgeRunner 强制 structured output，解析失败标记 INFRA_FAILURE |
| R6 | resolve_worker_prompt 与生产路径不等价 | P2 | override 走 load_skill_progressive() 完整流程 |
| R6 | Layer 1 不是 machine-readable contract | P2 | phase_registry 新增 required_report_sections 字段 |
| R7 | canonical schema 打破现有消费链 | P1 | dimensions 保持数组形态 + _schema_version + 线兼容 |
| R7 | structured output 缺 backend 落点 | P1 | llm_backends.py 新增 chat_structured() 方法 |
| R7 | resolve_worker_prompt 与生产路径不等价 | P1 | 以 PHASE_DEFS 为主 + Path 类型 + 4 个调用方迁移清单 |
| R7 | required_report_sections 未纳入 contract | P2 | 写入 phase_contract + 别名归一 + check_report_structure() |
| R8 | chat_structured() 丢失 raw_output | P1 | 返回 StructuredChatResult(parsed, raw_text, provider_meta) |
| R8 | adaptive re-judge 未收口到 JudgeRunner | P1 | _run_single_judge 改为 JudgeRunner.run() 的 thin wrapper |
| R8 | 迁移清单指错真实调用方 | P1 | 修正为 commands/agents.py + dag_scheduler.py，删除不存在的文件 |
| R9 | JudgeRunner 丢失 fallback 语义 | P1 | fallback 纳入 JudgeRunner.run() 正式契约，双失败才 INFRA_FAILURE |
| R9 | Guard 预算耗尽终态未定义 | P1 | GUARD_EXHAUSTED → INVALID，不计入 valid_votes，降级 manual judge |

## Out of Scope

- Phase Contract DSL 化（现有 `hard_checks` 结构够用）
- Adaptive loop 终止条件改为基于约束（保持 max 3 iterations + 放水重审预算）
- 成功轨迹提取（P1，后续迭代）
