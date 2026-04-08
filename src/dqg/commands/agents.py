"""Agent 命令：orchestrate / agent-run / adaptive."""

from __future__ import annotations

import sys
from pathlib import Path

from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
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
    print(f"\n  执行顺序: Worker → Judge → Critique")
    return 0


def cmd_agent_run(args, output_dir: Path) -> int:
    from dqg.agent_framework import AgentOrchestrator
    from dqg.agents.multi_agent import MultiAgentOrchestrator, generate_judge_prompt, generate_critique_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    skill_path = Path(phase_def.get("skill", ""))
    if not skill_path.exists():
        print(f"  ERROR: Skill 文件不存在 {skill_path}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    context_files = _collect_context_files(pd)

    orch = AgentOrchestrator(output_dir)
    print(f"\n  Multi-Agent Pipeline — Phase {args.phase}")
    print(f"  Worker: {args.primary} (fallback: {args.fallback})")
    print(f"  Judge:  {args.judge_model}")
    print(f"  Context: {len(context_files)} 个文件")

    results = orch.run_pipeline(
        args.project_id, args.phase,
        worker_prompt=skill_path.read_text(encoding="utf-8"),
        judge_rubric=generate_judge_prompt(output_dir, args.project_id, args.phase),
        critique_prompt=generate_critique_prompt(output_dir, args.project_id, args.phase),
        context_files=context_files,
    )
    print(orch.format_pipeline_result(results))
    return 0


def cmd_adaptive(args, output_dir: Path) -> int:
    from dqg.agents.adaptive_loop import AdaptiveLoop
    from dqg.agents.multi_agent import generate_judge_prompt, generate_critique_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  ERROR: 未知 Phase {args.phase}", file=sys.stderr)
        return 1

    skill_path = Path(phase_def.get("skill", ""))
    if not skill_path.exists():
        print(f"  ERROR: Skill 文件不存在 {skill_path}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    judge_models = [m.strip() for m in args.judge_models.split(",")]

    print(f"\n  自适应 Multi-Agent — Phase {args.phase}")
    print(f"  Worker: {args.primary} (fallback: {args.fallback})")
    print(f"  Judge:  {', '.join(judge_models)} (投票模式)")
    print(f"  最大迭代: {args.max_iter}, 通过阈值: {args.threshold}")

    loop = AdaptiveLoop(output_dir)
    result = loop.run(
        args.project_id, args.phase,
        worker_prompt=skill_path.read_text(encoding="utf-8"),
        judge_rubric=generate_judge_prompt(output_dir, args.project_id, args.phase),
        critique_prompt=generate_critique_prompt(output_dir, args.project_id, args.phase),
        context_files=_collect_context_files(pd),
        max_iterations=args.max_iter,
        pass_threshold=args.threshold,
        worker_model=args.primary,
        judge_models=judge_models,
        fallback=args.fallback,
    )
    print(loop.format_result(result))
    return 0
