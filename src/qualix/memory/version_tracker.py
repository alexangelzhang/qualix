"""需求版本追踪（Zep 时序知识图谱模式）.

PRD 更新时自动对比新旧版本，标记变更/新增/删除/过期的 REQ/BR/SE。
支持需求演进历史查询。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.json_utils import load_json
from qualix.store import get_connection


def track_version(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    current_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    """对比当前产物与上一版本，记录变更.

    Args:
        current_facts: 当前版本的 REQ/BR/SE/GAP/OPEN 列表
            每项需有 fact_id, fact_type, description

    Returns:
        变更摘要: added/modified/removed/unchanged 数量
    """
    now = datetime.now().isoformat()

    # 获取上一版本的活跃事实
    prev_facts = _get_active_facts(output_dir, project_id, phase_id)
    prev_map = {f["fact_id"]: f for f in prev_facts}
    curr_map = {f["fact_id"]: f for f in current_facts}

    changes = {"added": [], "modified": [], "removed": [], "unchanged": []}

    with get_connection(output_dir) as conn:
        # 检查新增和修改
        for fact_id, curr in curr_map.items():
            prev = prev_map.get(fact_id)
            if not prev:
                # 新增
                version = 1
                _insert_version(conn, project_id, phase_id, curr, version, "added", "", now)
                changes["added"].append(fact_id)
            elif curr.get("description", "") != prev.get("description", ""):
                # 修改
                version = prev.get("version", 1) + 1
                # 标记旧版本过期
                conn.execute(
                    "UPDATE requirement_versions SET status='superseded', valid_until=? WHERE project_id=? AND phase_id=? AND fact_id=? AND status='active'",
                    (now, project_id, phase_id, fact_id),
                )
                _insert_version(conn, project_id, phase_id, curr, version, "modified", prev.get("description", ""), now)
                changes["modified"].append(fact_id)
            else:
                changes["unchanged"].append(fact_id)

        # 检查删除
        for fact_id, _prev in prev_map.items():
            if fact_id not in curr_map:
                conn.execute(
                    "UPDATE requirement_versions SET status='removed', valid_until=? WHERE project_id=? AND phase_id=? AND fact_id=? AND status='active'",
                    (now, project_id, phase_id, fact_id),
                )
                changes["removed"].append(fact_id)

    return {
        "added": len(changes["added"]),
        "modified": len(changes["modified"]),
        "removed": len(changes["removed"]),
        "unchanged": len(changes["unchanged"]),
        "details": changes,
    }


def _insert_version(conn, project_id, phase_id, fact, version, change_type, prev_desc, valid_from):
    conn.execute(
        """INSERT INTO requirement_versions
        (project_id, phase_id, fact_id, fact_type, description, version, status, prev_description, change_type, valid_from)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
        (
            project_id,
            phase_id,
            fact.get("fact_id", ""),
            fact.get("fact_type", ""),
            fact.get("description", ""),
            version,
            prev_desc,
            change_type,
            valid_from,
        ),
    )


def _get_active_facts(output_dir: Path, project_id: str, phase_id: str) -> list[dict[str, Any]]:
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT fact_id, fact_type, description, version FROM requirement_versions WHERE project_id=? AND phase_id=? AND status='active'",
            (project_id, phase_id),
        ).fetchall()
        return [dict(r) for r in rows]


def get_fact_history(
    output_dir: Path,
    project_id: str,
    fact_id: str,
) -> list[dict[str, Any]]:
    """获取某个需求点的版本历史."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM requirement_versions WHERE project_id=? AND fact_id=? ORDER BY version",
            (project_id, fact_id),
        ).fetchall()
        return [dict(r) for r in rows]


def get_changes_since(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """获取某个时间点之后的所有变更."""
    with get_connection(output_dir) as conn:
        if since:
            rows = conn.execute(
                "SELECT * FROM requirement_versions WHERE project_id=? AND phase_id=? AND valid_from > ? ORDER BY valid_from",
                (project_id, phase_id, since),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requirement_versions WHERE project_id=? AND phase_id=? ORDER BY valid_from",
                (project_id, phase_id),
            ).fetchall()
        return [dict(r) for r in rows]


def extract_facts_from_json(json_path: Path) -> list[dict[str, Any]]:
    """从结构化 JSON 中提取所有事实."""
    data = load_json(json_path)
    if data is None:
        return []

    facts = []
    for req in data.get("requirements", []):
        facts.append(
            {
                "fact_id": req.get("req_id", ""),
                "fact_type": "REQ" if req.get("req_id", "").startswith("REQ") else "BR",
                "description": req.get("description", ""),
            }
        )
    for se in data.get("semantic_expectations", []):
        facts.append(
            {
                "fact_id": se.get("se_id", ""),
                "fact_type": "SE",
                "description": se.get("description", ""),
            }
        )
    for gap in data.get("gaps", []):
        facts.append(
            {
                "fact_id": gap.get("gap_id", ""),
                "fact_type": "GAP",
                "description": gap.get("description", ""),
            }
        )
    for op in data.get("open_items", []):
        facts.append(
            {
                "fact_id": op.get("open_id", ""),
                "fact_type": "OPEN",
                "description": op.get("question", "") or op.get("description", ""),
            }
        )
    return facts


def format_version_diff(diff: dict[str, Any]) -> str:
    """格式化版本差异报告."""
    lines = [
        "  需求版本追踪:",
        f"  新增: {diff['added']} | 修改: {diff['modified']} | 删除: {diff['removed']} | 不变: {diff['unchanged']}",
    ]
    details = diff.get("details", {})
    if details.get("modified"):
        lines.append(f"  修改项: {', '.join(details['modified'][:10])}")
    if details.get("removed"):
        lines.append(f"  删除项: {', '.join(details['removed'][:10])}")
    if details.get("added") and diff["added"] <= 10:
        lines.append(f"  新增项: {', '.join(details['added'][:10])}")
    return "\n".join(lines)
