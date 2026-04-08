"""Telemetry: Phase 执行的可观测性记录.

每次 Phase 执行记录一条结构化 log，追加到 output/<project_id>_telemetry.jsonl。
"""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, Field


class PhaseRunRecord(BaseModel):
    """单次 Phase 执行记录."""

    project_id: str
    phase_id: str
    phase_name: str = ""
    action: str = ""  # execute / finalize / approve / skip
    status: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    validation_errors: list[str] = Field(default_factory=list)
    comment: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    os_type: str = Field(default_factory=lambda: platform.system())
    python_version: str = Field(default_factory=platform.python_version)


def _telemetry_path(output_dir: Path, project_id: str) -> Path:
    """telemetry 文件存放在 output/{project_id}/ 子目录下."""
    proj_dir = output_dir / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    return proj_dir / f"{project_id}_telemetry.jsonl"


def append_record(output_dir: Path, record: PhaseRunRecord) -> Path:
    """追加一条 telemetry 记录到 JSONL 文件 + SQLite."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _telemetry_path(output_dir, record.project_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")

    # 同步写入 SQLite
    try:
        from dqg.store import insert_telemetry
        insert_telemetry(output_dir, record.model_dump())
    except Exception:
        pass  # SQLite 写入失败不阻断主流程

    return path


def load_records(output_dir: Path, project_id: str) -> list[PhaseRunRecord]:
    """加载项目的所有 telemetry 记录."""
    path = _telemetry_path(output_dir, project_id)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            records.append(PhaseRunRecord.model_validate(json.loads(line)))
    return records


def print_run_summary(output_dir: Path, project_id: str) -> None:
    """打印项目执行摘要."""
    records = load_records(output_dir, project_id)
    if not records:
        print("  无 telemetry 记录")
        return

    print()
    print("=" * 64)
    print(f"  执行记录 — {project_id}")
    print("=" * 64)
    print(f"  {'Phase':<8} {'Action':<12} {'Status':<16} {'Duration':<12} {'Time'}")
    print("-" * 64)

    for r in records:
        duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else "—"
        time_str = r.timestamp[:19] if r.timestamp else "—"
        print(f"  {r.phase_id:<8} {r.action:<12} {r.status:<16} {duration:<12} {time_str}")

    print("=" * 64)

    # 汇总
    approvals = [r for r in records if r.action == "approve"]
    total_duration = sum(r.duration_seconds or 0 for r in records if r.duration_seconds)
    errors = [r for r in records if r.validation_errors]

    print(f"\n  已完成: {len(approvals)} phases | 总耗时: {total_duration:.0f}s | 校验问题: {len(errors)} phases")
