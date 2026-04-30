"""Evidence Pack 渲染：chunk body 摘要、关键引用提取、JSON/文本内容格式化."""

from __future__ import annotations

import json
import re

from dqg.constants import (
    EVIDENCE_PACK_MAX_QUOTES,
    EVIDENCE_PACK_QUOTE_CHAR_LIMIT,
    EVIDENCE_PACK_SUMMARY_MAX_LINES,
    EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT,
    ID_FIELD_KEYS,
)

from .doc_summary import extract_summary

_KEY_QUOTE_PATTERN = re.compile(
    r"REQ-|BR-|SE-|GAP-|OPEN-|状态|流程|权限|异常|并发|幂等|校验|提示|接口|字段|图片|泳道|Mermaid",
    re.IGNORECASE,
)
_ID_KEYS = ID_FIELD_KEYS


def truncate_chars(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...(截断)"


def _sample_ids(items: list[object], max_items: int = 3) -> list[str]:
    samples: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in _ID_KEYS:
            value = item.get(key)
            if value:
                samples.append(str(value))
                break
        if len(samples) >= max_items:
            break
    return samples


def _summarize_json_content(content: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return truncate_chars(content, EVIDENCE_PACK_QUOTE_CHAR_LIMIT)

    lines: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                line = f"- {key}: {len(value)} 项"
                samples = _sample_ids(value)
                if samples:
                    line += f"；示例: {', '.join(samples)}"
                lines.append(line)
            elif isinstance(value, dict):
                lines.append(f"- {key}: {len(value)} 个字段")
            elif value not in (None, "", []):
                rendered = truncate_chars(str(value), 80).replace("\n", " ")
                lines.append(f"- {key}: {rendered}")
    elif isinstance(data, list):
        lines.append(f"- list: {len(data)} 项")
        samples = _sample_ids(data)
        if samples:
            lines.append(f"- 示例: {', '.join(samples)}")
    else:
        lines.append(f"- value: {truncate_chars(str(data), 120)}")

    return "\n".join(lines[: min(EVIDENCE_PACK_SUMMARY_MAX_LINES, 12)]) or truncate_chars(content, 200)


def _summarize_text_content(content: str) -> str:
    summary = extract_summary(content, max_lines=min(EVIDENCE_PACK_SUMMARY_MAX_LINES, 12)).strip()
    if not summary:
        paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
        summary = "\n\n".join(paragraphs[:2])
    return truncate_chars(summary, 1_200)


def render_chunk_body(chunk) -> str:
    """渲染单个 chunk 的 body 摘要，附 file_path citation."""
    content = chunk.content.strip()
    if not content:
        return "（空）"

    if "Bug cases" in chunk.source or "Diff context" in chunk.source:
        body = truncate_chars(content, 2_000)
    elif content.startswith("{") or content.startswith("["):
        body = _summarize_json_content(content)
    else:
        body = _summarize_text_content(content)

    file_path = getattr(chunk, "file_path", "") or ""
    if file_path:
        body += f"\n> [来源: {file_path}]"
    return body


def _pick_quote_candidates(content: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    candidates: list[str] = []
    for para in paragraphs:
        if para.startswith(("#", "- ", "|")) or _KEY_QUOTE_PATTERN.search(para):
            candidates.append(para)
    if not candidates:
        candidates = paragraphs[:2]

    deduped: list[str] = []
    seen: set[str] = set()
    for para in candidates:
        normalized = para.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def render_key_quotes(
    chunks,
    *,
    max_quotes: int = 0,
    total_char_limit: int = 0,
    priority_ids: set[str] | None = None,
) -> list[str]:
    """从 chunks 中提取关键引用行，附 file:line citation.

    Args:
        priority_ids: 若提供，包含这些 ID 的段落优先选取；其余按原有 regex 顺序填充。
    """
    if not max_quotes:
        max_quotes = EVIDENCE_PACK_MAX_QUOTES
    if not total_char_limit:
        total_char_limit = EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT

    # Collect all candidates with their chunk metadata
    all_candidates: list[tuple[str, str, str]] = []  # (para, source, file_path)
    for chunk in chunks:
        file_path = getattr(chunk, "file_path", "") or ""
        for para in _pick_quote_candidates(chunk.content):
            all_candidates.append((para, chunk.source, file_path))

    # Sort: priority matches first, preserving relative order within each group
    if priority_ids:
        priority: list[tuple[str, str, str]] = []
        rest: list[tuple[str, str, str]] = []
        for item in all_candidates:
            para = item[0]
            if any(pid in para for pid in priority_ids):
                priority.append(item)
            else:
                rest.append(item)
        all_candidates = priority + rest

    lines: list[str] = []
    quote_count = 0
    used_chars = 0

    for para, source, file_path in all_candidates:
        if quote_count >= max_quotes or used_chars >= total_char_limit:
            break
        remaining = total_char_limit - used_chars
        if remaining <= 0:
            break
        quote = truncate_chars(para, min(EVIDENCE_PACK_QUOTE_CHAR_LIMIT, remaining))
        if not quote:
            continue
        quote_count += 1
        used_chars += len(quote)
        citation = source
        if file_path:
            citation += f" [来源: {file_path}]"
        lines.append(f"### 引用 {quote_count}: {citation}")
        lines.extend(f"> {line}" for line in quote.splitlines())
        lines.append("")

    if not lines:
        return ["（无可用关键引用）"]
    if lines[-1] == "":
        lines.pop()
    return lines
