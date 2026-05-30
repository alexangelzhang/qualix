"""DAG 并行调度器：自动推进所有可执行 Phase，支持并行执行.

用法:
    scheduler = DAGScheduler(output_dir)
    result = scheduler.run_dag("my-project")
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qualix.constants import (
    DAG_DEFAULT_MAX_PARALLEL,
    DAG_DEFAULT_MODE,
    DEFAULT_ADAPTIVE_JUDGE_MODELS,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_PRIMARY_MODEL,
)
from qualix.core.state_machine import (
    PHASE_DEFS,
    PhaseStatus,
    get_available_phases,
    get_parallel_groups,
    load_state,
    save_state,
)
from qualix.core.state_machine import (
    phase_dir as _phase_dir,
)
from qualix.exceptions import PhaseError
from qualix.log import get_logger
from qualix.path_utils import resolve_effective_context_files
from qualix.runtime.result import RunStatus

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class PhaseResult:
    """单个 Phase 的 DAG 执行结果."""

    phase_id: str
    status: str  # success / failed / skipped
    run_status: RunStatus = RunStatus.OK
    mode: str = ""  # agent-run / adaptive
    duration_seconds: float = 0
    error: str = ""


@dataclass
class DAGResult:
    """整个 DAG 执行的汇总结果."""

    project_id: str
    phase_results: list[PhaseResult] = field(default_factory=list)
    total_duration: float = 0
    phases_executed: int = 0
    phases_failed: int = 0


# ---------------------------------------------------------------------------
# DAG 调度器
# ---------------------------------------------------------------------------


class DAGScheduler:
    """增强型 DAG 并行调度器：自动推进所有可执行 Phase."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    # -- 并行执行一组 Phase ------------------------------------------------

    def execute_parallel_phases(
        self,
        project_id: str,
        phase_ids: list[str],
        *,
        mode: str = DAG_DEFAULT_MODE,
        max_parallel: int = DAG_DEFAULT_MAX_PARALLEL,
        primary_model: str = DEFAULT_PRIMARY_MODEL,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
    ) -> list[PhaseResult]:
        """并行执行多个 Phase，每个走 Worker -> Judge -> Critique."""
        workers = min(max_parallel, len(phase_ids))
        results: list[PhaseResult] = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._run_single_phase,
                    project_id,
                    pid,
                    mode=mode,
                    primary_model=primary_model,
                    fallback_model=fallback_model,
                ): pid
                for pid in phase_ids
            }
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    result = future.result()
                except TimeoutError as exc:
                    log.error("Phase %s 超时: %s", pid, exc)
                    result = PhaseResult(
                        phase_id=pid,
                        status="failed",
                        run_status=RunStatus.TIMEOUT,
                        error=str(exc),
                    )
                except Exception as exc:
                    log.error("Phase %s 执行异常: %s", pid, exc)
                    result = PhaseResult(
                        phase_id=pid,
                        status="failed",
                        run_status=RunStatus.ADAPTER_CRASHED,
                        error=str(exc),
                    )
                results.append(result)

        results.sort(key=lambda r: phase_ids.index(r.phase_id))
        return results

    # -- 全自动 DAG 调度 ---------------------------------------------------

    def run_dag(
        self,
        project_id: str,
        *,
        skip_phases: list[str] | None = None,
        mode: str = DAG_DEFAULT_MODE,
        max_parallel: int = DAG_DEFAULT_MAX_PARALLEL,
        primary_model: str = DEFAULT_PRIMARY_MODEL,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
    ) -> DAGResult:
        """全自动 DAG 调度：循环推进所有可执行 Phase 直到无可执行."""
        skip_set = set(skip_phases or [])
        dag_result = DAGResult(project_id=project_id)
        dag_start = time.time()

        # Task store: 创建 DAG task run
        from qualix.runtime.task_store import complete_task_run, create_task_run

        task_id = create_task_run(
            self.output_dir,
            task_type="dag",
            project_id=project_id,
            config={"mode": mode, "max_parallel": max_parallel, "skip_phases": list(skip_set)},
        )

        # 先跳过指定 Phase
        if skip_set:
            self._apply_skips(project_id, skip_set)

        while True:
            state = load_state(self.output_dir, project_id)
            available = get_available_phases(state)
            available = [p for p in available if p not in skip_set]

            if not available:
                log.info("无可执行 Phase，DAG 调度结束")
                break

            groups = get_parallel_groups(state)
            groups = [[p for p in g if p in available] for g in groups]
            groups = [g for g in groups if g]

            if not groups:
                log.info("无可并行分组，DAG 调度结束")
                break

            batch = groups[0]
            log.info("DAG 批次执行: %s", " + ".join(batch))

            self._execute_dag_batch(
                project_id,
                batch,
                dag_result,
                mode,
                max_parallel,
                primary_model,
                fallback_model,
                task_id,
            )

        dag_result.total_duration = time.time() - dag_start

        # Task store: 标记完成
        complete_task_run(
            self.output_dir,
            task_id,
            status="completed" if dag_result.phases_failed == 0 else "failed",
            result_summary=f"{dag_result.phases_executed} executed, {dag_result.phases_failed} failed",
        )

        return dag_result

    # -- 内部方法 ----------------------------------------------------------

    def _execute_dag_batch(
        self,
        project_id: str,
        batch: list[str],
        dag_result: DAGResult,
        mode: str,
        max_parallel: int,
        primary_model: str,
        fallback_model: str,
        task_id: str,
    ) -> None:
        from qualix.runtime.task_store import add_task_event, save_checkpoint

        # 标记 in_progress + 执行 runtime handler
        for pid in batch:
            from qualix.runtime.execution_context import ExecutionContext
            from qualix.runtime.phase_runtime import runtime_execute

            ctx = ExecutionContext(
                output_dir=self.output_dir,
                project_id=project_id,
                phase_id=pid,
            )
            result = runtime_execute(ctx)
            if not result.success:
                log.warning("Phase %s 启动失败: %s", pid, result.errors)
                dag_result.phase_results.append(
                    PhaseResult(phase_id=pid, status="failed", error="; ".join(result.errors))
                )
                dag_result.phases_failed += 1

        # 并行执行
        batch_results = self.execute_parallel_phases(
            project_id,
            batch,
            mode=mode,
            max_parallel=max_parallel,
            primary_model=primary_model,
            fallback_model=fallback_model,
        )

        # finalize 每个成功的 Phase
        for pr in batch_results:
            dag_result.phase_results.append(pr)
            dag_result.phases_executed += 1
            if pr.status == "failed":
                dag_result.phases_failed += 1
                # 记录 run_status 到 state，即使失败也要记录失败原因
                state = load_state(self.output_dir, project_id)
                ps = state.phases.get(pr.phase_id)
                if ps:
                    ps.run_status = pr.run_status.value
                save_state(self.output_dir, state)
                continue

            # 记录 run_status 到 state
            state = load_state(self.output_dir, project_id)
            ps = state.phases.get(pr.phase_id)
            if ps:
                ps.run_status = pr.run_status.value
            save_state(self.output_dir, state)

            from qualix.runtime.execution_context import ExecutionContext
            from qualix.runtime.phase_runtime import runtime_finalize

            fin_ctx = ExecutionContext(
                output_dir=self.output_dir,
                project_id=project_id,
                phase_id=pr.phase_id,
            )
            fin_result = runtime_finalize(fin_ctx)
            if not fin_result.success:
                log.warning("Phase %s finalize 失败: %s", pr.phase_id, fin_result.errors)

        # Task store: 批次完成检查点
        add_task_event(
            self.output_dir,
            task_id,
            "batch_completed",
            {
                "batch": [pr.phase_id for pr in batch_results],
                "executed": dag_result.phases_executed,
                "failed": dag_result.phases_failed,
            },
        )
        save_checkpoint(
            self.output_dir,
            task_id,
            checkpoint_id=f"batch-{dag_result.phases_executed}",
            state_snapshot={
                "phases_executed": dag_result.phases_executed,
                "phases_failed": dag_result.phases_failed,
                "completed_phases": [pr.phase_id for pr in dag_result.phase_results if pr.status != "failed"],
            },
        )

    def _run_single_phase(
        self,
        project_id: str,
        phase_id: str,
        *,
        mode: str,
        primary_model: str,
        fallback_model: str,
    ) -> PhaseResult:
        """执行单个 Phase（agent-run 或 adaptive 模式）."""
        start = time.time()
        phase_def = PHASE_DEFS.get(phase_id)
        if not phase_def:
            raise PhaseError(phase_id, f"未知 Phase: {phase_id}")

        # Preflight: 上游产物完整性 + 级联失败阻断
        from qualix.runtime.preflight import run_preflight

        preflight = run_preflight(self.output_dir, project_id, phase_id)
        if not preflight.can_continue:
            fail_details = [c["detail"] for c in preflight.checks if c["status"] == "FAIL"]
            return PhaseResult(
                phase_id=phase_id,
                status="failed",
                run_status=RunStatus.ADAPTER_CRASHED,
                mode=mode,
                duration_seconds=round(time.time() - start, 1),
                error=f"Preflight blocked: {'; '.join(fail_details)}",
            )

        pd = _phase_dir(self.output_dir, project_id, phase_def)
        pd.mkdir(parents=True, exist_ok=True)
        context_files = resolve_effective_context_files(pd)

        from qualix.context.skill_loader import resolve_worker_prompt

        worker_prompt = resolve_worker_prompt(phase_id)

        from qualix.agents.multi_agent import (
            generate_critique_prompt,
            generate_judge_prompt,
        )

        judge_rubric = generate_judge_prompt(self.output_dir, project_id, phase_id)
        critique_prompt = generate_critique_prompt(self.output_dir, project_id, phase_id)

        if mode == "adaptive":
            run_status = self._run_adaptive(
                project_id,
                phase_id,
                worker_prompt,
                judge_rubric,
                critique_prompt,
                context_files,
                primary_model,
                fallback_model,
            )
        else:
            run_status = self._run_agent(
                project_id,
                phase_id,
                worker_prompt,
                judge_rubric,
                critique_prompt,
                context_files,
            )

        duration = time.time() - start
        status = "failed" if run_status != RunStatus.OK else "success"
        return PhaseResult(
            phase_id=phase_id,
            status=status,
            run_status=run_status,
            mode=mode,
            duration_seconds=round(duration, 1),
        )

    def _run_agent(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path],
    ) -> RunStatus:
        """agent-run 模式：单次 Worker -> Judge -> Critique."""
        from qualix.agents.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(self.output_dir)
        results = orch.run_pipeline(
            project_id,
            phase_id,
            worker_prompt=worker_prompt,
            judge_rubric=judge_rubric,
            critique_prompt=critique_prompt,
            context_files=context_files,
        )
        failed = any(r.status == "failed" for r in results.values())
        return RunStatus.ADAPTER_CRASHED if failed else RunStatus.OK

    def _run_adaptive(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path],
        primary_model: str,
        fallback_model: str,
    ) -> RunStatus:
        """adaptive 模式：自适应循环 + 多 Judge 投票."""
        from qualix.agents.adaptive_loop import AdaptiveLoop

        loop = AdaptiveLoop(self.output_dir)
        result = loop.run(
            project_id,
            phase_id,
            worker_prompt=worker_prompt,
            judge_rubric=judge_rubric,
            critique_prompt=critique_prompt,
            context_files=context_files,
            worker_model=primary_model,
            judge_models=list(DEFAULT_ADAPTIVE_JUDGE_MODELS),
            fallback=fallback_model,
        )
        return RunStatus.OK if result.final_verdict != "FAIL" else RunStatus.TAINTED

    def _apply_skips(self, project_id: str, skip_set: set[str]) -> None:
        """将指定 Phase 标记为 skipped."""
        from qualix.core.state_machine import skip_phase

        state = load_state(self.output_dir, project_id)
        for pid in skip_set:
            if pid in PHASE_DEFS:
                ps = state.phases.get(pid)
                if ps and ps.status == PhaseStatus.NOT_STARTED:
                    skip_phase(state, pid, comment="DAG --skip")
        save_state(self.output_dir, state)

    # -- 格式化输出 --------------------------------------------------------

    @staticmethod
    def format_dag_result(result: DAGResult) -> str:
        """格式化 DAG 执行结果."""
        lines = [
            f"\n  DAG 调度完成 — 项目: {result.project_id}",
            f"  总耗时: {result.total_duration:.1f}s",
            f"  执行: {result.phases_executed} 个 Phase, 失败: {result.phases_failed} 个",
            "",
        ]
        for pr in result.phase_results:
            icon = {"success": "+", "failed": "x", "skipped": "-"}.get(pr.status, "?")
            line = f"    [{icon}] Phase {pr.phase_id}: {pr.status}"
            if pr.run_status != RunStatus.OK:
                line += f" [{pr.run_status.value}]"
            if pr.mode:
                line += f" ({pr.mode})"
            if pr.duration_seconds:
                line += f" {pr.duration_seconds:.1f}s"
            if pr.error:
                line += f"\n        error: {pr.error[:120]}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def format_dag_plan(
        project_id: str,
        groups: list[list[str]],
        skip_phases: list[str] | None = None,
    ) -> str:
        """格式化 DAG 执行计划."""
        skip_set = set(skip_phases or [])
        lines = [f"\n  DAG 执行计划 — 项目: {project_id}"]
        if skip_set:
            lines.append(f"  跳过: {', '.join(sorted(skip_set))}")
        lines.append("")

        step = 1
        for group in groups:
            effective = [p for p in group if p not in skip_set]
            if not effective:
                continue
            parallel = " + ".join(effective)
            tag = "（并行）" if len(effective) > 1 else ""
            lines.append(f"    Step {step}: {parallel}{tag}")
            for pid in effective:
                lines.append(f"      -> Phase {pid}: Worker -> Judge -> Critique")
            step += 1

        if step == 1:
            lines.append("    无可执行 Phase")
        return "\n".join(lines)
