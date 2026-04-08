"""结构化事实缓存：将 Phase 产物中的 SE/GAP/OPEN 存入 SQLite FTS5.

搜索"并发"直接返回相关 SE/GAP，不需要读整个报告。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from dqg.constants import STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.store import get_connection
from dqg.text_utils import build_fts_query, row_to_dict, text_query_has_signal, tokenize_chinese

if TYPE_CHECKING:
    from pathlib import Path


def index_phase_facts(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> int:
    """从结构化 JSON 中提取 SE/GAP/OPEN 存入 FTS5 索引."""

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return 0

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return 0

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_path = pd / json_file
    if not json_path.exists():
        return 0

    data = load_json(json_path)
    if data is None:
        return 0

    count = 0

    with get_connection(output_dir) as conn:
        conn.execute(
            "DELETE FROM structured_facts WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        )

        for se in data.get("semantic_expectations", []):
            se_id = se.get("se_id", "")
            desc = se.get("description", "")
            target = se.get("mapping_target", "")
            _insert_fact(conn, project_id, phase_id, "SE", se_id, desc, [target] if target else [])
            count += 1

        for gap in data.get("gaps", []):
            gap_id = gap.get("gap_id", "")
            desc = gap.get("description", "")
            related = gap.get("related_ids", [])
            _insert_fact(conn, project_id, phase_id, "GAP", gap_id, desc, related)
            count += 1

        for op in data.get("open_items", []):
            open_id = op.get("open_id", "")
            desc = op.get("question", "") or op.get("description", "")
            related = op.get("related_ids", [])
            _insert_fact(conn, project_id, phase_id, "OPEN", open_id, desc, related)
            count += 1

        for req in data.get("requirements", []):
            req_id = req.get("req_id", "")
            desc = req.get("description", "")
            parent = req.get("parent_id", "")
            _insert_fact(
                conn,
                project_id,
                phase_id,
                "REQ" if req_id.startswith("REQ") else "BR",
                req_id,
                desc,
                [parent] if parent else [],
            )
            count += 1

    return count


def _insert_fact(conn, project_id, phase_id, fact_type, fact_id, description, related_ids):
    """插入一条事实并同步 FTS5."""
    related_str = json.dumps(related_ids, ensure_ascii=False)
    conn.execute(
        """INSERT INTO structured_facts (project_id, phase_id, fact_type, fact_id, description, related_ids)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, phase_id, fact_id) DO UPDATE SET
            description=excluded.description, related_ids=excluded.related_ids""",
        (project_id, phase_id, fact_type, fact_id, description, related_str),
    )
    row = conn.execute(
        "SELECT id FROM structured_facts WHERE project_id=? AND phase_id=? AND fact_id=?",
        (project_id, phase_id, fact_id),
    ).fetchone()
    if row:
        tokenized_desc = tokenize_chinese(f"{fact_id} {description}")
        tokenized_related = tokenize_chinese(related_str)
        conn.execute(
            "INSERT OR REPLACE INTO structured_facts_fts(rowid, fact_id, description, related_ids) VALUES (?, ?, ?, ?)",
            (row[0], tokenize_chinese(fact_id), tokenized_desc, tokenized_related),
        )


def search_facts(
    output_dir: Path,
    query: str,
    project_id: str | None = None,
    fact_type: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """搜索结构化事实."""
    results = []
    for mode in ("AND", "OR"):
        fts_query = build_fts_query(query, mode=mode)
        if not fts_query:
            break

        conditions = []
        params: list[Any] = [fts_query]
        if project_id:
            conditions.append("s.project_id = ?")
            params.append(project_id)
        if fact_type:
            conditions.append("s.fact_type = ?")
            params.append(fact_type)
        where = f"AND {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with get_connection(output_dir) as conn:
            rows = conn.execute(
                f"""SELECT s.* FROM structured_facts s
                JOIN structured_facts_fts f ON s.id = f.rowid
                WHERE structured_facts_fts MATCH ? {where}
                ORDER BY rank LIMIT ?""",
                params,
            ).fetchall()
            results = [row_to_dict(r) for r in rows]
            if results:
                break

    if results:
        filtered = []
        for row in results:
            candidate = f"{row.get('fact_id', '')} {row.get('description', '')} {row.get('related_ids', '')}"
            if text_query_has_signal(query, candidate):
                filtered.append(row)
        if filtered:
            results = filtered

    if not results:
        with get_connection(output_dir) as conn:
            conditions = ["description LIKE ?"]
            params = [f"%{query}%"]
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            if fact_type:
                conditions.append("fact_type = ?")
                params.append(fact_type)
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM structured_facts WHERE {' AND '.join(conditions)} LIMIT ?",
                params,
            ).fetchall()
            results = [row_to_dict(r) for r in rows]

    return results
