"""反馈信任等级：离散权重（无半衰期公式），供聚合或排序使用."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from qualix.store import get_connection


class TrustLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# 离散权重：显式人工批准 > 自动合成/弱信号
TRUST_WEIGHT: dict[TrustLevel, float] = {
    TrustLevel.HIGH: 1.0,
    TrustLevel.MEDIUM: 0.65,
    TrustLevel.LOW: 0.35,
}


def trust_weight(level: TrustLevel | str) -> float:
    if isinstance(level, TrustLevel):
        return TRUST_WEIGHT[level]
    try:
        return TRUST_WEIGHT[TrustLevel(level)]
    except ValueError:
        return TRUST_WEIGHT[TrustLevel.MEDIUM]


def record_trust_event(
    output_dir: Path,
    *,
    project_id: str,
    phase_id: str,
    event_type: str,
    trust_level: TrustLevel | str,
    payload: dict[str, Any] | None = None,
) -> None:
    """写入一条信任事件（SQLite）."""
    tl = trust_level.value if isinstance(trust_level, TrustLevel) else str(trust_level)
    blob = json.dumps(payload or {}, ensure_ascii=False)
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO feedback_trust (project_id, phase_id, event_type, trust_level, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, phase_id, event_type, tl, blob, datetime.now(UTC).isoformat()),
        )


def recent_trust_summary(
    output_dir: Path,
    *,
    project_id: str,
    phase_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """最近事件列表（调试 / 报表）."""
    with get_connection(output_dir) as conn:
        if phase_id:
            rows = conn.execute(
                """SELECT event_type, trust_level, payload, created_at FROM feedback_trust
                   WHERE project_id=? AND phase_id=? ORDER BY id DESC LIMIT ?""",
                (project_id, phase_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT phase_id, event_type, trust_level, payload, created_at FROM feedback_trust
                   WHERE project_id=? ORDER BY id DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        raw = d.get("payload")
        if isinstance(raw, str):
            try:
                d["payload"] = json.loads(raw)
            except json.JSONDecodeError:
                d["payload"] = {}
        out.append(d)
    return out
