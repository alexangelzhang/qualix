"""文本语义缓存：PRD/技术方案首次读取后分段存入 SQLite + FTS5，后续按需检索.

策略：
1. 首次读取时按章节分段，每段提取摘要+关键词
2. 存入 SQLite，FTS5 索引
3. 后续需要某个章节时按关键词检索，只返回相关段落
4. 不再读取全文

token 节省：从读全文 ~16000 token 降到按需检索 ~2000 token
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from dqg.store import get_connection
from dqg.text_utils import build_fts_query, row_to_dict, text_query_has_signal, tokenize_chinese

if TYPE_CHECKING:
    from pathlib import Path


def segment_document(text: str, doc_name: str = "") -> list[dict[str, Any]]:
    """按 markdown 标题分段."""
    lines = text.split("\n")
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] = {
        "doc_name": doc_name,
        "heading": "(文档开头)",
        "section_path": "",
        "line_start": 1,
        "lines": [],
    }

    for i, line in enumerate(lines, 1):
        heading_match = re.match(r'^(#{1,4})\s+(.+)', line)
        if heading_match:
            if current["lines"]:
                current["line_end"] = i - 1
                current["content"] = "\n".join(current["lines"])
                current["char_count"] = len(current["content"])
                segments.append(current)

            title = heading_match.group(2).strip()
            current = {
                "doc_name": doc_name,
                "heading": title,
                "section_path": title,
                "line_start": i,
                "lines": [line],
            }
        else:
            current["lines"].append(line)

    if current["lines"]:
        current["line_end"] = len(lines)
        current["content"] = "\n".join(current["lines"])
        current["char_count"] = len(current["content"])
        segments.append(current)

    return segments


def extract_keywords(text: str) -> list[str]:
    """从文本中提取关键词（ID + 英文词 + 中文关键短语）."""
    keywords = set()
    keywords.update(re.findall(r'(?:REQ|BR|SE|GAP|OPEN)-[\d\-]+', text))
    keywords.update(re.findall(r'(?:COVERED|PARTIAL|MISSING|IMPLICIT|BLOCKER)', text))
    keywords.update(re.findall(r'\b[A-Z]{2,}[a-z]*\b', text))
    keywords.update(w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', text) if len(w) <= 10)
    chars = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
    keywords.update(chars[:30])
    return sorted(keywords)


def cache_document(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    text: str,
    doc_name: str = "",
) -> int:
    """将文档分段后存入缓存. Returns 段落数."""
    segments = segment_document(text, doc_name)

    with get_connection(output_dir) as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM text_segments WHERE project_id=? AND phase_id=? AND doc_name=?",
            (project_id, phase_id, doc_name),
        ).fetchone()[0]
        if existing > 0:
            return 0

        for seg in segments:
            content = seg["content"]
            keywords = extract_keywords(content)
            tokenized = tokenize_chinese(f"{seg['heading']} {content}")

            conn.execute(
                """INSERT INTO text_segments
                (project_id, phase_id, doc_name, section_path, heading,
                 content, content_tokenized, line_start, line_end, char_count, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, phase_id, doc_name,
                    seg.get("section_path", ""),
                    seg["heading"],
                    content,
                    tokenized,
                    seg["line_start"],
                    seg.get("line_end", 0),
                    seg.get("char_count", 0),
                    json.dumps(keywords, ensure_ascii=False),
                ),
            )
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            kw_text = tokenize_chinese(" ".join(keywords))
            heading_text = tokenize_chinese(seg["heading"])
            conn.execute(
                "INSERT INTO text_segments_fts(rowid, heading, content_tokenized, keywords) VALUES (?, ?, ?, ?)",
                (row_id, heading_text, tokenized, kw_text),
            )

    return len(segments)


