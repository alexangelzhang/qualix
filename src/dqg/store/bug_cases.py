"""Bug Cases 存储：upsert、查询、压缩."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.store.core import get_connection, row_to_dict

COMPRESS_THRESHOLD = 5000  # 触发压缩的条目数上限
COMPRESS_TARGET = 4000  # 压缩后保留的目标条目数
_DECAY_HALF_LIFE_DAYS = 180.0  # 时间衰减半衰期（天）
_SEVERITY_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}
_STATUS_WEIGHT = {"open": 1.5, "resolved": 1.0, "wont_fix": 0.5}


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


def compress_bug_cases(
    output_dir: Path,
    threshold: int = COMPRESS_THRESHOLD,
    keep: int = COMPRESS_TARGET,
) -> dict[str, int]:
    """当 bug case 总数超过 threshold 时，按衰减评分淘汰低价值案例.

    评分 = severity_weight × time_decay × status_weight
    保护规则：status='open' 案例优先保留，不率先淘汰。

    Returns:
        {"total_before": N, "deleted": M, "total_after": K}
    """
    with get_connection(output_dir) as conn:
        total = conn.execute("SELECT COUNT(*) FROM bug_cases").fetchone()[0]
        if total <= threshold:
            return {"total_before": total, "deleted": 0, "total_after": total}

        to_delete = total - keep
        now = datetime.now(tz=UTC)

        rows = conn.execute("SELECT case_id, severity, status, created_at FROM bug_cases").fetchall()

        scored: list[tuple[float, str, str]] = []
        for row in rows:
            case_id, severity, status, created_at_str = row
            sev_w = _SEVERITY_WEIGHT.get((severity or "medium").lower(), 2.0)
            stat_w = _STATUS_WEIGHT.get((status or "open").lower(), 1.0)
            try:
                created = datetime.fromisoformat(created_at_str).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                created = now
            age_days = max(0.0, (now - created).total_seconds() / 86400)
            decay = math.exp(-math.log(2) / _DECAY_HALF_LIFE_DAYS * age_days)
            score = sev_w * decay * stat_w
            scored.append((score, case_id, status or "open"))

        # 非 open 案例优先淘汰，同等条件下评分低的先删
        scored.sort(key=lambda x: (x[2] == "open", x[0]))
        delete_ids = [case_id for _, case_id, _ in scored[:to_delete]]

        conn.executemany(
            "DELETE FROM bug_cases WHERE case_id = ?",
            [(cid,) for cid in delete_ids],
        )
        deleted = len(delete_ids)
        return {"total_before": total, "deleted": deleted, "total_after": total - deleted}


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
