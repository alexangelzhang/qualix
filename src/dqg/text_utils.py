"""共享文本工具：中文 n-gram 分词、通用 row_to_dict.

注意：REPORT_MAP / STRUCTURED_JSON_MAP 的权威定义已迁移到 constants.py，
此处 re-export 保持向后兼容。
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from typing import Any

from dqg.constants import (
    REPORT_MAP,  # noqa: F401 - re-export
    STRUCTURED_JSON_MAP,  # noqa: F401 - re-export
)

_CHINESE_SEGMENT_RE = re.compile(r"[\u4e00-\u9fff]+")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9]+(?:[_\-][A-Za-z0-9]+)*")
_CAMEL_PART_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
_CHINESE_ONLY_RE = re.compile(r"[\u4e00-\u9fff]+")


def _split_identifier_parts(token: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[_\-]+", token):
        if not chunk:
            continue
        camel_parts = _CAMEL_PART_RE.findall(chunk)
        if camel_parts:
            parts.extend(camel_parts)
        else:
            parts.append(chunk)
    return [part.lower() for part in parts if part]


def _tokenize_chinese_segment(segment: str) -> list[str]:
    chars = list(segment)
    tokens = chars[:]
    tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return tokens


def tokenize_chinese(text: str) -> str:
    """中文 n-gram 分词：单字+双字只在连续中文片段内生成，英文保留原词并拆 identifier 子 token."""
    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip().lower()
        if not token or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    cursor = 0
    for match in _CHINESE_SEGMENT_RE.finditer(text):
        prefix = text[cursor:match.start()]
        for ident in _IDENTIFIER_RE.findall(prefix):
            add(ident)
            for part in _split_identifier_parts(ident):
                add(part)
        for token in _tokenize_chinese_segment(match.group()):
            add(token)
        cursor = match.end()

    suffix = text[cursor:]
    for ident in _IDENTIFIER_RE.findall(suffix):
        add(ident)
        for part in _split_identifier_parts(ident):
            add(part)

    return " ".join(tokens)


def build_fts_query_tokens(text: str) -> list[str]:
    """将查询文本转换为 FTS MATCH 的 token 列表。"""
    tokenized = tokenize_chinese(text)
    tokens: list[str] = []
    for token in tokenized.split():
        if not token:
            continue
        if len(token) == 1 and _CHINESE_ONLY_RE.fullmatch(token):
            continue
        tokens.append(token)
    if not tokens:
        tokens = [token for token in tokenized.split() if token]
    return tokens


def build_fts_query(text: str, mode: str = "AND") -> str:
    """构造 FTS5 MATCH 查询字符串。"""
    tokens = build_fts_query_tokens(text)
    if not tokens:
        return ""
    quoted = [f'"{token}"' for token in tokens]
    mode = mode.upper()
    if mode not in {"AND", "OR"}:
        mode = "AND"
    return f" {mode} ".join(quoted)


def text_query_has_signal(query: str, candidate: str) -> bool:
    """轻量后过滤：候选内容是否含有查询里的中文/英文信号词。"""
    normalized_query = query.lower().strip()
    if not normalized_query:
        return False

    candidate_lower = candidate.lower()
    if normalized_query in candidate_lower:
        return True

    for token in build_fts_query_tokens(query):
        if len(token) <= 1:
            continue
        if token in candidate_lower:
            return True

    chinese_tokens = [t for t in build_fts_query_tokens(query) if len(t) > 1 and _CHINESE_ONLY_RE.fullmatch(t)]
    return any(token in candidate for token in chinese_tokens)


def row_to_dict(row, json_fields: list[str] | None = None) -> dict[str, Any]:
    """sqlite3.Row → dict，自动解析指定的 JSON 字段。"""
    d = dict(row)
    fields = json_fields or [k for k, v in d.items() if isinstance(v, str) and v and v[0] in ("[", "{")]
    for key in fields:
        if key in d and isinstance(d[key], str):
            with suppress(json.JSONDecodeError, TypeError):
                d[key] = json.loads(d[key])
    return d