def search_text(
    output_dir: Path,
    query: str,
    project_id: str | None = None,
    phase_id: str | None = None,
    limit: int = 5,
    max_chars: int = 3000,
) -> list[dict[str, Any]]:
    """FTS5 检索文本段落（按相关性排序，限制总字符数）."""
    results = []
    for mode in ("AND", "OR"):
        fts_query = build_fts_query(query, mode=mode)
        if not fts_query:
            continue
        results = _fts_search(output_dir, fts_query, project_id, phase_id, limit)
        if results:
            break

    if results and not any(text_query_has_signal(query, f"{r.get('content', '')} {r.get('heading', '')}") for r in results):
        results = []

    if not results:
        results = _like_search(output_dir, query, project_id, phase_id, limit)

    filtered = []
    total = 0
    for r in results:
        char_count = r.get("char_count", 0)
        if total + char_count > max_chars and char_count > max_chars // 2:
            content = r.get("content", "")
            snippets = _extract_snippets(content, query, context_chars=200, max_total=max_chars - total)
            if snippets:
                r = dict(r)
                r["content"] = "\n---\n".join(snippets)
                r["char_count"] = len(r["content"])
                r["truncated"] = True
                r["snippet_count"] = len(snippets)
            else:
                continue
        if total + r.get("char_count", 0) > max_chars:
            break
        filtered.append(r)
        total += r.get("char_count", 0)

    return filtered


def _extract_snippets(content: str, query: str, context_chars: int = 200, max_total: int = 3000) -> list[str]:
    query_lower = query.lower()
    content_lower = content.lower()

    positions = []
    start = 0
    while True:
        pos = content_lower.find(query_lower, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + 1

    if not positions:
        return []

    intervals = []
    for pos in positions:
        s = max(0, pos - context_chars)
        e = min(len(content), pos + len(query) + context_chars)
        intervals.append((s, e))

    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    snippets = []
    total_chars = 0
    for s, e in merged:
        prefix = "..." if s > 0 else ""
        suffix = "..." if e < len(content) else ""
        snippet = f"{prefix}{content[s:e]}{suffix}"
        if total_chars + len(snippet) > max_total:
            break
        snippets.append(snippet)
        total_chars += len(snippet)

    return snippets


def _fts_search(
    output_dir: Path,
    fts_query: str,
    project_id: str | None,
    phase_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = [fts_query]
    if project_id:
        conditions.append("s.project_id = ?")
        params.append(project_id)
    if phase_id:
        conditions.append("s.phase_id = ?")
        params.append(phase_id)
    where = f"AND {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"""SELECT s.* FROM text_segments s
            JOIN text_segments_fts f ON s.id = f.rowid
            WHERE text_segments_fts MATCH ? {where}
            ORDER BY rank LIMIT ?""",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def _like_search(
    output_dir: Path,
    query: str,
    project_id: str | None,
    phase_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    conditions = ["(content LIKE ? OR heading LIKE ? OR keywords LIKE ?)"]
    like = f"%{query}%"
    params: list[Any] = [like, like, like]
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)
    if phase_id:
        conditions.append("phase_id = ?")
        params.append(phase_id)
    where = " AND ".join(conditions)
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM text_segments WHERE {where} ORDER BY line_start LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_section(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    heading: str,
) -> dict[str, Any] | None:
    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT * FROM text_segments WHERE project_id=? AND phase_id=? AND heading=? LIMIT 1",
            (project_id, phase_id, heading),
        ).fetchone()
        return row_to_dict(row) if row else None


def get_all_headings(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, Any]]:
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT heading, line_start, line_end, char_count FROM text_segments WHERE project_id=? AND phase_id=? ORDER BY line_start",
            (project_id, phase_id),
        ).fetchall()
        return [dict(r) for r in rows]


def is_cached(output_dir: Path, project_id: str, phase_id: str) -> bool:
    with get_connection(output_dir) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM text_segments WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        ).fetchone()[0]
        return count > 0


def get_cache_stats(output_dir: Path, project_id: str, phase_id: str) -> dict[str, Any]:
    with get_connection(output_dir) as conn:
        total = conn.execute(
            "SELECT COUNT(*), SUM(char_count) FROM text_segments WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        ).fetchone()
        return {"segments": total[0], "chars": total[1] or 0}
