"""Phase reset command: archive or clean phase artifacts."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Final

from dqg.core.state_machine import (
    PHASE_DEFS,
    PHASE_ORDER,
    load_state,
    reset_phase,
    save_state,
)

# 产出物目录中需要保留的子目录（输入上下文，不是产出物）
_KEEP_DIRS: Final = frozenset({"_internal", "ingest"})


def _archive_artifacts(phase_path: Path) -> tuple[int, str | None]:
    """将产出物归档到 _archive/vN/ 目录.

    Returns:
        (archived_count, archive_dir_name | None)
    """
    if not phase_path.exists():
        return 0, None

    archive_root = phase_path / "_archive"
    archive_root.mkdir(exist_ok=True)
    existing = sorted(
        (d for d in archive_root.iterdir() if d.is_dir() and d.name.startswith("v")),
        key=lambda d: d.name,
    )
    next_ver = len(existing) + 1
    archive_dir = archive_root / f"v{next_ver}"
    archive_dir.mkdir()

    count = 0
    for item in phase_path.iterdir():
        if item.name in _KEEP_DIRS or item.name == "_archive":
            continue
        dest = archive_dir / item.name
        shutil.move(str(item), str(dest))
        count += 1

    if count == 0:
        archive_dir.rmdir()
        return 0, None

    return count, f"_archive/v{next_ver}"


def _clean_artifacts(phase_path: Path) -> int:
    """直接删除产出物（保留 _internal/ingest/_archive）."""
    if not phase_path.exists():
        return 0

    count = 0
    for item in phase_path.iterdir():
        if item.name in _KEEP_DIRS or item.name == "_archive":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
        count += 1
    return count


def cmd_reset(args, output_dir: Path) -> int:
    from dqg.commands.phase import _telemetry
    from dqg.core.state_machine import phase_dir_by_id

    state = load_state(output_dir, args.project_id)
    clean = getattr(args, "clean", False)
    cascade = getattr(args, "cascade", False)

    phases_to_reset = [args.phase]
    if cascade:
        try:
            idx = PHASE_ORDER.index(args.phase)
            phases_to_reset = PHASE_ORDER[idx:]
        except ValueError:
            phases_to_reset = [args.phase]

    reset_results = []
    for pid in phases_to_reset:
        errors = reset_phase(state, pid)
        if errors:
            for e in errors:
                print(f"  WARNING: {e}", file=sys.stderr)
            continue

        phase_path = phase_dir_by_id(output_dir, args.project_id, pid)
        if clean:
            removed = _clean_artifacts(phase_path)
            reset_results.append((pid, "deleted", removed, None))
        else:
            archived, archive_name = _archive_artifacts(phase_path)
            reset_results.append((pid, "archived", archived, archive_name))

    save_state(output_dir, state)

    PhaseRunRecord, append_record, _ = _telemetry()
    for pid, action_type, count, archive_name in reset_results:
        append_record(
            output_dir,
            PhaseRunRecord(
                project_id=args.project_id,
                phase_id=pid,
                phase_name=PHASE_DEFS[pid]["name"],
                action="reset",
                status="not_started",
                comment=f"{action_type}: {count} files" + (f" → {archive_name}" if archive_name else ""),
            ),
        )

    print("\n  Reset 完成:")
    for pid, action_type, count, archive_name in reset_results:
        if action_type == "archived" and archive_name:
            print(f"    Phase {pid}: {count} 个产出物已归档到 {archive_name}")
        elif action_type == "deleted":
            print(f"    Phase {pid}: {count} 个产出物已删除")
        else:
            print(f"    Phase {pid}: 状态已重置（无产出物）")

    return 0
