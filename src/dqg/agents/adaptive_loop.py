"""Multi-Agent Phase 3: 自适应循环 + 多 Judge 投票.

核心能力:
1. Judge 发现问题 → 自动触发 Worker 修正 → 再次 Judge → 循环直到通过
2. 多 Judge 投票（不同模型/不同 prompt），取共识
3. 研发反馈自动路由到对应 Agent 的 bug case 库

用法:
    loop = AdaptiveLoop(output_dir)
    result = loop.run("damage-assessment", "Q01",
        worker_prompt="...", judge_rubric="...",
        max_iterations=3,
        judge_models=["claude-sonnet-4-6", "deepseek-chat"],
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dqg.agents.agent import Agent, AgentResult
from dqg.agents.llm_backends import LLMConfig
from dqg.constants import DEFAULT_ADAPTIVE_JUDGE_MODELS
from dqg.log import get_logger
from dqg.agents.judge_vote import (  # noqa: F401 — re-export for backward compat
    IterationRecord,
    JudgeVote,
    VoteResult,
    judge_health_check,
    multi_judge_vote,
)
from dqg.agents.handoff_builder import build_handoff_document

log = get_logger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


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

    def __init__(self, output_dir: "Path"):
        self.output_dir = output_dir

    def run(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list["Path"] | None = None,
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

        # Prepend bootstrap context if available
        from dqg.constants import PHASE_DIR_MAP
        _dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
        _bootstrap_path = self.output_dir / project_id / _dir_suffix / "_internal" / "_bootstrap_context.md"
        if _bootstrap_path.exists():
            context_files = [_bootstrap_path] + (context_files or [])
            log.info("Bootstrap context prepended: %s", _bootstrap_path)

        from dqg.constants import REPORT_MAP
        report_file = REPORT_MAP.get(phase_id, "phase_report.md")
        report_path = pd / report_file

        iterations: list[IterationRecord] = []
        start = time.time()
        final_verdict = "MAX_ITERATIONS"

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
            record, passed = self._execute_iteration(
                i=i,
                pd=pd,
                report_path=report_path,
                worker_prompt=worker_prompt,
                judge_rubric=judge_rubric,
                critique_prompt=critique_prompt,
                context_files=context_files,
                worker_model=worker_model,
                judge_models=judge_models,
                fallback=fallback,
                pass_threshold=pass_threshold,
                iterations=iterations,
                task_id=task_id,
            )
            iterations.append(record)

            if passed:
                final_verdict = "PASS" if record.judge_result.consensus == "PASS" else "PASS_WITH_CONCERNS"
                break

        total_duration = time.time() - start
        models_used = list(set([worker_model, *judge_models, fallback]))

        self._handle_post_loop(
            iterations=iterations,
            final_verdict=final_verdict,
            max_iterations=max_iterations,
            phase_id=phase_id,
            project_id=project_id,
            task_id=task_id,
        )

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

        self._write_summary(pd, result)
        return result

    def _write_summary(self, pd: "Path", result: AdaptiveResult) -> None:
        """Write adaptive loop summary JSON."""
        from dqg.json_utils import save_json
        summary_path = pd / "_adaptive_summary.json"
        save_json(summary_path, {
            "project_id": result.project_id,
            "phase_id": result.phase_id,
            "final_verdict": result.final_verdict,
            "total_iterations": len(result.iterations),
            "total_duration": round(result.total_duration, 1),
            "models_used": result.models_used,
            "iterations": [
                {
                    "iteration": r.iteration,
                    "worker_status": r.worker_result.status if r.worker_result else "skipped",
                    "judge_consensus": r.judge_result.consensus if r.judge_result else "skipped",
                    "judge_avg_score": round(r.judge_result.avg_score, 2) if r.judge_result else 0,
                    "fix_applied": r.fix_applied,
                    "duration": round(r.duration, 1),
                }
                for r in result.iterations
            ],
        })

    def _execute_iteration(
        self,
        i: int,
        pd: "Path",
        report_path: "Path",
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list["Path"] | None,
        worker_model: str,
        judge_models: list[str],
        fallback: str,
        pass_threshold: float,
        iterations: list[IterationRecord],
        task_id: str,
    ) -> tuple[IterationRecord, bool]:
        """执行单轮迭代：Worker → Judge → Critique，返回 (record, passed)."""
        from dqg.runtime.task_store import add_task_event, save_checkpoint

        iter_start = time.time()
        record = IterationRecord(iteration=i + 1)

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
            prev = iterations[-1]
            handoff_path = pd / f"_handoff_iter{i + 1}.md"
            handoff_path.write_text(
                build_handoff_document(prev, i + 1),
                encoding="utf-8",
            )
            fixer = Agent(
                name=f"fixer-iter{i + 1}",
                role="worker",
                system_prompt=no_tool_prefix + worker_prompt,
                model=LLMConfig(primary=worker_model, fallback=fallback),
                output_dir=self.output_dir,
            )
            fixer_context = [handoff_path, report_path] + (context_files or [])
            record.worker_result = fixer.run(
                f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
                context_files=fixer_context,
            )
            if record.worker_result.status != "failed":
                report_path.write_text(record.worker_result.content, encoding="utf-8")
                record.fix_applied = True

        record.judge_result = multi_judge_vote(self.output_dir, report_path, judge_rubric, judge_models, fallback)

        # HARD_BLOCK: multi_judge_vote returns None when guard exhausted
        if record.judge_result is None:
            log.warning("Judge returned None (HARD_BLOCK), stopping adaptive loop")
            record.duration = time.time() - iter_start
            return record, False

        judge_log = pd / f"_judge_iter{i + 1}.json"
        from dqg.json_utils import save_json
        save_json(judge_log, {
            "iteration": i + 1,
            "consensus": record.judge_result.consensus,
            "avg_score": record.judge_result.avg_score,
            "votes": [
                {"model": v.model, "verdict": v.verdict, "overall": v.overall}
                for v in record.judge_result.votes
            ],
            "disagreements": record.judge_result.disagreements,
        })

        record.duration = time.time() - iter_start

        add_task_event(self.output_dir, task_id, "iteration_completed", {
            "iteration": i + 1,
            "consensus": record.judge_result.consensus if record.judge_result else "unknown",
            "avg_score": record.judge_result.avg_score if record.judge_result else 0,
        })
        save_checkpoint(self.output_dir, task_id,
                        checkpoint_id=f"iter-{i + 1}",
                        phase_id="",
                        iteration=i + 1,
                        state_snapshot={
                            "iterations_completed": i + 1,
                            "report_file": str(report_path),
                        })

        passed = False
        if record.judge_result.consensus == "PASS" or record.judge_result.avg_score >= pass_threshold:
            passed = True
        elif (
            record.judge_result.consensus == "PASS_WITH_CONCERNS"
            and record.judge_result.avg_score >= pass_threshold - 0.5
        ):
            passed = True

        critique = Agent(
            name=f"critique-iter{i + 1}",
            role="critique",
            system_prompt=critique_prompt,
            model=LLMConfig(primary=fallback, fallback=fallback),
            output_dir=self.output_dir,
        )
        record.critique_result = critique.run(
            "找出报告中的遗漏和错误，给出修正建议。",
            context_files=[report_path],
        )

        return record, passed

    def _handle_post_loop(
        self,
        iterations: list[IterationRecord],
        final_verdict: str,
        max_iterations: int,
        phase_id: str,
        project_id: str,
        task_id: str,
    ) -> None:
        """循环结束后处理：SkillReflector 触发."""
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
