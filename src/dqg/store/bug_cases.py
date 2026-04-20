"""Bug Cases 存储：upsert、查询."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.store.core import get_connection, row_to_dict


def upsert_bug_case(output_dir: Path, case: dict[str, Any]) -> None:
    """插入或更新一条 bug case."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO bug_cases
            (case_id, phase, error_type, severity, title, root_cause,
             fix_target, tags, status, source, expected, actual, lesson, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                status=excluded.status, severity=excluded.severity,
                lesson=excluded.lesson, updated_at=datetime('now')""",
            (
                case.get("case_id", ""),
                case.get("phase", ""),
                case.get("error_type", ""),
                case.get("severity", "medium"),
                case.get("title", ""),
                case.get("root_cause", ""),
                case.get("fix_target", ""),
                dump_json_str(case.get("tags", []), indent=None),
                case.get("status", "open"),
                dump_json_str(case.get("source", {}), indent=None),
                dump_json_str(case.get("expected", {}), indent=None),
                dump_json_str(case.get("actual", {}), indent=None),
                case.get("lesson", ""),
                case.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            ),
        )


def query_bug_cases(
    output_dir: Path,
    phase: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """查询 bug cases."""
    conditions = []
    params: list[Any] = []
    if phase:
        conditions.append("phase = ?")
        params.append(phase)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM bug_cases {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]
