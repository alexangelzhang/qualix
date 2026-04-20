"""Preferences 存储：插入、查询、JSONL 迁移."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.store.core import get_connection, row_to_dict


def insert_preference(output_dir: Path, record: dict[str, Any]) -> None:
    """插入一条偏好记录."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO preferences
            (project_id, phase_id, preferred, confidence,
             dimensions, critique_effectiveness, summary, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("project_id", ""),
                record.get("phase_id", ""),
                record.get("preferred", ""),
                record.get("confidence", ""),
                dump_json_str(record.get("dimensions", {}), indent=None),
                dump_json_str(record.get("critique_effectiveness", []), indent=None),
                record.get("summary", ""),
                record.get("timestamp", datetime.now().isoformat()),
            ),
        )


def query_preferences(
    output_dir: Path,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """查询偏好记录."""
    if project_id:
        sql = "SELECT * FROM preferences WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?"
        params: list[Any] = [project_id, limit]
    else:
        sql = "SELECT * FROM preferences ORDER BY timestamp DESC LIMIT ?"
        params = [limit]

    with get_connection(output_dir) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]


def migrate_preference_jsonl(base_dir: Path, output_dir: Path) -> int:
    """将现有 preference JSONL 迁移到 SQLite."""
    pref_path = base_dir / "regression" / "preference_history.jsonl"
    if not pref_path.exists():
        return 0
    count = 0
    for line in pref_path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                record = json.loads(line)
                insert_preference(output_dir, record)
                count += 1
            except (json.JSONDecodeError, sqlite3.IntegrityError):
                continue
    return count
