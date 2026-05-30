"""查询命令：status / next / detail / log / startup."""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from typing import Final

from qualix.core.state_machine import (
    PHASE_DEFS,
    PHASE_ORDER,
    PhaseStatus,
    get_available_phases,
    get_parallel_groups,
    load_state,
    save_state,
)
from qualix.core.state_machine import (
    phase_dir as _phase_dir,
)
from qualix.json_utils import dump_json_str, load_json_strict

STATUS_ICONS: Final = MappingProxyType(
    {
        PhaseStatus.NOT_STARTED: "⬜",
        PhaseStatus.IN_PROGRESS: "🔶",
        PhaseStatus.PENDING_REVIEW: "🔍",
        PhaseStatus.APPROVED: "✅",
        PhaseStatus.SKIPPED: "⏭",
    }
)


def print_status(state, output_dir: Path) -> None:
    """打印状态看板."""
    print()
    print("=" * 68)
    print(f"  项目状态看板 — {state.project_id}")
    print(f"  当前 Profile — {state.profile_id}")
    print("=" * 68)
    print(f"  {'Phase':<8} {'名称':<20} {'状态':<18} {'耗时':<12} {'备注'}")
    print("-" * 68)

    total = len(PHASE_ORDER)
    done = 0
    total_duration = 0.0
    judge_scores: list[float] = []

    for phase_id in PHASE_ORDER:
        ps = state.phases[phase_id]
        icon = STATUS_ICONS.get(ps.status, "?")
        name = PHASE_DEFS[phase_id]["name"]
        duration = f"{ps.duration_seconds:.0f}s" if ps.duration_seconds else "—"
        comment = ps.comment[:20] if ps.comment else ""
        errors = f" ({len(ps.validation_errors)} errors)" if ps.validation_errors else ""
        judge = f" [J:{ps.judge_score:.1f}{'✅' if ps.judge_passed else '⚠'}]" if ps.judge_score is not None else ""
        print(f"  {phase_id:<8} {name:<20} {icon} {ps.status:<14} {duration:<12} {comment}{errors}{judge}")

        if ps.status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED):
            done += 1
        if ps.duration_seconds:
            total_duration += ps.duration_seconds
        if ps.judge_score is not None:
            judge_scores.append(ps.judge_score)

    print("=" * 68)

    # 全局进度摘要
    pct = int(done / total * 100) if total else 0
    avg_judge = f"{sum(judge_scores) / len(judge_scores):.1f}" if judge_scores else "—"
    print(f"\n  进度: {done}/{total} ({pct}%) | 总耗时: {total_duration:.0f}s | 平均质量分: {avg_judge}")

    available = get_available_phases(state)
    if available:
        groups = get_parallel_groups(state)
        print("\n  可执行:")
        for group in groups:
            if len(group) > 1:
                names = " + ".join(f"{pid}({PHASE_DEFS[pid]['name']})" for pid in group)
                print(f"    [并行] {names}")
            else:
                print(f"    qualix-run {state.project_id} execute {group[0]}")
    else:
        all_done = all(state.phases[pid].status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED) for pid in PHASE_ORDER)
        print("\n  所有 Phase 已完成!" if all_done else "\n  无可执行的 Phase（检查前置依赖）")


def cmd_status(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.core.profiles import get_profile

    state = load_state(output_dir, args.project_id)
    if getattr(args, "profile", None):
        state.profile_id = get_profile(args.profile).profile_id
        save_state(output_dir, state)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="status",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={
                    "state": state.model_dump(mode="json"),
                    "available_phases": get_available_phases(state),
                    "parallel_groups": get_parallel_groups(state),
                },
            )
        )
        return 0
    print_status(state, output_dir)
    return 0


def cmd_next(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    state = load_state(output_dir, args.project_id)
    groups = get_parallel_groups(state)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="next",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"parallel_groups": groups},
            )
        )
        return 0
    if not groups:
        print("  无可执行的 Phase")
        return 0
    for group in groups:
        if len(group) > 1:
            print("  [可并行]")
            for pid in group:
                print(f"    qualix-run {args.project_id} execute {pid}  # {PHASE_DEFS[pid]['name']}")
        else:
            pid = group[0]
            print(f"  qualix-run {args.project_id} execute {pid}  # {PHASE_DEFS[pid]['name']}")
    return 0


