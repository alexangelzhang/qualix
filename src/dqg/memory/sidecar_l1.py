"""Memory Layer 1：轻量 per-phase 旁路（入队），重活交给 Garden."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dqg.constants import MEMORY_SIDECAR_QUEUE
from dqg.json_utils import save_json

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext


def enqueue_memory_sidecar(
    output_dir: Path,
    *,
    project_id: str,
    phase_id: str,
    fingerprint: str,
) -> None:
    """追加一条待 Garden 处理的任务（JSONL，幂等重跑可接受重复行）."""
    path = output_dir / MEMORY_SIDECAR_QUEUE
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "project_id": project_id,
        "phase_id": phase_id,
        "ts": datetime.now(UTC).isoformat(),
        "fingerprint": fingerprint,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def after_memory_index(ctx: ExecutionContext, index_result: dict[str, Any]) -> None:
    """memory_index handler 尾部：入队 + L1 标记."""
    if index_result.get("skipped"):
        return
    fp = str(index_result.get("signature") or "")
    enqueue_memory_sidecar(
        ctx.output_dir,
        project_id=ctx.project_id,
        phase_id=ctx.phase_id,
        fingerprint=fp,
    )
    vc = int(index_result.get("version_changes") or 0)
    write_l1_flags(ctx.internal_dir, pending_garden=vc > 0, fingerprint=fp)


def write_l1_flags(internal_dir: Path, *, pending_garden: bool, fingerprint: str) -> None:
    """标记本 phase 是否有版本变更等，供下游或人工查看."""
    internal_dir.mkdir(parents=True, exist_ok=True)
    save_json(
        internal_dir / "_memory_l1_flags.json",
        {
            "pending_garden": pending_garden,
            "fingerprint": fingerprint,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
