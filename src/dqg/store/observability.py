"""Observe alerts 存储：写入 + 查询."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.store.core import get_connection, row_to_dict


def insert_observe_alerts(
    output_dir: Path,
    label: str,
    alerts: list[dict[str, Any]],
) -> int:
    """批量写入 observe 告警到 SQLite，返回插入行数."""
    if not alerts:
        return 0
    with get_connection(output_dir) as conn:
        # 同一 label 先清除旧告警（幂等）
        conn.execute("DELETE FROM observe_alerts WHERE label = ?", (label,))
        for a in alerts:
            conn.execute(
                """INSERT INTO observe_alerts
                   (label, severity, rule, project_id, phase, message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    label,
                    a.get("severity", "MEDIUM"),
                    a.get("rule", ""),
                    a.get("project_id", ""),
                    a.get("phase", ""),
                    a.get("message", ""),
                ),
            )
    return len(alerts)


def query_observe_alerts(
    output_dir: Path,
    *,
    label: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """查询 observe 告警."""
    conditions: list[str] = []
    params: list[Any] = []
    if label:
        conditions.append("label = ?")
        params.append(label)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM observe_alerts {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_latest_observe_alerts(output_dir: Path, limit: int = 50) -> list[dict[str, Any]]:
    """获取最近的 observe 告警（dashboard 用）."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM observe_alerts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
