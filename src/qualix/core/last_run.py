"""last_run.py — 记录最近一次 qualix-run 调用的 marker.

写入 .dqg/last-run.json（原子写），供 qualix-run doctor 读取。
若 .dqg/ 目录不存在则静默跳过，不污染非 DQG 工作区。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from qualix.json_utils import dump_json_str, load_json_strict

_LAST_RUN_RELATIVE = ".dqg/last-run.json"
_STDERR_TAIL_MAX = 4096


def write_last_run(
    project_root: Path,
    cmd: list[str],
    exit_code: int,
    stderr_tail: str,
) -> None:
    """Atomically write marker to .dqg/last-run.json, or skip if .dqg/ missing."""
    target_dir = project_root / ".dqg"
    if not target_dir.exists():
        return
    path = project_root / _LAST_RUN_RELATIVE
    tmp = path.with_suffix(".tmp")
    payload: dict[str, Any] = {
        "cmd": cmd,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "cwd": str(project_root),
        "exit_code": exit_code,
        "stderr_tail": stderr_tail[-_STDERR_TAIL_MAX:] if stderr_tail else "",
    }
    tmp.write_text(dump_json_str(payload))
    os.replace(tmp, path)


def read_last_run(project_root: Path) -> dict[str, Any] | None:
    """Read .dqg/last-run.json; return None if missing."""
    path = project_root / _LAST_RUN_RELATIVE
    if not path.exists():
        return None
    return load_json_strict(path)
