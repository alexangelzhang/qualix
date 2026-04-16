"""Multi-Agent Phase 3: 自适应循环 + 多 Judge 投票.

核心能力:
1. Judge 发现问题 → 自动触发 Worker 修正 → 再次 Judge → 循环直到通过
2. 多 Judge 投票（不同模型/不同 prompt），取共识
3. 研发反馈自动路由到对应 Agent 的 bug case 库

用法:
    loop = AdaptiveLoop(output_dir)
    result = loop.run("damage-assessment", "A",
        worker_prompt="...", judge_rubric="...",
        max_iterations=3,
        judge_models=["claude-sonnet-4-6", "deepseek-chat"],
    )
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dqg.agent_framework import Agent, AgentResult, LLMConfig
from dqg.constants import DEFAULT_ADAPTIVE_JUDGE_MODELS
from dqg.log import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Judge 投票
# ---------------------------------------------------------------------------


@dataclass
class JudgeVote:
    model: str
    scores: dict[str, int]
    overall: float
    verdict: str  # PASS / PASS_WITH_CONCERNS / FAIL
    issues: list[dict[str, Any]]
    duration: float = 0
    raw_output: str = ""
    health: str = "HEALTHY"  # HEALTHY | INFRA_FAILURE | GUARD_EXHAUSTED


@dataclass
class VoteResult:
    votes: list[JudgeVote]
    consensus: str  # PASS / PASS_WITH_CONCERNS / FAIL
    avg_score: float
    disagreements: list[str]


def _run_single_judge(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    model: str,
    fallback: str,
    warning_override: str | None = None,
) -> JudgeVote | None:
    """Thin wrapper: delegates to JudgeRunner, handles round orchestration."""
    from dqg.quality.judge_runner import JudgeRunner

    runner = JudgeRunner()
    result = runner.run(
        phase="",
        report_path=str(report_path),
        output_dir=str(output_dir),
        model=model,
        fallback=fallback,
        rubric=rubric,
        warning_override=warning_override,
    )

    if result.health == "INFRA_FAILURE":
        log.warning("JudgeRunner returned INFRA_FAILURE for model=%s", model)
        return None

    return JudgeVote(
        model=result.model,
        scores={d["id"]: d.get("score", 0) for d in result.dimensions},
        overall=result.overall_score,
        verdict=result.verdict,
        issues=result.issues,
        duration=result.duration,
        raw_output=result.raw_output,
        health=result.health,
    )


def multi_judge_vote(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    models: list[str],
    fallback: str = "deepseek-chat",
) -> VoteResult:
    """Primary Judge + Secondary Validation 策略.

    1. 先用第一个模型（primary）独立评审
    2. 如果 primary 分数在边界区间（pass_threshold ± 0.5），启动 secondary 验证
    3. 如果 primary 分数明确 PASS 或 FAIL，直接采纳，不浪费 secondary 调用
    """
    from dqg.constants import JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA

    unique_models = list(dict.fromkeys(models))
    if not unique_models:
        return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["No judge models configured"])

    primary_model = unique_models[0]
    secondary_models = unique_models[1:]

    # Step 1: Primary Judge
    primary_vote = _run_single_judge(output_dir, report_path, rubric, primary_model, fallback)
    if primary_vote is None:
        # Primary 失败，fallback 到全量投票
        log.warning("Primary judge %s failed, falling back to secondary models", primary_model)
        votes = []
        for model in secondary_models:
            vote = _run_single_judge(output_dir, report_path, rubric, model, fallback)
            if vote is not None:
                votes.append(vote)
        if not votes:
            return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["所有 Judge 执行失败"])
        avg_score = sum(v.overall for v in votes) / len(votes)
        verdicts = [v.verdict for v in votes]
        consensus = _compute_consensus(verdicts, avg_score, JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA)
        return VoteResult(votes=votes, consensus=consensus, avg_score=avg_score, disagreements=[])

    # --- Guard: Anti-Rationalization check on primary vote ---
    if primary_vote is not None and primary_vote.raw_output:
        from dqg.quality.rationalization_guard import RationalizationGuard, format_rejudge_warning

        guard = RationalizationGuard()
        guard_result = guard.check(primary_vote.raw_output)

        if not guard_result.passed:
            log.warning("Guard detected rationalization in primary judge, re-judging")
            warning_text = format_rejudge_warning(guard_result)
            primary_vote = _run_single_judge(
                output_dir, report_path, rubric, primary_model, fallback,
                warning_override=warning_text,
            )
            if primary_vote is not None:
                guard_result_2 = guard.check(primary_vote.raw_output)
                if not guard_result_2.passed:
                    log.warning("Guard budget exhausted, marking as GUARD_EXHAUSTED")
                    primary_vote.health = "GUARD_EXHAUSTED"
                    primary_vote.verdict = "INVALID"

        if primary_vote is not None and primary_vote.health == "GUARD_EXHAUSTED":
            log.warning("Primary vote GUARD_EXHAUSTED, excluding from consensus")
            primary_vote = None

    if primary_vote is None:
        # Primary failed or was excluded by guard, fallback to secondary models
        log.warning("Primary judge excluded, falling back to secondary models")
        votes_fallback: list[JudgeVote] = []
        for model in secondary_models:
            vote = _run_single_judge(output_dir, report_path, rubric, model, fallback)
            if vote is not None:
                votes_fallback.append(vote)
        if not votes_fallback:
            return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["所有 Judge 执行失败"])
        avg_score = sum(v.overall for v in votes_fallback) / len(votes_fallback)
        verdicts = [v.verdict for v in votes_fallback]
        consensus = _compute_consensus(verdicts, avg_score, JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA)
        return VoteResult(votes=votes_fallback, consensus=consensus, avg_score=avg_score, disagreements=[])

    votes: list[JudgeVote] = [primary_vote]

    # Step 2: 判断是否需要 secondary validation
    boundary_low = JUDGE_PASS_THRESHOLD - JUDGE_PASS_WITH_CONCERNS_DELTA
    boundary_high = JUDGE_PASS_THRESHOLD + JUDGE_PASS_WITH_CONCERNS_DELTA
    is_boundary = boundary_low <= primary_vote.overall <= boundary_high

    if is_boundary and secondary_models:
        log.info(
            "Primary judge %s score=%.1f in boundary [%.1f, %.1f], invoking secondary validation",
            primary_model, primary_vote.overall, boundary_low, boundary_high,
        )
        # 并行执行 secondary judges
        max_workers = max(1, len(secondary_models))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_single_judge, output_dir, report_path, rubric, model, fallback): model
                for model in secondary_models
            }
            for future in as_completed(futures):
                vote = future.result()
                if vote is not None:
                    votes.append(vote)
    elif not is_boundary:
        log.info(
            "Primary judge %s score=%.1f clear %s, skipping secondary validation",
            primary_model, primary_vote.overall,
            "PASS" if primary_vote.overall >= JUDGE_PASS_THRESHOLD else "FAIL",
        )

    # Step 3: 计算共识
    avg_score = sum(v.overall for v in votes) / len(votes)
    verdicts = [v.verdict for v in votes]
    consensus = _compute_consensus(verdicts, avg_score, JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA)

    # 找分歧
    disagreements = []
    if len(set(verdicts)) > 1:
        for v in votes:
            disagreements.append(f"{v.model}: {v.verdict} (score={v.overall:.1f})")

    return VoteResult(votes=votes, consensus=consensus, avg_score=avg_score, disagreements=disagreements)


def _compute_consensus(
    verdicts: list[str], avg_score: float, pass_threshold: float, concerns_delta: float,
) -> str:
    """从投票结果计算共识."""
    if all(v == "PASS" for v in verdicts):
        return "PASS"
    if all(v == "FAIL" for v in verdicts) or verdicts.count("FAIL") > len(verdicts) / 2:
        return "FAIL"
    if avg_score >= pass_threshold:
        return "PASS_WITH_CONCERNS"
    if avg_score >= pass_threshold - concerns_delta:
        return "PASS_WITH_CONCERNS"
    return "FAIL"


def judge_health_check(judge_results: list[VoteResult]) -> str:
    """Check if judge results contain enough valid votes.

    Returns:
        'HEALTHY' if >= 2 valid votes across all iterations
        'SEMANTIC_FAIL' if valid votes exist but all FAIL
        'INFRA_FAILURE' if insufficient valid votes
    """
    valid_votes = 0
    for vr in judge_results:
        for v in vr.votes:
            if v.health == "HEALTHY":
                valid_votes += 1
    if valid_votes < 2:
        return "INFRA_FAILURE"
    if all(vr.consensus == "FAIL" for vr in judge_results):
        return "SEMANTIC_FAIL"
    return "HEALTHY"


def _parse_judge_output(content: str, model: str, duration: float) -> JudgeVote:
    """解析 Judge 输出的 JSON."""
    import re as _re
    try:
        # 优先从 ```json 代码块提取
        json_match = _re.search(r"```json\s*\n([\s\S]*?)\n```", content)
        if json_match:
            raw = json_match.group(1)
        else:
            # fallback: 从第一个 { 到最后一个 }
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                raw = content[start:end]
            else:
                log.warning("Judge %s: no JSON found in output (len=%d)", model, len(content))
                return JudgeVote(model=model, scores={}, overall=0, verdict="FAIL", issues=[], duration=duration)

        data = json.loads(raw)
        vote = JudgeVote(
            model=model,
            scores=data.get("scores", {}),
            overall=data.get("overall", 0),
            verdict=data.get("verdict", "FAIL"),
            issues=data.get("issues", []),
            duration=duration,
        )
        log.info("Judge %s parsed: verdict=%s, overall=%s", model, vote.verdict, vote.overall)
        return vote
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("Judge %s: JSON parse failed: %s, content[:200]=%s", model, e, content[:200])
        return JudgeVote(model=model, scores={}, overall=0, verdict="FAIL", issues=[], duration=duration)


# ---------------------------------------------------------------------------
# 自适应循环
# ---------------------------------------------------------------------------


@dataclass
class IterationRecord:
    iteration: int
    worker_result: AgentResult | None = None
    judge_result: VoteResult | None = None
    critique_result: AgentResult | None = None
    fix_applied: bool = False
    duration: float = 0


@dataclass
class AdaptiveResult:
    project_id: str
    phase_id: str
    iterations: list[IterationRecord]
    final_verdict: str  # PASS / FAIL / MAX_ITERATIONS
    total_duration: float = 0
    models_used: list[str] = field(default_factory=list)


class AdaptiveLoop:
    """自适应循环：Judge 不通过 → 自动修正 → 再 Judge → 直到通过或达上限."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def run(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None = None,
        max_iterations: int = 3,
        pass_threshold: float = 3.5,
        worker_model: str = "claude-opus-4-6",
        judge_models: list[str] | None = None,
        fallback: str = "deepseek-chat",
    ) -> AdaptiveResult:
        """执行自适应循环."""
        if judge_models is None:
            judge_models = list(DEFAULT_ADAPTIVE_JUDGE_MODELS)

        from dqg.core.state_machine import PHASE_DEFS
        from dqg.core.state_machine import phase_dir as _pd

        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _pd(self.output_dir, project_id, phase_def)
        pd.mkdir(parents=True, exist_ok=True)

        report_map = {
            "A": "phase_a_report.md",
            "A.3": "tech_design.md",
            "A.5": "tech_design_coverage_review.md",
            "A.6": "tech_design_quality_review.md",
            "B": "eut_matrix.md",
            "C": "ut_audit_report.md",
            "D": "review_report.md",
        }
        report_file = report_map.get(phase_id, "phase_report.md")
        report_path = pd / report_file

        iterations: list[IterationRecord] = []
        start = time.time()
        final_verdict = "MAX_ITERATIONS"

        # Task store: 创建 task run
        from dqg.runtime.task_store import add_task_event, complete_task_run, create_task_run, save_checkpoint

        task_id = create_task_run(
            self.output_dir,
            task_type="adaptive",
            project_id=project_id,
            phase_id=phase_id,
            config={"max_iterations": max_iterations, "pass_threshold": pass_threshold,
                    "worker_model": worker_model, "judge_models": judge_models},
        )

        for i in range(max_iterations):
            iter_start = time.time()
            record = IterationRecord(iteration=i + 1)

            # Step 1: Worker（首次执行或修正）
            # Worker 禁止调用工具，必须基于 context_files 直接输出报告
            no_tool_prefix = (
                "【重要约束】\n"
                "1. 你不能调用任何工具（bash/readFile/grep/fsWrite 等），所有信息已在 context_files 中提供。\n"
                "2. 每条结论必须标注来源（[来源: 文件名:行号]）和置信度（`High`/`Medium`/`Low`）。\n"
                "3. 报告末尾必须包含「自我评审记录」章节（Judge + Critique 视角）。\n"
                "4. 直接输出 Markdown 报告内容，不要输出 JSON 或 tool_call。\n\n"
            )
            if i == 0:
                worker = Agent(
                    name=f"worker-iter{i + 1}",
                    role="worker",
                    system_prompt=no_tool_prefix + worker_prompt,
                    model=LLMConfig(primary=worker_model, fallback=fallback),
                    output_dir=self.output_dir,
                )
                record.worker_result = worker.run(
                    "基于提供的上下文，执行 Phase 任务，直接输出结构化报告。",
                    context_files=context_files,
                )
                if record.worker_result.status != "failed":
                    report_path.write_text(record.worker_result.content, encoding="utf-8")
            else:
                # Context Reset：每轮启动全新 agent 实例 + 结构化交接文档
                # 不在同一 context 里累积，避免 Brevity Bias 和 Context Collapse
                prev = iterations[-1]
                handoff_path = pd / f"_handoff_iter{i + 1}.md"
                handoff_path.write_text(
                    self._build_handoff_document(prev, i + 1),
                    encoding="utf-8",
                )
                fixer = Agent(
                    name=f"fixer-iter{i + 1}",
                    role="worker",
                    system_prompt=no_tool_prefix + worker_prompt,
                    model=LLMConfig(primary=worker_model, fallback=fallback),
                    output_dir=self.output_dir,
                )
                # 干净的 context：system prompt + 交接文档 + 上一轮报告 + 原始 context
                fixer_context = [handoff_path, report_path] + (context_files or [])
                record.worker_result = fixer.run(
                    f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
                    context_files=fixer_context,
                )
                if record.worker_result.status != "failed":
                    report_path.write_text(record.worker_result.content, encoding="utf-8")
                    record.fix_applied = True

            # Step 2: Multi-Judge 投票
            record.judge_result = multi_judge_vote(self.output_dir, report_path, judge_rubric, judge_models, fallback)

            # 保存 Judge 结果
            judge_log = pd / f"_judge_iter{i + 1}.json"
            judge_log.write_text(
                json.dumps(
                    {
                        "iteration": i + 1,
                        "consensus": record.judge_result.consensus,
                        "avg_score": record.judge_result.avg_score,
                        "votes": [
                            {"model": v.model, "verdict": v.verdict, "overall": v.overall}
                            for v in record.judge_result.votes
                        ],
                        "disagreements": record.judge_result.disagreements,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            record.duration = time.time() - iter_start
            iterations.append(record)

            # Task store: 保存检查点 + 记录事件
            add_task_event(self.output_dir, task_id, "iteration_completed", {
                "iteration": i + 1,
                "consensus": record.judge_result.consensus if record.judge_result else "unknown",
                "avg_score": record.judge_result.avg_score if record.judge_result else 0,
            })
            save_checkpoint(self.output_dir, task_id,
                            checkpoint_id=f"iter-{i + 1}",
                            phase_id=phase_id,
                            iteration=i + 1,
                            state_snapshot={
                                "verdict": final_verdict,
                                "iterations_completed": i + 1,
                                "report_file": str(report_path),
                            })

            # 判断是否通过
            passed = False
            if record.judge_result.consensus == "PASS" or record.judge_result.avg_score >= pass_threshold:
                final_verdict = "PASS"
                passed = True
            elif (
                record.judge_result.consensus == "PASS_WITH_CONCERNS"
                and record.judge_result.avg_score >= pass_threshold - 0.5
            ):
                final_verdict = "PASS_WITH_CONCERNS"
                passed = True

            # Step 3: Critique（每轮都执行，不只是 FAIL 时）
            # PASS 时 Critique 的发现记录为参考，FAIL 时用于指导 Fixer
            critique = Agent(
                name=f"critique-iter{i + 1}",
                role="critique",
                system_prompt=critique_prompt,
                model=LLMConfig(primary=fallback, fallback=fallback),  # Critique 用便宜模型
                output_dir=self.output_dir,
            )
            record.critique_result = critique.run(
                "找出报告中的遗漏和错误，给出修正建议。",
                context_files=[report_path],
            )

            # PASS 时记录 Critique notes 后退出
            if passed:
                break

        total_duration = time.time() - start
        models_used = list(set([worker_model, *judge_models, fallback]))

        # SkillReflector trigger: all iterations exhausted with FAIL
        all_judge_results = [r.judge_result for r in iterations if r.judge_result is not None]
        all_failed = final_verdict not in ("PASS", "PASS_WITH_CONCERNS") and len(iterations) >= max_iterations
        if all_failed and all_judge_results:
            health = judge_health_check(all_judge_results)
            if health == "SEMANTIC_FAIL":
                log.info("All iterations FAIL with healthy judges → triggering SkillReflector")
                from dqg.tracking.skill_reflector import SkillReflector
                reflector = SkillReflector(phase=phase_id, project_id=project_id)
                judge_dicts = []
                for vr in all_judge_results:
                    for v in vr.votes:
                        judge_dicts.append({
                            "verdict": v.verdict,
                            "overall": v.overall,
                            "issues": v.issues,
                        })
                evolution_outcome = reflector.reflect_and_write(judge_dicts)
                log.info("SkillReflector outcome: %s", evolution_outcome.action)
            elif health == "INFRA_FAILURE":
                log.warning("Judge infrastructure failure detected, skipping skill evolution")

        # Task store: 标记完成
        complete_task_run(
            self.output_dir, task_id,
            status="completed" if final_verdict in ("PASS", "PASS_WITH_CONCERNS") else "failed",
            result_summary=f"{final_verdict} after {len(iterations)} iterations",
        )

        result = AdaptiveResult(
            project_id=project_id,
            phase_id=phase_id,
            iterations=iterations,
            final_verdict=final_verdict,
            total_duration=total_duration,
            models_used=models_used,
        )

        # 保存总结
        summary_path = pd / "_adaptive_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "phase_id": phase_id,
                    "final_verdict": final_verdict,
                    "total_iterations": len(iterations),
                    "total_duration": round(total_duration, 1),
                    "models_used": models_used,
                    "iterations": [
                        {
                            "iteration": r.iteration,
                            "worker_status": r.worker_result.status if r.worker_result else "skipped",
                            "judge_consensus": r.judge_result.consensus if r.judge_result else "skipped",
                            "judge_avg_score": round(r.judge_result.avg_score, 2) if r.judge_result else 0,
                            "fix_applied": r.fix_applied,
                            "duration": round(r.duration, 1),
                        }
                        for r in iterations
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return result

    def _build_handoff_document(self, prev: IterationRecord, next_iteration: int) -> str:
        """生成结构化交接文档（Anthropic Context Reset 模式）.

        交接文档是新 agent 实例的唯一上下文来源（除了原始 context_files），
        确保关键信息不会在 context 压缩中丢失。
        """
        parts = [
            f"# 交接文档 — 第 {next_iteration} 轮修正",
            "",
            "## Goal（任务目标）",
            "修正上一轮报告中 Judge 和 Critique 指出的问题，输出改进后的完整报告。",
            "",
        ]

        # Progress（上一轮进展）
        parts.append("## Progress（上一轮进展）")
        parts.append(f"- 迭代轮次: 第 {prev.iteration} 轮")
        if prev.judge_result:
            parts.append(f"- Judge 共识: {prev.judge_result.consensus}")
            parts.append(f"- Judge 均分: {prev.judge_result.avg_score:.1f}")
        parts.append("")

        # Decisions（需要保留的决策）
        parts.append("## Decisions（已确认的决策，修正时不要推翻）")
        if prev.judge_result:
            for vote in prev.judge_result.votes:
                for issue in vote.issues:
                    if issue.get("severity") in ("info", "suggestion"):
                        parts.append(f"- [保留] {issue.get('description', '')}")
        if not any(line.startswith("- [保留]") for line in parts):
            parts.append("- （无需特别保留的决策）")
        parts.append("")

        # Issues（必须修正的问题）
        parts.append("## Issues（必须修正的问题，按严重程度排序）")
        if prev.judge_result:
            issue_idx = 0
            for vote in prev.judge_result.votes:
                for issue in vote.issues:
                    severity = issue.get("severity", "medium")
                    if severity in ("info", "suggestion"):
                        continue
                    issue_idx += 1
                    parts.append(
                        f"{issue_idx}. [{severity}] {issue.get('description', '')}"
                    )
                    if issue.get("suggestion"):
                        parts.append(f"   建议: {issue['suggestion']}")
        if prev.judge_result and prev.judge_result.disagreements:
            parts.append("")
            parts.append("### Judge 分歧")
            for d in prev.judge_result.disagreements:
                parts.append(f"- {d}")
        parts.append("")

        # Critique 发现
        if prev.critique_result and prev.critique_result.status != "failed":
            parts.append("## Critique 发现")
            # 截断但保留结构
            critique_text = prev.critique_result.content
            if len(critique_text) > 2000:
                critique_text = critique_text[:2000] + "\n...(截断)"
            parts.append(critique_text)
            parts.append("")

        # Next Steps（修正指引）
        parts.append("## Next Steps（修正指引）")
        parts.append("1. 逐条修正上述 Issues 中的问题")
        parts.append("2. 保留 Decisions 中已确认的内容")
        parts.append("3. 修正后在报告末尾更新「自我评审记录」章节")
        parts.append("4. 确保修正不引入新问题")

        return "\n".join(parts)

    def _collect_feedback(self, prev: IterationRecord) -> str:
        """从上一轮的 Judge/Critique 结果收集修正反馈（向后兼容）."""
        parts = []

        if prev.judge_result:
            parts.append(
                f"## Judge 评审结果（共识: {prev.judge_result.consensus}，均分: {prev.judge_result.avg_score:.1f}）"
            )
            for vote in prev.judge_result.votes:
                parts.append(f"\n### {vote.model} (verdict={vote.verdict}, score={vote.overall})")
                for issue in vote.issues:
                    parts.append(
                        f"- [{issue.get('type', '?')}][{issue.get('severity', '?')}] {issue.get('description', '')}"
                    )
                    if issue.get("suggestion"):
                        parts.append(f"  建议: {issue['suggestion']}")

        if prev.critique_result and prev.critique_result.status != "failed":
            parts.append("\n## Critique 发现")
            parts.append(prev.critique_result.content[:2000])

        return "\n".join(parts) if parts else "无具体反馈"

    def format_result(self, result: AdaptiveResult) -> str:
        """格式化自适应循环结果."""
        lines = [
            f"  自适应 Multi-Agent — Phase {result.phase_id}",
            f"  最终判定: {result.final_verdict}",
            f"  迭代次数: {len(result.iterations)}/{3}",
            f"  总耗时: {result.total_duration:.1f}s",
            f"  使用模型: {', '.join(result.models_used)}",
        ]

        for r in result.iterations:
            judge_info = ""
            if r.judge_result:
                judge_info = f"consensus={r.judge_result.consensus}, avg={r.judge_result.avg_score:.1f}"
                if r.judge_result.disagreements:
                    judge_info += f", 分歧={len(r.judge_result.disagreements)}"
            fix_info = " [已修正]" if r.fix_applied else ""
            lines.append(f"    Iter {r.iteration}: {judge_info}{fix_info} ({r.duration:.1f}s)")

        return "\n".join(lines)
