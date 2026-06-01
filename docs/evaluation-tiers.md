# Qualix 评估 / 评分线梳理

> 2026-05-10 创建。系统快照，会随代码漂移——修代码时请同步更新本文件或用 `gitnexus_detect_changes` 验证后刷新。

Qualix 评估机制按"从硬门槛到元评分"分 8 个 Tier，层层叠加。本文档按 Tier 列出所有组件、文件路径和作用，附使用场景提示。

## 层级概览

| Tier | 组件数 | 覆盖范围 | 成本 |
|------|-------|---------|------|
| T1 确定性检查 | 13 | 零 LLM 硬门槛 | 0 token |
| T2 Guardrail | 8 | finalize 批量并发 | 0 token |
| T3 LLM 评审 | 10 | Judge / Critique / Preference / Review Chain | 主要 token 开销 |
| T4 Guard 守卫 | 6 | Judge 结果的放水 / 过严 / 死循环守卫 | 轻量 LLM（haiku 级） |
| T5 Gate 汇总 | 4 | 统一 HARD/SOFT 卡控 | 0 token |
| T6 趋势 / 回归 | 11 | 跨运行 + 跨项目 | 0 token（统计） |
| T7 前置决策 | 5 | risk → depth / confidence / trust | 0 token |
| T8 Skill Evolution | 7 | 元评分 / absorb 闭环 | 中等 LLM（分类 + 校准） |
| **合计** | **~64** | 8 层叠加 | — |

---

## Tier 1 — 确定性检查（零 LLM、二值判定）

回答"产物格式对不对、字段在不在、数字达不达标"。

| 组件 | 文件 | 判定 |
|------|------|------|
| Phase Contract hard_checks | `runtime/phase_contract.py` | `_get_hard_checks()` 每 Phase 必填字段/结构约束，fail 即 BLOCKED |
| Schema 校验 | `schemas/phase_q01..q07.py` | Pydantic，fail_closed（错误列表而非 None） |
| AutoChecks | `quality/checks/auto_checks.py::auto_derive_checks` | schema + phase_registry 自动推导：合规 / 交叉引用 / 严重等级 / RSM 覆盖率 |
| Cross-Phase 交叉引用 | `quality/checks/cross_phase_check.py::check_cross_phase_refs` | Q06 审计的 EUT 必须在 Q05a 存在等 |
| Compile check | `quality/checks/compile_check.py` | Q05b 代码真编译（maven/gradle/go） |
| Coverage gate | `quality/checks/coverage_gate.py` | JaCoCo 解析，line/branch ≥ 80%；blast radius 内优先增量 |
| Rule compliance | `quality/rules/rule_compliance.py::compute_rule_compliance` | 11 条规则逐条检测 |
| Report quality checks | `quality/checks/report_quality_checks.py` | 来源标注 / ID 格式 / GAP 风险 / OPEN 决策方等 6 项正则 |
| Requirement smell | `quality/checks/requirement_smell.py` | 5 类异味 VAGUE / INCOMPLETE 等正则 |
| Requirement graph | `quality/checks/requirement_graph.py` | REQ→BR→SE networkx 图，5 类异常检测 |
| Demand trace + code skeleton | `quality/checks/demand_trace.py` / `code_skeleton.py` | SE→入口方法→调用链 + TREEFRAG 代码骨架 |
| Q05a structure check | `quality/checks/q05_structure_checks.py` | mock_wrong / phantom_method / eut_missing_se 等 |
| Weak assert gate | `runtime/handlers/handlers_detection.py` + `languages/**/assertions.py` | tree-sitter AST 弱断言识别，high-risk ≥ 1 BLOCKED |
| Mock coincidence | `runtime/handlers/handlers_detection.py::handle_mock_coincidence_check` | 固定返回 / 硬编码关键词扫描 |

**输出**：结果进 `verification_bundle.json`，作为 Tier 2/3 的 evidence。

---

## Tier 2 — Guardrail 层（finalize 批量并发执行）

统一接口 `PhaseGuardrail`（`quality/guardrail/guardrail.py`），并发执行后写入 `_internal/_guardrail_results.json`。

| Guardrail | 文件 | 级别 | 作用 |
|-----------|------|------|------|
| `finalize_checks` | `guardrail_impl.py::FinalizeChecksGuardrail` | BLOCKED | 包装 Tier 1 硬检查结果 |
| `phase_constraints` | `guardrail_impl.py::PhaseConstraintsGuardrail` | BLOCKED | 包装 phase_contract 约束 |
| `rule_compliance` | `guardrail_impl.py::RuleComplianceGuardrail` | WARNING | 11 条规则合规度 |
| `report_semantic` | `semantic_guardrail.py::ReportSemanticGuardrail` | BLOCKED/WARNING | BR 概括性 / 覆盖度虚高 / 跨 Phase 越权 / P0 未闭环 |
| `output_completeness` | `output_completeness.py` | BLOCKED | 报告截断检测 + 最小长度 |
| `fabrication_detector` | `fabrication_detector.py` | BLOCKED | 虚构字段 / 编造引用 |
| `q05_branch_coverage` | `q05_branch_coverage.py` | WARNING | Q05a 分支覆盖校验 |
| `rationalization_probe_structured` | `rationalization_probe.py` | WARNING | Q03/Q06 结构化字段级放水词扫描 |

