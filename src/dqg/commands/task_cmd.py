"""dqg-run <pid> task list|resume — Task 管理 CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("  (无记录)")
        return
    cols = ["id", "task_type", "project_id", "phase_id", "status", "created_at"]
    widths = {c: max(len(c), max((len(str(r.get(c, "") or "")) for r in rows), default=0)) for c in cols}
    header = "  " + "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  " + "  ".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        print("  " + "  ".join(str(row.get(c, "") or "").ljust(widths[c]) for c in cols))


def cmd_task(args, output_dir: Path) -> int:
    """dqg-run <pid> task list|resume."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.runtime.task_store import (
        get_latest_checkpoint,
        get_resumable_task,
        get_task_run,
        list_task_runs,
    )

    action = getattr(args, "task_action", "list") or "list"
    task_id = getattr(args, "task_id", None)
    use_json = cli_json_mode(args)

    if action == "list":
        status_filter = getattr(args, "status", "all")
        limit = getattr(args, "limit", 20)
        runs = list_task_runs(
            output_dir,
            project_id=args.project_id,
            status=None if status_filter == "all" else status_filter,
            limit=limit,
        )
        if use_json:
            print_cli_json(
                cli_envelope(
                    command="task list",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={"tasks": runs, "total": len(runs)},
                )
            )
        else:
            print(f"\n  Task runs（{args.project_id}）:")
            _print_table(runs)
        return 0

    if action == "resume":
        if task_id:
            task = get_task_run(output_dir, task_id)
            if not task:
                if not use_json:
                    print(f"  Task {task_id} 不存在", file=sys.stderr)
                return 1
            ckpt = get_latest_checkpoint(output_dir, task_id)
            if use_json:
                print_cli_json(
                    cli_envelope(
                        command="task resume",
                        project_id=args.project_id,
                        success=True,
                        exit_code=0,
                        extra={"task": task, "checkpoint": ckpt},
                    )
                )
            else:
                print(f"\n  Task: {task_id}")
                print(f"  类型: {task.get('task_type')}  Phase: {task.get('phase_id')}  状态: {task.get('status')}")
                if ckpt:
                    print(f"  最新 checkpoint: {ckpt.get('checkpoint_id')} ({ckpt.get('created_at', '')})")
                else:
                    print("  无 checkpoint")
            return 0
        else:
            task = get_resumable_task(output_dir, project_id=args.project_id)
            if not task:
                if not use_json:
                    print(f"\n  (无可恢复的 task，project={args.project_id})")
                return 0
            ckpt = get_latest_checkpoint(output_dir, task["id"])
            if use_json:
                print_cli_json(
                    cli_envelope(
                        command="task resume",
                        project_id=args.project_id,
                        success=True,
                        exit_code=0,
                        extra={"task": task, "checkpoint": ckpt},
                    )
                )
            else:
                print(f"\n  可恢复任务: {task['id']}")
                print(f"  类型: {task.get('task_type')}  Phase: {task.get('phase_id')}  状态: {task.get('status')}")
                if ckpt:
                    print(f"  最新 checkpoint: {ckpt.get('checkpoint_id')} ({ckpt.get('created_at', '')})")
                    print(
                        f"  恢复命令: dqg-run {args.project_id} adaptive"
                        f" {task.get('phase_id', '')} --resume {task['id']}"
                    )
            return 0

    print(f"  未知 task action: {action}", file=sys.stderr)
    return 1
