"""Agent 命令：orchestrate / agent-run / adaptive."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.path_utils import resolve_effective_context_files


def _collect_context_files(pd: Path) -> list[Path]:
    return resolve_effective_context_files(pd)


def _dag_phase_result_dict(pr: Any) -> dict[str, Any]:
    return {
        "phase_id": pr.phase_id,
        "status": pr.status,
        "run_status": pr.run_status.value if hasattr(pr.run_status, "value") else str(pr.run_status),
        "mode": pr.mode,
        "duration_seconds": pr.duration_seconds,
        "error": pr.error,
    }


def _adaptive_result_dict(result: Any) -> dict[str, Any]:
    iterations_out: list[dict[str, Any]] = []
    for r in result.iterations:
        jr = r.judge_result
        judge_block: dict[str, Any] | None = None
        if jr is not None:
            judge_block = {
                "consensus": jr.consensus,
                "avg_score": jr.avg_score,
                "disagreement_count": len(jr.disagreements or []),
            }
        iterations_out.append(
            {
                "iteration": r.iteration,
                "fix_applied": r.fix_applied,
                "duration": r.duration,
                "judge": judge_block,
                "schema_errors": list(getattr(r, "schema_errors", []) or []),
            }
        )
    return {
        "project_id": result.project_id,
        "phase_id": result.phase_id,
        "final_verdict": result.final_verdict,
        "total_duration": result.total_duration,
        "models_used": result.models_used,
        "early_stop_reason": result.early_stop_reason,
        "health_summary": result.health_summary,
        "iterations": iterations_out,
        "llm_calls": result.llm_calls,
    }


def _pipeline_results_dict(results: dict[str, Any]) -> dict[str, Any]:
    from dqg.agents.agent import extract_llm_call

    out: dict[str, Any] = {}
    for role, ar in results.items():
        d = extract_llm_call(ar)
        d["error"] = (ar.error or "")[:500]
        d["output_files"] = list(ar.output_files)
        out[role] = d
    return out


def cmd_orchestrate(args, output_dir: Path) -> int:
    from dqg.agents.multi_agent import MultiAgentOrchestrator
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    orch = MultiAgentOrchestrator(output_dir)
    if getattr(args, "plan", False):
        plan_text = orch.format_execution_plan(args.project_id)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="orchestrate",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    phase_id=args.phase,
                    extra={"plan": True, "plan_text": plan_text},
                )
            )
        else:
            print(plan_text)
        return 0
    prompts = orch.generate_prompts(args.project_id, args.phase)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="orchestrate",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                phase_id=args.phase,
                extra={"plan": False, "prompts": {k: str(v) for k, v in prompts.items()}},
            )
        )
    else:
        print(f"\n  Multi-Agent Prompt 已生成 — Phase {args.phase}")
        for role, path in prompts.items():
            print(f"    [{role}] {path}")
        print("\n  执行顺序: Worker → Judge → Critique")
    return 0


def cmd_agent_run(args, output_dir: Path) -> int:
    from dqg.agent_framework import AgentOrchestrator
    from dqg.agents.multi_agent import generate_critique_prompt, generate_judge_prompt
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="agent-run",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unknown_phase"},
                )
            )
        else:
            print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    context_files = _collect_context_files(pd)

    from dqg.context.skill_loader import resolve_worker_prompt

    worker_prompt = resolve_worker_prompt(args.phase)

    orch = AgentOrchestrator(output_dir)
    if not cli_json_mode(args):
        print(f"\n  Multi-Agent Pipeline — Phase {args.phase}")
        print(f"  Worker: {args.primary} (fallback: {args.fallback})")
        print(f"  Judge:  {args.judge_model}")
        print(f"  Context: {len(context_files)} 个文件")

    results = orch.run_pipeline(
        args.project_id,
        args.phase,
        worker_prompt=worker_prompt,
        judge_rubric=generate_judge_prompt(output_dir, args.project_id, args.phase),
        critique_prompt=generate_critique_prompt(output_dir, args.project_id, args.phase),
        context_files=context_files,
    )
    worker_ok = results.get("worker") and getattr(results["worker"], "status", "") != "failed"
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="agent-run",
                project_id=args.project_id,
                success=bool(worker_ok),
                exit_code=0,
                phase_id=args.phase,
                extra={
                    "primary": args.primary,
                    "fallback": args.fallback,
                    "judge_model": args.judge_model,
                    "context_file_count": len(context_files),
                    "pipeline": _pipeline_results_dict(results),
                },
            )
        )
    else:
        print(orch.format_pipeline_result(results))
    return 0


def cmd_adaptive(args, output_dir: Path) -> int:
    from dqg.agents.adaptive_loop import AdaptiveLoop
    from dqg.agents.multi_agent import generate_critique_prompt, generate_judge_prompt
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.constants import MODEL_TIER

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="adaptive",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unknown_phase"},
                )
            )
        else:
            print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    judge_models = [m.strip() for m in args.judge_models.split(",")]

    # 自动按 recommended_model 选择 Worker 模型（除非用户显式指定了 --primary）
    tier = phase_def.get("recommended_model", "strong")
    auto_model = MODEL_TIER.get(tier, args.primary)
    worker_model = args.primary if args.primary != "claude-opus-4-6" else auto_model

    if not cli_json_mode(args):
        print(f"\n  自适应 Multi-Agent — Phase {args.phase}")
        print(f"  Worker: {worker_model} ({tier}) (fallback: {args.fallback})")
        print(f"  Judge:  {', '.join(judge_models)} (投票模式)")
        print(f"  最大迭代: {args.max_iter}, 通过阈值: {args.threshold}")

    from dqg.context.skill_loader import resolve_worker_prompt

    loop = AdaptiveLoop(output_dir)
    result = loop.run(
        args.project_id,
        args.phase,
        worker_prompt=resolve_worker_prompt(args.phase),
        judge_rubric=generate_judge_prompt(output_dir, args.project_id, args.phase),
        critique_prompt=generate_critique_prompt(output_dir, args.project_id, args.phase),
        context_files=_collect_context_files(pd),
        max_iterations=args.max_iter,
        pass_threshold=args.threshold,
        worker_model=worker_model,
        judge_models=judge_models,
        fallback=args.fallback,
    )
    if cli_json_mode(args):
        body = _adaptive_result_dict(result)
        body["worker_model"] = worker_model
        body["tier"] = tier
        body["judge_models"] = judge_models
        body["max_iter"] = args.max_iter
        body["threshold"] = args.threshold
        print_cli_json(
            cli_envelope(
                command="adaptive",
                project_id=args.project_id,
                success=result.final_verdict != "FAIL",
                exit_code=0,
                phase_id=args.phase,
                extra=body,
            )
        )
    else:
        print(loop.format_result(result))
    return 0


def cmd_dag(args, output_dir: Path) -> int:
    from dqg.agents.dag_scheduler import DAGScheduler
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.core.state_machine import get_parallel_groups, load_state

    scheduler = DAGScheduler(output_dir)
    skip_phases = getattr(args, "skip", None) or []
    max_parallel = getattr(args, "max_parallel", 3)
    mode = getattr(args, "mode", "adaptive")

    # --plan: 只显示执行计划
    if getattr(args, "plan", False):
        state = load_state(output_dir, args.project_id)
        groups = get_parallel_groups(state)
        plan_text = DAGScheduler.format_dag_plan(
            args.project_id,
            groups,
            skip_phases,
        )
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="dag",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={
                        "plan": True,
                        "skip_phases": list(skip_phases),
                        "groups": groups,
                        "plan_text": plan_text,
                    },
                )
            )
        else:
            print(plan_text)
        return 0

    if not cli_json_mode(args):
        print(f"\n  DAG 调度启动 — 项目: {args.project_id}")
        print(f"  模式: {mode}, 最大并行: {max_parallel}")
        if skip_phases:
            print(f"  跳过: {', '.join(skip_phases)}")

    result = scheduler.run_dag(
        args.project_id,
        skip_phases=skip_phases,
        mode=mode,
        max_parallel=max_parallel,
        primary_model=getattr(args, "primary", "claude-opus-4-6"),
        fallback_model=getattr(args, "fallback", "deepseek-chat"),
    )
    exit_code = 0 if result.phases_failed == 0 else 1
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="dag",
                project_id=args.project_id,
                success=exit_code == 0,
                exit_code=exit_code,
                extra={
                    "plan": False,
                    "mode": mode,
                    "max_parallel": max_parallel,
                    "skip_phases": list(skip_phases),
                    "total_duration": result.total_duration,
                    "phases_executed": result.phases_executed,
                    "phases_failed": result.phases_failed,
                    "phase_results": [_dag_phase_result_dict(pr) for pr in result.phase_results],
                },
            )
        )
    else:
        print(DAGScheduler.format_dag_result(result))
    return exit_code