---

## Tier 3 — LLM 语义评审（主力评分机制）

| 组件 | 文件 | 作用 |
|------|------|------|
| JudgeRunner（统一入口） | `quality/judge/judge_runner.py` | canonical schema + primary→fallback 模型链 + structured output 硬约束 |
| Multi-Judge 投票 | `agents/judge_vote.py::multi_judge_vote` | Primary + boundary 区间触发 secondary，verdict 共识 + 均分 |
| Judge rubric（组装） | `quality/judge/judge_rubrics.py::compose_rubric_layered` | Shared(40%) + Routed(60%) + Dynamic 维度，按 Phase 路由 |
| Rubric data | `quality/judge/_rubric_data.py::JUDGE_RUBRICS` | 每 Phase 的具体 1-5 Likert 评分维度 |
| Dynamic dimensions | `quality/judge/dynamic_rubric.py::generate_dynamic_dimensions` | Q01 按 SE 类型分布追加评审维度 |
| Judge 结果合成 | `quality/judge/judge.py::synthesize_judge_result` | rubric + verification_bundle 合成 Judge prompt |
| Critique | `quality/judge/critique.py::write_critique_prompt` | 可执行反馈（target_id + action + patch + confidence） |
| Preference | `quality/judge/critique.py::write_preference_prompt` | RLAIF 风格偏好对比 |
| Review Chain | `quality/judge/review_chain.py::write_review_chain_prompt` | 链式审阅（worker → judge → critique → fixer） |
| Verification Bundle | `quality/regression/verification_bundle.py` | 把 Tier 1 证据打包给 Judge 当 evidence |

---

## Tier 4 — Guard 守卫层（Judge 结果的二次守卫）

| 组件 | 文件 | 作用 |
|------|------|------|
| RationalizationGuard | `quality/judge/rationalization_guard.py::RationalizationGuard` | Judge 放水两层检测（regex + LLM 确认），重审预算 1 次，`GUARD_EXHAUSTED → HARD_BLOCK` |
| OvercorrectionGuard | `quality/judge/rationalization_guard.py::OvercorrectionGuard` | Judge 过严信号 + FAIL 缺行号证据检测 |
| Anti-Rat section 嵌入 | `quality/judge/_rubric_data.py::ANTI_RATIONALIZATION_SECTION` | Judge prompt 里的劝说层（8 条放水借口 + 反驳） |
| Guard telemetry | `quality/judge/guard_telemetry.py` | LAYER1_HIT / REJUDGE_PASSED / GUARD_EXHAUSTED + before/after pair 落盘 |
| LoopHealthMonitor | `agents/loop_health.py` | adaptive loop 3 维死循环检测：score stagnation / issue repetition / infra failure streak |
| judge_health_check | `agents/judge_vote.py::judge_health_check` | SEMANTIC_FAIL vs INFRA_FAILURE 区分 |

**数据流**：Guard block → telemetry jsonl + before/after pair → T6 Guard precision 周报聚合。

---

## Tier 5 — Gate 汇总层（统一卡控）

| 组件 | 文件 | 作用 |
|------|------|------|
| GateVerdict | `runtime/gate_verdict.py::GateVerdict` | 汇总 handler errors + guardrail + phase_constraints 成单一 verdict |
| CheckItem 分级 | `runtime/gate_verdict.py::CheckItem` | HARD / SOFT，HARD 不可 `--force` 绕过 |
| Upstream hash staleness | `runtime/gate_verdict.py::GateVerdict.is_stale` | 上游产物 MD5 比对，上游变更标 stale |
| cmd_approve 决策 | `commands/approve.py` | 优先读 `_gate_verdict.json`，HARD 拦截 + SOFT 可 force |

---

## Tier 6 — 趋势 / 基线 / 回归层（跨运行 + 跨项目）

| 组件 | 文件 | 作用 |
|------|------|------|
| Eval baseline | `quality/eval/eval_baseline.py::compare_with_baseline` | Phase 级指标基线对比，REGRESSION_THRESHOLD=5% + 经验尾部检验 |
| Eval metric runs | `quality/eval/eval_baseline.py::PHASE_METRICS` | 每 Phase 7-8 个固定指标（REQ 数量、GAP 闭环率、覆盖率等） |
| Eval holdout | `quality/eval/eval_holdout.py::validate_against_holdout` | bug case 分布 + suggestion 覆盖，三条件 overfitting 检测 |
| Score calibration | `quality/judge/score_calibration.py` | 评分趋势监控（通胀/通缩）；DeepEval 校准已禁用（见 ROADMAP） |
| Behavioral fingerprint | `quality/eval/behavioral_fingerprint.py::BehavioralFingerprint` | trajectory 工具调用模式 / ID 数量 / 输出长度，PASS/FAIL/INCONCLUSIVE 三态 |
| Regression runner | `tracking/regression.py` + `commands/ops.py::cmd_regression` | 基线样例回放 + 失败样例库趋势 |
| Prompt eval | `tracking/prompt_eval.py::PromptEvalExecutor` | Q05a/Q06 curated test case，不同 prompt 版本 A/B |
| Rule impact | `tracking/rule_impact.py` | 规则变更 → 指标变化归因 |
| Bug case library | `regression/failure-library/` + `tracking/bug_cases.py` | 失败案例库（2000+ 条）+ fingerprint 聚类 |
| Observability anomalies | `reporting/observability_anomalies.py::detect_metric_anomalies` | Z-score 指标异常检测 |
| Guard precision 周报 | `reporting/guard_precision_report.py` | Guardrail + Guard telemetry 合并周报 |

