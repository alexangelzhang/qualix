"""Experiments 存储：插入、更新、查询、汇总."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dqg.store.core import get_connection, row_to_dict


def insert_experiment(output_dir: Path, record: dict[str, Any]) -> None:
    """插入一条实验记录."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO experiments
            (experiment_id, skill_file, phase_id, cycle, benchmark_case,
             prompt_diff, prompt_hash, judge_score, judge_dimensions,
             baseline_score, delta, accepted, reason,
             duration_seconds, token_count, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("experiment_id", ""),
                record.get("skill_file", ""),
                record.get("phase_id", ""),
                record.get("cycle", 0),
                record.get("benchmark_case", ""),
                record.get("prompt_diff", ""),
                record.get("prompt_hash", ""),
                record.get("judge_score"),
                json.dumps(record.get("judge_dimensions", {}), ensure_ascii=False),
                record.get("baseline_score"),
                record.get("delta"),
                1 if record.get("accepted") else 0,
                record.get("reason", ""),
                record.get("duration_seconds"),
                record.get("token_count"),
                record.get("started_at", ""),
                record.get("finished_at"),
            ),
        )


def update_experiment(output_dir: Path, experiment_id: str, updates: dict[str, Any]) -> None:
    """更新实验记录."""
    allowed = {"judge_score", "judge_dimensions", "delta", "accepted", "reason", "finished_at", "duration_seconds", "token_count"}
    sets = []
    params: list[Any] = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "judge_dimensions":
            v = json.dumps(v, ensure_ascii=False)
        if k == "accepted":
            v = 1 if v else 0
        sets.append(f"{k} = ?")
        params.append(v)

    if not sets:
        return
    params.append(experiment_id)
    with get_connection(output_dir) as conn:
        conn.execute(f"UPDATE experiments SET {', '.join(sets)} WHERE experiment_id = ?", params)


def query_experiments(
    output_dir: Path,
    skill_file: str | None = None,
    phase_id: str | None = None,
    accepted_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """查询实验记录."""
    conditions = []
    params: list[Any] = []
    if skill_file:
        conditions.append("skill_file = ?")
        params.append(skill_file)
    if phase_id:
        conditions.append("phase_id = ?")
        params.append(phase_id)
    if accepted_only:
        conditions.append("accepted = 1")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM experiments {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_experiment_summary(output_dir: Path, skill_file: str) -> dict[str, Any]:
    """获取某个 skill 的实验汇总."""
    with get_connection(output_dir) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM experiments WHERE skill_file = ?", (skill_file,)
        ).fetchone()[0]
        accepted = conn.execute(
            "SELECT COUNT(*) FROM experiments WHERE skill_file = ? AND accepted = 1", (skill_file,)
        ).fetchone()[0]
        best = conn.execute(
            "SELECT MAX(judge_score) FROM experiments WHERE skill_file = ?", (skill_file,)
        ).fetchone()[0]
        latest = conn.execute(
            "SELECT judge_score, delta, accepted, reason FROM experiments WHERE skill_file = ? ORDER BY created_at DESC LIMIT 1",
            (skill_file,),
        ).fetchone()

        return {
            "skill_file": skill_file,
            "total_experiments": total,
            "accepted_count": accepted,
            "acceptance_rate": accepted / max(total, 1),
            "best_score": best,
            "latest": row_to_dict(latest) if latest else None,
        }
