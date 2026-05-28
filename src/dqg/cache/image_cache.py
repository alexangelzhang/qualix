"""图片语义缓存：首次解析后存入 SQLite + FTS5，后续按关键词检索不再读图片.

中文搜索方案：存入 FTS5 前用单字+双字 n-gram 分词，查询时同样分词后匹配。
零额外依赖，性能远优于 LIKE。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dqg.json_utils import dump_json_str
from dqg.store import get_connection
from dqg.text_utils import build_fts_query, row_to_dict, text_query_has_signal, tokenize_chinese

if TYPE_CHECKING:
    from pathlib import Path


def save_image_semantic(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    record: dict[str, Any],
) -> None:
    """保存一条图片语义记录（分词写入 description_tokenized，触发器同步 FTS5）."""
    desc = record.get("description", "")
    reqs_str = dump_json_str(record.get("related_reqs", []), indent=None)
    mermaid = record.get("mermaid_code", "")
    section = record.get("section_context", "")
    filename = record.get("filename", "")

    # 分词写入 description_tokenized，FTS5 通过触发器使用此列
    tokenized = tokenize_chinese(f"{filename} {desc} {reqs_str} {mermaid} {section}")

    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO image_semantics
            (project_id, phase_id, filename, kind, description, description_tokenized,
             related_reqs, mermaid_code, section_context, token_estimate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, phase_id, filename) DO UPDATE SET
                description=excluded.description,
                description_tokenized=excluded.description_tokenized,
                related_reqs=excluded.related_reqs,
                mermaid_code=excluded.mermaid_code,
                section_context=excluded.section_context,
                token_estimate=excluded.token_estimate""",
            (
                project_id,
                phase_id,
                filename,
                record.get("kind", "image"),
                desc,
                tokenized,
                reqs_str,
                mermaid,
                section,
                record.get("token_estimate", 0),
            ),
        )


def save_batch(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    records: list[dict[str, Any]],
) -> int:
    for r in records:
        save_image_semantic(output_dir, project_id, phase_id, r)
    return len(records)


def get_phase_images(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, Any]]:
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM image_semantics WHERE project_id = ? AND phase_id = ? ORDER BY filename",
            (project_id, phase_id),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def search_image_semantics(
    output_dir: Path,
    query: str,
    project_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """FTS5 检索图片语义（中文 n-gram 分词）."""
    results: list[dict[str, Any]] = []
    for mode in ("AND", "OR"):
        fts_query = build_fts_query(query, mode=mode)
        if not fts_query:
            continue
        with get_connection(output_dir) as conn:
            if project_id:
                rows = conn.execute(
                    """SELECT s.* FROM image_semantics s
                    JOIN image_semantics_fts f ON s.id = f.rowid
                    WHERE image_semantics_fts MATCH ? AND s.project_id = ?
                    ORDER BY rank LIMIT ?""",
                    (fts_query, project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT s.* FROM image_semantics s
                    JOIN image_semantics_fts f ON s.id = f.rowid
                    WHERE image_semantics_fts MATCH ?
                    ORDER BY rank LIMIT ?""",
                    (fts_query, limit),
                ).fetchall()
            results = [row_to_dict(r) for r in rows]
        if results:
            break

    if results:
        filtered = []
        for row in results:
            candidate = f"{row.get('filename', '')} {row.get('description', '')} {row.get('section_context', '')} {row.get('mermaid_code', '')}"
            if text_query_has_signal(query, candidate):
                filtered.append(row)
        if filtered:
            results = filtered

    return results


def get_image_by_filename(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    filename: str,
) -> dict[str, Any] | None:
    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT * FROM image_semantics WHERE project_id = ? AND phase_id = ? AND filename = ?",
            (project_id, phase_id, filename),
        ).fetchone()
        return row_to_dict(row) if row else None


def export_to_markdown(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str:
    images = get_phase_images(output_dir, project_id, phase_id)
    if not images:
        return ""

    boards = [i for i in images if i.get("kind") == "board"]
    others = [i for i in images if i.get("kind") != "board"]

    lines = [f"## 图片语义缓存（{len(images)} 张）", ""]

    if boards:
        lines.append(f"### Board 类（{len(boards)} 张）")
        lines.append("")
        lines.append("| 文件名 | 语义 | 关联 REQ |")
        lines.append("|--------|------|---------|")
        for img in boards:
            reqs = ", ".join(img.get("related_reqs", []))
            lines.append(f"| {img['filename']} | {img['description']} | {reqs} |")
        lines.append("")

        for img in boards:
            mermaid = img.get("mermaid_code", "")
            if mermaid:
                lines.append(f"#### {img['filename']}: {img['description']}")
                lines.append("")
                lines.append("```mermaid")
                lines.append(mermaid)
                lines.append("```")
                lines.append("")

    if others:
        lines.append(f"### Image 类（{len(others)} 张）")
        lines.append("")
        lines.append("| 文件名 | 语义 | 关联 REQ |")
        lines.append("|--------|------|---------|")
        for img in others:
            reqs = ", ".join(img.get("related_reqs", []))
            lines.append(f"| {img['filename']} | {img['description']} | {reqs} |")
        lines.append("")

    return "\n".join(lines)


def write_cache_markdown(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    md = export_to_markdown(output_dir, project_id, phase_id)
    if not md:
        return None

    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _pd

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _pd(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "image_semantics.md"
    path.write_text(md, encoding="utf-8")
    return path
