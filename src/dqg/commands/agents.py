"""Agent 命令：orchestrate / agent-run / adaptive."""

from __future__ import annotations

import sys
from pathlib import Path

from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.path_utils import resolve_effective_context_files


def _collect_context_files(pd: Path) -> list[Path]:
    return resolve_effective_context_files(pd)


def cmd_orchestrate(args, output_dir: Path) -> int:
    from dqg.agents.multi_agent import MultiAgentOrchestrator

    orch = MultiAgentOrchestrator(output_dir)
    if getattr(args, "plan", False):
        print(orch.format_execution_plan(args.project_id))
        return 0
    prompts = orch.generate_prompts(args.project_id, args.phase)
    print(f"\n  Multi-Agent Prompt 已生成 — Phase {args.phase}")
    for role, path in prompts.items():
        print(f"    [{role}] {path}")
    print("\n  执行顺序: Worker → Judge → Critique")
    return 0


def cmd_agent_run(args, output_dir: Path) -> int:
    from dqg.agent_framework import AgentOrchestrator
    from dqg.agents.multi_agent import generate_critique_prompt, generate_judge_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    context_files = _collect_context_files(pd)

    from dqg.context.skill_loader import resolve_worker_prompt

    worker_prompt = resolve_worker_prompt(args.phase)

    orch = AgentOrchestrator(output_dir)
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
    print(orch.format_pipeline_result(results))
    return 0


def cmd_adaptive(args, output_dir: Path) -> int:
    from dqg.agents.adaptive_loop import AdaptiveLoop
    from dqg.agents.multi_agent import generate_critique_prompt, generate_judge_prompt
    from dqg.constants import MODEL_TIER

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    judge_models = [m.strip() for m in args.judge_models.split(",")]

    # 自动按 recommended_model 选择 Worker 模型（除非用户显式指定了 --primary）
    tier = phase_def.get("recommended_model", "strong")
    auto_model = MODEL_TIER.get(tier, args.primary)
    worker_model = args.primary if args.primary != "claude-opus-4-6" else auto_model

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
    print(loop.format_result(result))
    return 0


def cmd_dag(args, output_dir: Path) -> int:
    from dqg.agents.dag_scheduler import DAGScheduler
    from dqg.core.state_machine import get_parallel_groups, load_state

    scheduler = DAGScheduler(output_dir)
    skip_phases = getattr(args, "skip", None) or []
    max_parallel = getattr(args, "max_parallel", 3)
    mode = getattr(args, "mode", "adaptive")

    # --plan: 只显示执行计划
    if getattr(args, "plan", False):
        state = load_state(output_dir, args.project_id)
        groups = get_parallel_groups(state)
        print(
            DAGScheduler.format_dag_plan(
                args.project_id,
                groups,
                skip_phases,
            )
        )
        return 0

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
    print(DAGScheduler.format_dag_result(result))
    return 0 if result.phases_failed == 0 else 1
