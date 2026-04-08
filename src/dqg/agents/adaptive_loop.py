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
) -> JudgeVote | None:
    try:
        judge = Agent(
            name=f"judge-{model}",
            role="judge",
            system_prompt=rubric,
            model=LLMConfig(primary=model, fallback=fallback),
            output_dir=output_dir,
        )
        context = [report_path] if report_path.exists() else []
        result = judge.run("评审报告质量，输出 JSON 格式评审结果。", context_files=context)
    except Exception:
        return None
    if result.status not in ("success", "fallback"):
        return None
    return _parse_judge_output(result.content, result.model_used, result.duration_seconds)


def multi_judge_vote(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    models: list[str],
    fallback: str = "deepseek-chat",
) -> VoteResult:
    """多 Judge 投票：不同模型独立评审，取共识."""
    votes: list[JudgeVote] = []
    unique_models = list(dict.fromkeys(models))
    max_workers = max(1, len(unique_models))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single_judge, output_dir, report_path, rubric, model, fallback): model
            for model in unique_models
        }
        for future in as_completed(futures):
            vote = future.result()
            if vote is not None:
                votes.append(vote)

    votes.sort(key=lambda vote: unique_models.index(vote.model) if vote.model in unique_models else len(unique_models))

    if not votes:
        return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["所有 Judge 执行失败"])

    # 计算共识
    verdicts = [v.verdict for v in votes]
    avg_score = sum(v.overall for v in votes) / len(votes)

    if all(v == "PASS" for v in verdicts):
        consensus = "PASS"
    elif all(v == "FAIL" for v in verdicts) or verdicts.count("FAIL") > len(verdicts) / 2:
        consensus = "FAIL"
    else:
        consensus = "PASS_WITH_CONCERNS"

    # 找分歧
    disagreements = []
    if len(set(verdicts)) > 1:
        for _i, v in enumerate(votes):
            disagreements.append(f"{v.model}: {v.verdict} (score={v.overall:.1f})")

    return VoteResult(votes=votes, consensus=consensus, avg_score=avg_score, disagreements=disagreements)


def _parse_judge_output(content: str, model: str, duration: float) -> JudgeVote:
    """解析 Judge 输出的 JSON."""
    try:
        # 尝试从 content 中提取 JSON
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return JudgeVote(
                model=model,
                scores=data.get("scores", {}),
                overall=data.get("overall", 0),
                verdict=data.get("verdict", "FAIL"),
                issues=data.get("issues", []),
                duration=duration,
            )
    except (json.JSONDecodeError, KeyError):
        pass

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
            "A.5": "tech_design_coverage_review.md",
            "A.6": "tech_design_quality_review.md",
        }
        report_file = report_map.get(phase_id, "phase_report.md")
        report_path = pd / report_file

        iterations: list[IterationRecord] = []
        start = time.time()
        final_verdict = "MAX_ITERATIONS"

        for i in range(max_iterations):
            iter_start = time.time()
            record = IterationRecord(iteration=i + 1)

            # Step 1: Worker（首次执行或修正）
            if i == 0:
                worker = Agent(
                    name=f"worker-iter{i + 1}",
                    role="worker",
                    system_prompt=worker_prompt,
                    model=LLMConfig(primary=worker_model, fallback=fallback),
                    output_dir=self.output_dir,
                )
                record.worker_result = worker.run(
                    "执行 Phase 任务，输出报告。",
                    context_files=context_files,
                )
                if record.worker_result.status != "failed":
                    report_path.write_text(record.worker_result.content, encoding="utf-8")
            else:
                # 修正：基于上一轮的 Judge/Critique 反馈
                prev = iterations[-1]
                feedback = self._collect_feedback(prev)
                fixer = Agent(
                    name=f"fixer-iter{i + 1}",
                    role="worker",
                    system_prompt=worker_prompt + "\n\n## 修正指令\n" + feedback,
                    model=LLMConfig(primary=worker_model, fallback=fallback),
                    output_dir=self.output_dir,
                )
                record.worker_result = fixer.run(
                    f"根据以下反馈修正报告（第 {i + 1} 轮）:\n{feedback}",
                    context_files=[report_path] + (context_files or []),
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

            # 判断是否通过
            if record.judge_result.consensus == "PASS" or record.judge_result.avg_score >= pass_threshold:
                final_verdict = "PASS"
                break
            elif (
                record.judge_result.consensus == "PASS_WITH_CONCERNS"
                and record.judge_result.avg_score >= pass_threshold - 0.5
            ):
                final_verdict = "PASS_WITH_CONCERNS"
                break

            # Step 3: Critique（为下一轮修正提供方向）
            if i < max_iterations - 1:
                critique = Agent(
                    name=f"critique-iter{i + 1}",
                    role="critique",
                    system_prompt=critique_prompt,
                    model=LLMConfig(primary=worker_model, fallback=fallback),
                    output_dir=self.output_dir,
                )
                record.critique_result = critique.run(
                    "找出报告中的遗漏和错误，给出修正建议。",
                    context_files=[report_path],
                )

        total_duration = time.time() - start
        models_used = list(set([worker_model, *judge_models, fallback]))

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

    def _collect_feedback(self, prev: IterationRecord) -> str:
        """从上一轮的 Judge/Critique 结果收集修正反馈."""
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
