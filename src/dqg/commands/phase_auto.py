"""Phase auto command: interactive input collection and full pipeline automation."""

from __future__ import annotations

import sys
from pathlib import Path  # noqa: TC003

from dqg.core.state_machine import (
    PHASE_DEFS,
    PhaseStatus,
    approve_phase,
    get_parallel_groups,
    load_state,
    save_state,
    skip_phase,
)
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir


def collect_inputs(project_id: str, phase_id: str, output_dir: Path) -> dict[str, str] | None:
    """交互式收集 Phase 所需的输入材料."""
    phase_def = PHASE_DEFS[phase_id]
    required = phase_def.get("required_inputs", [])
    optional = phase_def.get("optional_inputs", [])
    if not required and not optional:
        return {}

    print(f"\n  Phase {phase_id}({phase_def['name']}) 需要以下输入:")
    inputs: dict[str, str] = {}

    for inp in required:
        is_required = inp.get("required", True)
        print(f"  [{inp['label']}]{' *' if is_required else ''}")
        while True:
            try:
                value = input(f"    {inp['prompt']}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if value:
                inputs[inp["key"]] = value
                break
            if not is_required:
                break
            print("    (必填，请输入)")

    for inp in optional:
        print(f"  [{inp['label']}] (可选)")
        try:
            value = input(f"    {inp['prompt']}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if value:
            inputs[inp["key"]] = value

    if inputs:
        # 解析 code_repo 逗号分隔为 code_repos 列表
        raw_cr = inputs.get("code_repo", "")
        if raw_cr and "," in raw_cr:
            inputs["code_repos"] = [p.strip() for p in raw_cr.split(",") if p.strip()]
            inputs["code_repo"] = inputs["code_repos"][0]
        elif raw_cr:
            inputs["code_repos"] = [raw_cr]

        phase_dir = _phase_dir(output_dir, project_id, phase_def)
        phase_dir.mkdir(parents=True, exist_ok=True)
        int_dir = _internal_dir(output_dir, project_id, phase_def)
        int_dir.mkdir(parents=True, exist_ok=True)
        from dqg.json_utils import save_json

        (int_dir / "_inputs.json").parent.mkdir(parents=True, exist_ok=True)
        save_json(int_dir / "_inputs.json", inputs)
    return inputs


def prompt_approve(project_id: str, phase_id: str, phase_name: str) -> tuple[bool, str]:
    """交互式等待人工 approve."""
    phase_def = PHASE_DEFS[phase_id]
    print(f"\n  Phase {phase_id}({phase_name}) 等待 review")
    for d in phase_def.get("deliverables", []):
        print(f"    - {d}")
    for item in phase_def.get("approve_checklist", []):
        print(f"    [ ] {item}")
    print("\n  [a] approve  [s] skip  [q] 退出 auto 模式")
    while True:
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False, "interrupted"
        if choice in ("a", "approve", ""):
            comment = input("  备注 (回车跳过): ").strip()
            return True, comment
        if choice in ("s", "skip"):
            reason = input("  跳过原因: ").strip()
            return False, reason or "skipped in auto mode"
        if choice in ("q", "quit", "exit"):
            return False, "__quit__"
        print("  请输入 a/s/q")


def cmd_auto(args, output_dir: Path) -> int:
    """全自动推进 pipeline."""
    import dqg.runtime  # noqa: F401 — 触发 handler 注册
    from dqg.commands.phase import _telemetry
    from dqg.commands.query import print_status
    from dqg.core.profiles import get_profile
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.phase_runtime import runtime_execute, runtime_finalize

    state = load_state(output_dir, args.project_id)
    state.profile_id = get_profile(getattr(args, "profile", None)).profile_id
    save_state(output_dir, state)
    model_name = getattr(args, "model", None)
    skip_phases = set(args.skip) if hasattr(args, "skip") and args.skip else set()

    print()
    print("=" * 60)
    print(f"  Auto Pipeline — {args.project_id}")
    print("=" * 60)

    for skip_id in skip_phases:
        if state.phases.get(skip_id) and state.phases[skip_id].status == PhaseStatus.NOT_STARTED:
            skip_phase(state, skip_id, "skipped via auto --skip")
            save_state(output_dir, state)
            print(f"  Phase {skip_id} 已跳过")

    iteration = 0
    max_iterations = 20

    while iteration < max_iterations:
        iteration += 1
        groups = get_parallel_groups(state)
        if not groups:
            break

        for group in groups:
            if len(group) > 1:
                names = " + ".join(f"{pid}({PHASE_DEFS[pid]['name']})" for pid in group)
                print(f"\n  [并行执行] {names}")
            else:
                print(f"\n  [执行] Phase {group[0]}({PHASE_DEFS[group[0]]['name']})")

            for pid in group:
                inputs = collect_inputs(args.project_id, pid, output_dir)
                if inputs is None:
                    print("\n  Auto 模式中断")
                    return 1

                ctx = ExecutionContext(
                    output_dir=output_dir,
                    project_id=args.project_id,
                    phase_id=pid,
                    profile_id=state.profile_id,
                    model_name=model_name,
                )
                result = runtime_execute(ctx)
                if not result.success:
                    for e in result.errors:
                        print(f"  ERROR executing {pid}: {e}", file=sys.stderr)
                    continue

                state = load_state(output_dir, args.project_id)

                for event in result.events:
                    if event.event_type.value == "context_loaded":
                        print(f"    上下文: {event.message}")

                print(f"    Skill: {PHASE_DEFS[pid]['skill']}")
                print(f"    请执行 Phase {pid} 的 skill，完成后按回车继续...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Auto 模式中断")
                    return 1

            for pid in group:
                if state.phases[pid].status != PhaseStatus.IN_PROGRESS:
                    continue

                ctx = ExecutionContext(
                    output_dir=output_dir,
                    project_id=args.project_id,
                    phase_id=pid,
                )
                result = runtime_finalize(ctx)
                state = load_state(output_dir, args.project_id)

                if not result.success:
                    for e in result.errors:
                        print(f"    {e}", file=sys.stderr)
                    continue

                ve = [e for e in result.events if e.event_type.value == "validation_completed"]
                if ve and ve[0].data.get("validation_errors"):
                    print(f"    Schema 校验: {len(ve[0].data['validation_errors'])} 个问题")
                duration = ctx.shared.get("duration_seconds")
                if duration:
                    print(f"    耗时: {duration:.0f}s")

            for pid in group:
                if state.phases[pid].status != PhaseStatus.PENDING_REVIEW:
                    continue
                approved, comment = prompt_approve(args.project_id, pid, PHASE_DEFS[pid]["name"])
                if comment == "__quit__":
                    print("\n  Auto 模式退出")
                    print_status(state, output_dir)
                    return 0
                PhaseRunRecord, append_record, _ = _telemetry()  # noqa: N806
                if approved:
                    approve_phase(state, pid, comment)
                    save_state(output_dir, state)
                    append_record(
                        output_dir,
                        PhaseRunRecord(
                            project_id=args.project_id,
                            phase_id=pid,
                            phase_name=PHASE_DEFS[pid]["name"],
                            action="approve",
                            status="approved",
                            comment=comment,
                        ),
                    )
                    print(f"    Phase {pid} ✅ approved")
                else:
                    skip_phase(state, pid, comment)
                    save_state(output_dir, state)
                    append_record(
                        output_dir,
                        PhaseRunRecord(
                            project_id=args.project_id,
                            phase_id=pid,
                            phase_name=PHASE_DEFS[pid]["name"],
                            action="skip",
                            status="skipped",
                            comment=comment,
                        ),
                    )
                    print(f"    Phase {pid} ⏭ skipped")

    print()
    print_status(state, output_dir)
    _, _, print_run_summary = _telemetry()
    print_run_summary(output_dir, args.project_id)
    return 0
