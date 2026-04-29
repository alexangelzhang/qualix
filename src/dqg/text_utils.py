"""共享文本工具：中文分词（jieba 词级 + n-gram 兜底）、通用 row_to_dict.

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

# ---------------------------------------------------------------------------
# jieba 懒加载（可选依赖，不可用时降级到 n-gram）
# ---------------------------------------------------------------------------

_jieba_available: bool | None = None
_jieba_module: Any = None

# 中文停用词（高频无意义词）
_CHINESE_STOPWORDS: frozenset[str] = frozenset(
    {
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "他",
        "她",
        "它",
        "们",
        "那",
        "些",
        "什么",
        "怎么",
        "如果",
        "因为",
        "所以",
        "但是",
        "而且",
        "或者",
        "以及",
        "可以",
        "需要",
        "进行",
        "使用",
        "通过",
        "对于",
        "关于",
        "其中",
        "以下",
        "以上",
        "之后",
        "之前",
        "目前",
        "已经",
        "正在",
        "将要",
        "应该",
        "必须",
    }
)


def _ensure_jieba() -> bool:
    """懒加载 jieba，返回是否可用."""
    global _jieba_available, _jieba_module
    if _jieba_available is not None:
        return _jieba_available
    try:
        import jieba as _jb

        _jb.setLogLevel(20)  # 抑制 jieba 的 DEBUG 日志
        _jieba_module = _jb
        _jieba_available = True
    except ImportError:
        _jieba_available = False
    return _jieba_available


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


def _tokenize_chinese_segment_ngram(segment: str) -> list[str]:
    """n-gram 分词（降级方案）：单字+双字."""
    chars = list(segment)
    tokens = chars[:]
    tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return tokens


def _tokenize_chinese_segment_jieba(segment: str) -> list[str]:
    """jieba 词级分词 + 双字 n-gram 补充（提高召回率）."""
    tokens: list[str] = []
    # jieba 精确模式分词
    words = _jieba_module.lcut(segment)
    for word in words:
        if word.strip() and word not in _CHINESE_STOPWORDS:
            tokens.append(word)
    # 补充双字 n-gram（覆盖 jieba 未识别的新词）
    chars = list(segment)
    for i in range(len(chars) - 1):
        bigram = chars[i] + chars[i + 1]
        if bigram not in _CHINESE_STOPWORDS:
            tokens.append(bigram)
    return tokens


def tokenize_chinese(text: str) -> str:
    """中文分词：jieba 词级（可用时）或 n-gram 降级，英文保留原词并拆 identifier 子 token."""
    use_jieba = _ensure_jieba()
    segment_fn = _tokenize_chinese_segment_jieba if use_jieba else _tokenize_chinese_segment_ngram

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
        prefix = text[cursor : match.start()]
        for ident in _IDENTIFIER_RE.findall(prefix):
            add(ident)
            for part in _split_identifier_parts(ident):
                add(part)
        for token in segment_fn(match.group()):
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


# ---------------------------------------------------------------------------
# EUT ID 展开（支持逗号分隔 + 范围格式）
# ---------------------------------------------------------------------------

_EUT_RANGE_RE = re.compile(r"^(?:EUT-)?(\d+)~(?:EUT-)?(\d+)$")


def expand_eut_ids(raw: str) -> set[str]:
    """展开 EUT ID 字符串为独立 ID 集合.

    支持格式: "EUT-001", "EUT-001,EUT-002", "EUT-008~012", "EUT-001,EUT-008~012"
    """
    result: set[str] = set()
    for segment in re.split(r"[,\s]+", raw):
        segment = segment.strip()
        if not segment:
            continue
        range_match = _EUT_RANGE_RE.match(segment)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            for n in range(start, end + 1):
                result.add(f"EUT-{n:03d}")
        elif re.match(r"^EUT-\d+$", segment):
            result.add(segment)
        elif re.match(r"^\d+$", segment):
            result.add(f"EUT-{int(segment):03d}")
    return result
