"""Dashboard 聚合查询：项目汇总、项目列表、质量趋势."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.store.core import get_connection, row_to_dict


def get_project_summary(output_dir: Path, project_id: str) -> dict[str, Any]:
    """获取项目级汇总（看板用）."""
    with get_connection(output_dir) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE project_id = ? AND action = 'finalize'",
            (project_id,),
        ).fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE project_id = ? AND action = 'approve'",
            (project_id,),
        ).fetchone()[0]

        avg_duration = conn.execute(
            "SELECT AVG(duration_seconds) FROM telemetry WHERE project_id = ? AND action = 'finalize' AND duration_seconds IS NOT NULL",
            (project_id,),
        ).fetchone()[0]

        open_cases = conn.execute(
            "SELECT COUNT(*) FROM bug_cases WHERE status = 'open'",
        ).fetchone()[0]

        latest_judge = conn.execute(
            "SELECT phase_id, overall_score FROM judge_results WHERE project_id = ? ORDER BY judged_at DESC LIMIT 6",
            (project_id,),
        ).fetchall()

        return {
            "project_id": project_id,
            "phase_approval_rate": approved / max(total, 1),
            "total_finalized": total,
            "total_approved": approved,
            "avg_duration_seconds": round(avg_duration or 0, 1),
            "open_bug_cases": open_cases,
            "latest_judge_scores": {r["phase_id"]: r["overall_score"] for r in latest_judge},
        }


def get_all_projects(output_dir: Path) -> list[str]:
    """获取所有项目 ID."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT DISTINCT project_id FROM telemetry ORDER BY project_id",
        ).fetchall()
        return [r["project_id"] for r in rows]


def get_quality_trend(
    output_dir: Path,
    project_id: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """获取质量趋势数据（看板用）."""
    conditions = ["timestamp >= datetime('now', ?)"]
    params: list[Any] = [f"-{days} days"]
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)

    where = f"WHERE {' AND '.join(conditions)}"

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"""SELECT date(timestamp) as day, action,
                COUNT(*) as count,
                AVG(duration_seconds) as avg_duration
            FROM telemetry {where}
            GROUP BY day, action
            ORDER BY day""",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# P2 新增查询：Token 消耗、事件时间线、Phase 质量评分
# ---------------------------------------------------------------------------


def get_token_consumption(output_dir: Path, project_id: str | None = None) -> list[dict[str, Any]]:
    """按 Phase 聚合 token 消耗和成本."""
    conditions: list[str] = []
    params: list[Any] = []
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)

    conditions.append(
        "metric_name IN ('input_tokens', 'output_tokens', 'total_tokens', 'cost_estimate_usd', 'tokens_per_second')"
    )
    where = f"WHERE {' AND '.join(conditions)}"

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"""SELECT project_id, phase_id, metric_name, metric_value, timestamp
            FROM metrics {where}
            ORDER BY timestamp""",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_phase_durations(output_dir: Path, project_id: str) -> list[dict[str, Any]]:
    """获取项目各 Phase 的耗时（瀑布图用）."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT phase_id, phase_name, action, status,
                duration_seconds, started_at, finished_at, timestamp
            FROM telemetry
            WHERE project_id = ? AND action IN ('finalize', 'approve', 'skip')
            ORDER BY timestamp""",
            (project_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_event_timeline(output_dir: Path, project_id: str, phase_id: str | None = None) -> list[dict[str, Any]]:
    """获取事件时间线."""
    conditions = ["project_id = ?"]
    params: list[Any] = [project_id]
    if phase_id:
        conditions.append("phase_id = ?")
        params.append(phase_id)

    where = f"WHERE {' AND '.join(conditions)}"
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM events {where} ORDER BY id ASC LIMIT 500",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_phase_scores(output_dir: Path, project_id: str) -> list[dict[str, Any]]:
    """获取项目各 Phase 的 Judge 评分."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT phase_id, overall_score, dimensions, judged_at
            FROM judge_results
            WHERE project_id = ?
            ORDER BY judged_at DESC""",
            (project_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
