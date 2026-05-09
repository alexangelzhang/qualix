"""T10: Failure→Reflector 轻量回流 — 新写入 case 时补齐 lesson / case_category.

使用 `lesson_inference.infer_lesson_with_fallback` 与 `case_category.infer_case_category`，
不依赖外部 LLM，便于 CI 与离线环境一致。
"""

from __future__ import annotations

from typing import Any, Final

from dqg.tracking.case_category import CASE_CATEGORIES, infer_case_category
from dqg.tracking.lesson_inference import infer_lesson_with_fallback

# 与 2026-05-09 报告「约 80 字」对齐（按 Python len，非 grapheme）
REFLECT_LESSON_MAX_LEN: Final[int] = 80


def _truncate_lesson(text: str, max_len: int = REFLECT_LESSON_MAX_LEN) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    if max_len <= 3:
        return t[:max_len]
    return t[: max_len - 3].rstrip() + "..."


def apply_reflect_metadata(case: dict[str, Any]) -> dict[str, Any]:
    """返回 case 副本：在 lesson / case_category 缺失时填入推断值。

    已有非空 lesson 时保留原文（不截断）；仅对本次推断出的 lesson 做长度裁剪。
    """
    out = dict(case)
    had_lesson = bool(str(out.get("lesson", "")).strip())
    if not had_lesson:
        raw = infer_lesson_with_fallback(out)
        out["lesson"] = _truncate_lesson(raw)

    cat = str(out.get("case_category", "") or "").strip()
    if not cat or cat not in CASE_CATEGORIES:
        out["case_category"] = infer_case_category(out)

    return out