---

## Tier 7 — 前置决策层（指导评分力度）

| 组件 | 文件 | 作用 |
|------|------|------|
| Blast radius risk score | `quality/checks/blast_radius.py::compute_risk_score` | LOW/MEDIUM/HIGH/CRITICAL，驱动 adaptive loop 深度 |
| REVIEW_DEPTH_CONFIG | `constants.py` | risk_tier → max_iterations / force_secondary / skip_critique |
| Confidence decay | `memory/confidence_decay.py` | Correction 365d / Preference 90d / Fact 30d 半衰期 |
| Trust level | `memory/trust_level.py::TRUST_WEIGHT` | 项目信任标量 |
| Confidence tagging | Phase schema 的 `confidence` 字段 | EXTRACTED / INFERRED / AMBIGUOUS 三级 |

---

## Tier 8 — Skill Evolution 元评分 / 自改进

| 组件 | 文件 | 作用 |
|------|------|------|
| SkillReflector | `tracking/skill_reflector.py` | 失败模式 LLM 分类（SKILL_RULE / KNOWLEDGE / CONTEXT / SCHEMA） |
| SkillFactory | `tracking/skill_factory.py` | 从 bug case 生成 Anti-Rat + 红线规则建议 |
| skill_auto_merge | `tracking/skill_auto_merge.py` | ApplyResult + 幂等 + dry_run + 非 fail-open 的 holdout 验证（2026-05-10 重构） |
| skill_evolution | `tracking/skill_evolution.py` | 生成 diff + 进化谱系 + 高置信度标记 |
| Gene Store | `quality/regression/gene_store.py` | 高置信 Critique 结晶为 Gene，按 phase+role 过滤注入 |
| Skill Crystal | `context/skill_crystal.py` | 高分（score≥4）执行结晶为复用模板 |
| Data patterns | `tracking/data_patterns.py` | Q06 bug case 提取 8 种故障数据模式 |

---

## 组件间关系（简化视图）

```
Worker 输出
  ↓
[T1 确定性检查] ——→ verification_bundle.json
  ↓
[T2 Guardrail 批量] ——→ _guardrail_results.json
  ↓
[T3 LLM 评审] Multi-Judge → Critique → Review Chain
  ↓
[T4 Guard 守卫] RationalizationGuard / OvercorrectionGuard → 重审或 HARD_BLOCK
  ↓
[T5 GateVerdict] 汇总 → _gate_verdict.json → cmd_approve 决策
  ↓
（跨 session）
[T6 趋势 / 回归] eval_baseline + prompt_eval + regression runner
[T7 前置决策] risk_score + confidence_decay + trust_level（下轮起作用）
[T8 Skill Evolution] SkillReflector → skill_auto_merge → holdout 验证 → SKILL.md 改写
```

---

## 观察与 Gap

1. **T1 + T3 是主 pipeline**：verification_bundle 把 T1 结果打包喂给 T3 做 evidence，这是"确定性证据 + 语义判断"的组合
2. **T4 完全是 T3 的守卫**：守 Judge 自己的偏软/偏严问题，不评产物本身
3. **T6 趋势层是跨 session 记忆**：`score_calibration` / `eval_holdout` 的打折实现都在这层
4. **DeepEval 属于 T3 横向扩展**（第四个 Judge 意见），不是新增 Tier；当前"代码保留但禁用"
5. **T8 是评"评分机制"本身**：刚补完 absorb 闭环（2026-05-10 `cf657a6`）

## 下一步决策依赖

本梳理可运营的地方：

- **Guard precision 评估**（Anti-Rat Guard P1a）→ 数据源主要是 T4 telemetry + T6 failure-library
- **ReplayExecutor**（Skill Evolution P2）→ 需要跨 T1+T3+T5 的完整回放（目前 T6 holdout 只做分布对比）
- **Bug Case compress**（T8 缺的另一半）→ 需要 T6 的时间 / 访问频率信号
- **DeepEval 复活**（T3 横向扩展）→ 需要 T4 telemetry 先暴露 Multi-Judge 系统偏软

相关 ROADMAP 条目见 §3.C "仍需推进（P1）"。

*最后更新：2026-05-10*
