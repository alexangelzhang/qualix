"""Judge Results 存储：插入."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.json_utils import dump_json_str
from qualix.store.core import get_connection


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
                dump_json_str(result.get("dimensions", []), indent=None),
                dump_json_str(result.get("gate_checklist", []), indent=None),
                dump_json_str(result.get("top_issues", []), indent=None),
                result.get("summary", ""),
                result.get("judged_at", datetime.now().isoformat()),
            ),
        )
