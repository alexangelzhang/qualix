"""Metrics 存储：插入、查询."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.json_utils import dump_json_str
from qualix.store.core import get_connection, row_to_dict


def insert_metric(output_dir: Path, record: dict[str, Any]) -> None:
    """插入一条指标记录."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO metrics
            (project_id, phase_id, metric_name, metric_value,
             metric_data, period, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("project_id", ""),
                record.get("phase_id"),
                record.get("metric_name", ""),
                record.get("metric_value"),
                dump_json_str(record.get("metric_data", {}), indent=None),
                record.get("period", "daily"),
                record.get("timestamp", datetime.now().isoformat()),
            ),
        )


def query_metrics(
    output_dir: Path,
    project_id: str | None = None,
    metric_name: str | None = None,
    period: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """查询指标记录."""
    conditions = []
    params: list[Any] = []
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)
    if metric_name:
        conditions.append("metric_name = ?")
        params.append(metric_name)
    if period:
        conditions.append("period = ?")
        params.append(period)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM metrics {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]
