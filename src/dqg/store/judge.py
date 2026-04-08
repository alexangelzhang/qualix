"""Judge Results 存储：插入."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.store.core import get_connection


def insert_judge_result(output_dir: Path, result: dict[str, Any]) -> None:
    """插入一条 judge 评审结果."""
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO judge_results
            (project_id, phase_id, overall_score, precision_estimate,
             recall_estimate, dimensions, gate_checklist, top_issues,
             summary, judged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.get("project_id", ""),
                result.get("phase_id", ""),
                result.get("overall_score"),
                result.get("precision_estimate"),
                result.get("recall_estimate"),
                json.dumps(result.get("dimensions", []), ensure_ascii=False),
                json.dumps(result.get("gate_checklist", []), ensure_ascii=False),
                json.dumps(result.get("top_issues", []), ensure_ascii=False),
                result.get("summary", ""),
                result.get("judged_at", datetime.now().isoformat()),
            ),
        )
