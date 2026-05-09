"""P0: LLM prompt/response 低频采样 — 写入 telemetry llm_calls 便于调试（非全量）."""

from __future__ import annotations

import os
import random
from typing import Any

_DEFAULT_SAMPLE_RATE = 0.02
_DEFAULT_PROMPT_MAX = 8000
_DEFAULT_RESPONSE_MAX = 4000


def telemetry_payload_sample_rate() -> float:
    raw = os.environ.get("DQG_TELEMETRY_PAYLOAD_SAMPLE_RATE", str(_DEFAULT_SAMPLE_RATE)).strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.0


def telemetry_payload_max_chars() -> tuple[int, int]:
    """Returns (prompt_max, response_max)."""
    try:
        p = int(os.environ.get("DQG_TELEMETRY_PAYLOAD_PROMPT_MAX", str(_DEFAULT_PROMPT_MAX)))
        r = int(os.environ.get("DQG_TELEMETRY_PAYLOAD_RESPONSE_MAX", str(_DEFAULT_RESPONSE_MAX)))
        return max(0, p), max(0, r)
    except ValueError:
        return _DEFAULT_PROMPT_MAX, _DEFAULT_RESPONSE_MAX


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text:
        return ""
    t = text.strip()
    if len(t) <= max_chars:
        return t
    if max_chars <= 3:
        return t[:max_chars]
    return t[: max_chars - 3].rstrip() + "..."


def build_prompt_preview(messages: list[dict[str, Any]], max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role", "?"))
        content = str(m.get("content", ""))
        parts.append(f"[{role}]\n{content}")
    full = "\n\n".join(parts)
    return _truncate(full, max_chars)


def maybe_sample_agent_payload(
    messages: list[dict[str, Any]],
    response_text: str,
) -> tuple[str, str]:
    """按采样率为单次 Agent 调用生成 prompt/response 摘录（空字符串表示未采样）."""
    rate = telemetry_payload_sample_rate()
    if rate <= 0.0:
        return "", ""
    if random.random() >= rate:
        return "", ""
    pm, rm = telemetry_payload_max_chars()
    return build_prompt_preview(messages, pm), _truncate(response_text.strip(), rm)
