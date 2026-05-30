"""Coverage 趋势追踪：每次 finalize 保存覆盖率快照，支持趋势查询."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qualix.json_utils import dump_json_str
from qualix.store.core import get_connection

if TYPE_CHECKING:
    from qualix.schemas.rsm import CoverageReport


def _ensure_table(output_dir: Path) -> None:
    """确保 coverage_snapshots 表存在."""
    with get_connection(output_dir) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS coverage_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                phase_id TEXT NOT NULL,
                req_coverage_rate REAL DEFAULT 0,
                se_coverage_rate REAL DEFAULT 0,
                test_coverage_rate REAL DEFAULT 0,
                review_coverage_rate REAL DEFAULT 0,
                gap_closure_rate REAL DEFAULT 0,
                open_closure_rate REAL DEFAULT 0,
                total_reqs INTEGER DEFAULT 0,
                total_ses INTEGER DEFAULT 0,
                total_gaps INTEGER DEFAULT 0,
                total_opens INTEGER DEFAULT 0,
                details_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_coverage_project_phase
            ON coverage_snapshots(project_id, phase_id, created_at)
        """)


def save_coverage_snapshot(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    coverage_report: CoverageReport,
) -> None:
    """保存一次覆盖率快照."""
    _ensure_table(output_dir)
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO coverage_snapshots
            (project_id, phase_id, req_coverage_rate, se_coverage_rate,
             test_coverage_rate, review_coverage_rate, gap_closure_rate,
             open_closure_rate, total_reqs, total_ses, total_gaps, total_opens,
             details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                phase_id,
                coverage_report.req_coverage_rate,
                coverage_report.se_coverage_rate,
                coverage_report.test_coverage_rate,
                coverage_report.review_coverage_rate,
                coverage_report.gap_closure_rate,
                coverage_report.open_closure_rate,
                coverage_report.total_reqs,
                coverage_report.total_ses,
                coverage_report.total_gaps,
                coverage_report.total_opens,
                dump_json_str(coverage_report.to_dict(), indent=None),
                time.time(),
            ),
        )


def query_coverage_trend(
    output_dir: Path,
    project_id: str,
    phase_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """查询覆盖率趋势（按时间倒序）."""
    _ensure_table(output_dir)
    conditions = ["project_id = ?"]
    params: list[Any] = [project_id]
    if phase_id:
        conditions.append("phase_id = ?")
        params.append(phase_id)
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"""SELECT * FROM coverage_snapshots
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC LIMIT ?""",
            params,
        ).fetchall()

    results = []
    for row in rows:
        results.append({
            "project_id": row["project_id"],
            "phase_id": row["phase_id"],
            "req_coverage_rate": row["req_coverage_rate"],
            "se_coverage_rate": row["se_coverage_rate"],
            "test_coverage_rate": row["test_coverage_rate"],
            "review_coverage_rate": row["review_coverage_rate"],
            "gap_closure_rate": row["gap_closure_rate"],
            "open_closure_rate": row["open_closure_rate"],
            "created_at": row["created_at"],
        })
    return results


def get_coverage_delta(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, float] | None:
    """计算最近两次覆盖率的变化量. 返回 None 如果不足两次."""
    trend = query_coverage_trend(output_dir, project_id, phase_id, limit=2)
    if len(trend) < 2:
        return None

    current, previous = trend[0], trend[1]
    delta = {}
    for key in ("req_coverage_rate", "se_coverage_rate", "test_coverage_rate",
                "review_coverage_rate", "gap_closure_rate", "open_closure_rate"):
        delta[key] = round(current[key] - previous[key], 4)
    return delta