def cmd_detail(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    state = load_state(output_dir, args.project_id)
    phase_id = args.phase
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="detail",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=phase_id,
                    extra={"error": "unknown_phase"},
                )
            )
        else:
            print(f"  ERROR: 未知的 Phase: {phase_id}", file=sys.stderr)
        return 1

    ps = state.phases[phase_id]
    if cli_json_mode(args):
        phase_dir = _phase_dir(output_dir, args.project_id, phase_def)
        deliverables = phase_def.get("deliverables", [])
        files_status: list[dict] = []
        for d in deliverables:
            filename = d.split("—")[0].strip().split(" ")[0].strip()
            filepath = phase_dir / filename
            files_status.append(
                {
                    "spec": d,
                    "filename": filename,
                    "exists": filepath.exists(),
                    "bytes": filepath.stat().st_size if filepath.exists() else None,
                }
            )
        print_cli_json(
            cli_envelope(
                command="detail",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                phase_id=phase_id,
                extra={
                    "phase_state": ps.model_dump(mode="json"),
                    "deliverables": files_status,
                },
            )
        )
        return 0
    print()
    print("=" * 60)
    print(f"  Phase {phase_id} — {phase_def['name']}")
    print("=" * 60)

    print(f"\n  状态: {ps.status}")
    if ps.started_at:
        print(f"  开始: {ps.started_at[:19]}")
    if ps.finished_at:
        print(f"  完成: {ps.finished_at[:19]}")
    if ps.duration_seconds:
        print(f"  耗时: {ps.duration_seconds:.0f}s")
    if ps.comment:
        print(f"  备注: {ps.comment}")

    phase_dir = _phase_dir(output_dir, args.project_id, phase_def)
    deliverables = phase_def.get("deliverables", [])
    if deliverables:
        print("\n  交付物:")
        for d in deliverables:
            filename = d.split("—")[0].strip().split(" ")[0].strip()
            filepath = phase_dir / filename
            exists = filepath.exists()
            size = f"({filepath.stat().st_size} bytes)" if exists else "(未找到)"
            print(f"    {'✓' if exists else '✗'} {d} {size}")

    from qualix.path_utils import resolve_internal_file

    inputs_path = resolve_internal_file(phase_dir, "_inputs.json")
    if inputs_path.exists():
        inputs = load_json_strict(inputs_path)
        if inputs:
            print("\n  输入记录:")
            for key, value in inputs.items():
                print(f"    {key}: {value}")

    if ps.validation_errors:
        print(f"\n  校验问题 ({len(ps.validation_errors)}):")
        for err in ps.validation_errors[:5]:
            print(f"    - {err}")
    elif ps.status == PhaseStatus.APPROVED:
        print("\n  校验: PASS")

    print()
    print("=" * 60)
    return 0


def cmd_log(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.reporting.telemetry import load_records, print_run_summary

    if cli_json_mode(args):
        records = load_records(output_dir, args.project_id)
        print_cli_json(
            cli_envelope(
                command="log",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"records": [r.model_dump(mode="json") for r in records]},
            )
        )
        return 0
    print_run_summary(output_dir, args.project_id)
    return 0


def cmd_startup(args, output_dir: Path) -> int:
    state = load_state(output_dir, args.project_id)
    available = get_available_phases(state)
    groups = get_parallel_groups(state)

    menu_items = []
    for phase_id in PHASE_ORDER:
        ps = state.phases[phase_id]
        phase_def = PHASE_DEFS[phase_id]
        menu_items.append(
            {
                "phase_id": phase_id,
                "name": phase_def["name"],
                "status": ps.status.value,
                "icon": STATUS_ICONS.get(ps.status, "?"),
                "available": phase_id in available,
                "skippable": phase_def.get("skippable", False),
                "skip_condition": phase_def.get("skip_condition", None),
                "skill": phase_def["skill"],
                "required_inputs": phase_def.get("required_inputs", []),
                "optional_inputs": phase_def.get("optional_inputs", []),
                "deliverables": phase_def.get("deliverables", []),
                "approve_checklist": phase_def.get("approve_checklist", []),
                "duration": f"{ps.duration_seconds:.0f}s" if ps.duration_seconds else None,
                "comment": ps.comment or None,
            }
        )

    all_done = all(state.phases[pid].status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED) for pid in PHASE_ORDER)

    # 全局进度统计
    total = len(PHASE_ORDER)
    done = sum(1 for pid in PHASE_ORDER if state.phases[pid].status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED))
    total_duration = sum(state.phases[pid].duration_seconds or 0.0 for pid in PHASE_ORDER)
    judge_scores = [state.phases[pid].judge_score for pid in PHASE_ORDER if state.phases[pid].judge_score is not None]
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None

    print(
        dump_json_str(
            {
                "project_id": args.project_id,
                "profile_id": state.profile_id,
                "all_done": all_done,
                "progress": {
                    "done": done,
                    "total": total,
                    "percent": int(done / total * 100) if total else 0,
                    "total_duration_seconds": round(total_duration, 1),
                    "avg_judge_score": round(avg_judge, 2) if avg_judge else None,
                },
                "menu": menu_items,
                "next_groups": [{"phases": g, "parallel": len(g) > 1} for g in groups],
                "shortcuts": {
                    "v": "详情模式（展示每个 Phase 的交付物和校验结果）",
                    "g": "全局进度（展示进度/耗时/质量分汇总）",
                    "数字": "选择要执行的阶段编号",
                },
            }
        )
    )

    # Session orientation：输出跨 session 进度摘要到 stderr（不影响 JSON stdout）
    try:
        from qualix.runtime.session_startup import format_orientation, session_startup

        orientation = session_startup(output_dir, args.project_id)
        if orientation:
            import sys

            print(format_orientation(orientation), file=sys.stderr)
    except Exception:
        from qualix.log import get_logger

        get_logger(__name__).warning("Session orientation 失败，不阻断 startup", exc_info=True)

    return 0
