"""Lossless prompt compression via dictionary encoding.

Based on: Lossless Prompt Compression (arXiv:2604.13066)

Strategy:
1. Scan text for repeated phrases (≥ 2 occurrences, ≥ MIN_PHRASE_LEN chars)
2. Build a compact dictionary: [D1] → "repeated phrase"
3. Replace all occurrences with short tokens
4. Prepend dictionary header so LLM can decode exactly

Only applied when compression ratio > MIN_SAVINGS_RATIO to avoid overhead.
Conservative: only compress phrases that appear ≥ MIN_REPEAT times.
"""

from __future__ import annotations

import re
from collections import Counter

MIN_PHRASE_LEN = 20  # minimum chars for a phrase to be worth compressing
MIN_REPEAT = 2  # minimum occurrences to compress
MIN_SAVINGS_RATIO = 0.08  # only compress if saves ≥ 8% of original length
MAX_DICT_ENTRIES = 40  # cap dictionary size to avoid header bloat

_DICT_HEADER_START = "<!-- DICT"
_DICT_HEADER_END = "DICT -->"

# Patterns to extract candidate phrases from Evidence Pack text
_CANDIDATE_PATTERNS = [
    # SE/REQ/BR/GAP descriptions: "SE-001: some description text"
    re.compile(r"(?:SE|REQ|BR|GAP|OPEN)-\d+[：:]\s*.{20,120}"),
    # Markdown list items with substantial content
    re.compile(r"^[-*]\s+.{20,100}$", re.MULTILINE),
    # Source headers repeated across chunks
    re.compile(r"Phase [A-Z0-9.]+ .{10,60}"),
]


def _extract_candidates(text: str) -> list[str]:
    """Extract candidate phrases for compression."""
    candidates = []
    for pattern in _CANDIDATE_PATTERNS:
        candidates.extend(m.group().strip() for m in pattern.finditer(text))
    return candidates


def _build_dictionary(text: str) -> dict[str, str]:
    """Build compression dictionary: token → original phrase.

    Returns dict sorted by phrase length descending (longer phrases first
    to avoid partial replacement issues).
    """
    candidates = _extract_candidates(text)
    counts = Counter(candidates)

    # Filter: must repeat enough times and be long enough
    eligible = [phrase for phrase, count in counts.items() if count >= MIN_REPEAT and len(phrase) >= MIN_PHRASE_LEN]

    # Sort by savings potential: (len - token_len) * count, descending
    def savings(phrase: str) -> int:
        token_len = len(f"[D{1}]")  # approximate
        return (len(phrase) - token_len) * counts[phrase]

    eligible.sort(key=savings, reverse=True)
    eligible = eligible[:MAX_DICT_ENTRIES]

    # Build token map: phrase → [D1], [D2], ...
    return {phrase: f"[D{i + 1}]" for i, phrase in enumerate(eligible)}


def compress(text: str) -> str:
    """Apply dictionary compression to text.

    Returns original text if compression ratio < MIN_SAVINGS_RATIO.
    Prepends a DICT header that LLM uses to decode tokens.
    """
    if not text or len(text) < 500:
        return text

    dictionary = _build_dictionary(text)
    if not dictionary:
        return text

    # Apply replacements (longest phrases first to avoid partial matches)
    compressed = text
    for phrase, token in sorted(dictionary.items(), key=lambda x: -len(x[0])):
        compressed = compressed.replace(phrase, token)

    # Check savings
    savings_ratio = 1 - len(compressed) / len(text)
    if savings_ratio < MIN_SAVINGS_RATIO:
        return text

    # Build dictionary header
    dict_lines = [
        _DICT_HEADER_START,
        "以下是压缩字典，[Dn] 是对应短语的替代符号，阅读时请自动展开：",
    ]
    for phrase, token in sorted(dictionary.items(), key=lambda x: x[1]):
        dict_lines.append(f"{token} = {phrase}")
    dict_lines.append(_DICT_HEADER_END)
    dict_lines.append("")

    header = "\n".join(dict_lines)
    return header + compressed


def decompress(text: str) -> str:
    """Reverse dictionary compression (for testing / audit)."""
    if _DICT_HEADER_START not in text:
        return text

    header_end = text.find(_DICT_HEADER_END)
    if header_end == -1:
        return text

    header = text[:header_end]
    body = text[header_end + len(_DICT_HEADER_END) :].lstrip("\n")

    # Parse dictionary from header
    token_map: dict[str, str] = {}
    for line in header.splitlines():
        if " = " in line and line.startswith("[D"):
            token, phrase = line.split(" = ", 1)
            token_map[token.strip()] = phrase.strip()

    # Replace tokens with original phrases
    result = body
    for token, phrase in token_map.items():
        result = result.replace(token, phrase)
    return result


def compression_ratio(original: str, compressed: str) -> float:
    """Return compression ratio (0.0 = no compression, 1.0 = fully compressed)."""
    if not original:
        return 0.0
    return 1 - len(compressed) / len(original)
