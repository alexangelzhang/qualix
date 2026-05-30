"""结构化事实缓存：将 Phase 产物中的 SE/GAP/OPEN 存入 SQLite FTS5.

搜索"并发"直接返回相关 SE/GAP，不需要读整个报告。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qualix.constants import STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import dump_json_str, load_json
from qualix.store import get_connection
from qualix.text_utils import build_fts_query, row_to_dict, text_query_has_signal, tokenize_chinese

if TYPE_CHECKING:
    from pathlib import Path


def index_phase_facts(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> int:
    """从结构化 JSON 中提取 SE/GAP/OPEN 存入 FTS5 索引（批量写入）."""

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

    # 收集所有 facts
    facts: list[tuple[str, str, str, str, str, str, str]] = []

    for se in data.get("semantic_expectations", []):
        se_id = se.get("se_id", "")
        desc = se.get("description", "")
        target = se.get("mapping_target", "")
        confidence = "EXTRACTED" if target else "INFERRED"
        related_str = dump_json_str([target] if target else [], indent=None)
        facts.append((project_id, phase_id, "SE", se_id, desc, related_str, confidence))

    for gap in data.get("gaps", []):
        gap_id = gap.get("gap_id", "")
        desc = gap.get("description", "")
        related_str = dump_json_str(gap.get("related_ids", []), indent=None)
        facts.append((project_id, phase_id, "GAP", gap_id, desc, related_str, "INFERRED"))

    for op in data.get("open_items", []):
        open_id = op.get("open_id", "")
        desc = op.get("question", "") or op.get("description", "")
        related_str = dump_json_str(op.get("related_ids", []), indent=None)
        facts.append((project_id, phase_id, "OPEN", open_id, desc, related_str, "AMBIGUOUS"))

    for req in data.get("requirements", []):
        req_id = req.get("req_id", "")
        desc = req.get("description", "")
        parent = req.get("parent_id", "")
        fact_type = "REQ" if req_id.startswith("REQ") else "BR"
        related_str = dump_json_str([parent] if parent else [], indent=None)
        facts.append((project_id, phase_id, fact_type, req_id, desc, related_str, "EXTRACTED"))

    if not facts:
        return 0

    with get_connection(output_dir) as conn:
        # 批量删除旧数据
        conn.execute(
            "DELETE FROM structured_facts WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        )

        # 批量插入主表
        conn.executemany(
            """INSERT INTO structured_facts (project_id, phase_id, fact_type, fact_id, description, related_ids, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, phase_id, fact_id) DO UPDATE SET
                description=excluded.description, related_ids=excluded.related_ids, confidence=excluded.confidence""",
            facts,
        )

        # 批量查询 rowid 并插入 FTS5
        rows = conn.execute(
            "SELECT id, fact_id, description, related_ids FROM structured_facts WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        ).fetchall()

        fts_data = [
            (row[0], tokenize_chinese(row[1]), tokenize_chinese(f"{row[1]} {row[2]}"), tokenize_chinese(row[3]))
            for row in rows
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO structured_facts_fts(rowid, fact_id, description, related_ids) VALUES (?, ?, ?, ?)",
            fts_data,
        )

    return len(facts)


def _insert_fact(conn, project_id, phase_id, fact_type, fact_id, description, related_ids, confidence="EXTRACTED"):
    """插入一条事实并同步 FTS5."""
    related_str = dump_json_str(related_ids, indent=None)
    conn.execute(
        """INSERT INTO structured_facts (project_id, phase_id, fact_type, fact_id, description, related_ids, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, phase_id, fact_id) DO UPDATE SET
            description=excluded.description, related_ids=excluded.related_ids, confidence=excluded.confidence""",
        (project_id, phase_id, fact_type, fact_id, description, related_str, confidence),
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


def count_facts(
    output_dir: Path,
    project_id: str | None = None,
) -> int:
    """统计结构化事实总数."""
    with get_connection(output_dir) as conn:
        if project_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM structured_facts WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM structured_facts").fetchone()
    return row[0] if row else 0


def export_facts_to_markdown(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """将指定 Phase 的结构化事实导出为 Markdown，纳入 git 追踪.

    输出路径：output/<project_id>/<phase_dir>/facts_export.md
    每次 finalize 后覆盖写入，git diff 可见变化。
    """
    from datetime import datetime

    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    phase_path = output_dir / project_id / dir_suffix
    phase_path.mkdir(parents=True, exist_ok=True)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT fact_type, fact_id, description, related_ids, confidence, created_at "
            "FROM structured_facts WHERE project_id=? AND phase_id=? ORDER BY fact_type, fact_id",
            (project_id, phase_id),
        ).fetchall()

    if not rows:
        return None

    # 按 fact_type 分组
    groups: dict[str, list] = {}
    for row in rows:
        ft = row[0]
        groups.setdefault(ft, []).append(row)

    type_order = ["REQ", "BR", "SE", "GAP", "OPEN"]
    type_labels = {
        "REQ": "需求点 (REQ)",
        "BR": "业务规则 (BR)",
        "SE": "语义期望 (SE)",
        "GAP": "缺口 (GAP)",
        "OPEN": "待确认项 (OPEN)",
    }

    lines = [
        f"# Facts Export — {project_id} / Phase {phase_id}",
        "",
        f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}，由 Qualix finalize 写入，可纳入 git 追踪。",
        f"> 共 {len(rows)} 条结构化事实。",
        "",
    ]

    for ft in type_order + [k for k in groups if k not in type_order]:
        if ft not in groups:
            continue
        label = type_labels.get(ft, ft)
        lines.append(f"## {label} ({len(groups[ft])} 条)")
        lines.append("")
        lines.append("| ID | 描述 | 置信度 | 关联 |")
        lines.append("|---|---|---|---|")
        for row in groups[ft]:
            fact_id = row[1] or ""
            desc = (row[2] or "").replace("|", "｜").replace("\n", " ")[:120]
            confidence = row[4] or ""
            try:
                related = json.loads(row[3] or "[]")
                related_str = ", ".join(str(r) for r in related[:3]) if related else "—"
            except Exception:
                related_str = "—"
            lines.append(f"| `{fact_id}` | {desc} | {confidence} | {related_str} |")
        lines.append("")

    content = "\n".join(lines)
    export_path = phase_path / "facts_export.md"
    export_path.write_text(content, encoding="utf-8")
    return export_path
