"""Telemetry 存储：插入、查询、JSONL 迁移."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.store.core import get_connection, row_to_dict


def insert_telemetry(output_dir: Path, record: dict[str, Any]) -> None:
    """插入一条 telemetry 记录."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO telemetry
            (project_id, phase_id, phase_name, action, status,
             started_at, finished_at, duration_seconds,
             validation_errors, comment, timestamp, os_type, python_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("project_id", ""),
                record.get("phase_id", ""),
                record.get("phase_name", ""),
                record.get("action", ""),
                record.get("status", ""),
                record.get("started_at"),
                record.get("finished_at"),
                record.get("duration_seconds"),
                dump_json_str(record.get("validation_errors", []), indent=None),
                record.get("comment", ""),
                record.get("timestamp", datetime.now().isoformat()),
                record.get("os_type", ""),
                record.get("python_version", ""),
            ),
        )


def query_telemetry(
    output_dir: Path,
    project_id: str | None = None,
    phase_id: str | None = None,
    action: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """查询 telemetry 记录."""
    conditions = []
    params: list[Any] = []
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)
    if phase_id:
        conditions.append("phase_id = ?")
        params.append(phase_id)
    if action:
        conditions.append("action = ?")
        params.append(action)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM telemetry {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def migrate_telemetry_jsonl(output_dir: Path) -> int:
    """将现有 telemetry JSONL 文件迁移到 SQLite（跳过已迁移的）."""
    with get_connection(output_dir) as conn:
        existing = conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
        if existing > 0:
            return 0

    count = 0
    jsonl_paths = list(output_dir.glob("*/*_telemetry.jsonl"))
    jsonl_paths += list(output_dir.glob("*_telemetry.jsonl"))
    for jsonl_path in jsonl_paths:
        for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    record = json.loads(line)
                    insert_telemetry(output_dir, record)
                    count += 1
                except (json.JSONDecodeError, sqlite3.IntegrityError):
                    continue
    return count
