"""案例相关性匹配 + Warm Start prompt 渲染."""

from __future__ import annotations

import re
from typing import Any

from dqg.tracking.bug_cases import load_cases_by_phase


def _extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词（中文分词简化版：按标点和空格切分）."""
    stopwords = {"的", "了", "在", "是", "和", "与", "或", "等", "为", "对", "从", "到", "中", "上", "下", "不", "有", "无"}
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_][A-Za-z0-9_]+", text)
    return {t for t in tokens if t not in stopwords and len(t) >= 2}


def _compute_relevance(case: dict[str, Any], input_keywords: set[str]) -> float:
    """计算案例与输入的相关性分数 (0-1)."""
    actual = case.get("actual", {})
    expected = case.get("expected", {})
    source = case.get("source", {})
    case_text_parts = [
        case.get("title", ""),
        case.get("lesson", ""),
        " ".join(case.get("tags", [])),
        case.get("root_cause", ""),
        case.get("fix_target", ""),
        actual.get("content", "") if isinstance(actual, dict) else str(actual),
        expected.get("content", "") if isinstance(expected, dict) else str(expected),
        source.get("validation_error", "") if isinstance(source, dict) else "",
    ]

    case_keywords = _extract_keywords(" ".join(case_text_parts))
    if not case_keywords or not input_keywords:
        return 0.0

    overlap = case_keywords & input_keywords
    return len(overlap) / max(len(case_keywords), 1)


def select_relevant_cases(
    phase: str,
    input_text: str,
    max_cases: int = 8,
    min_relevance: float = 0.05,
) -> list[dict[str, Any]]:
    """选择与当前输入最相关的 bug 案例."""
    cases = [c for c in load_cases_by_phase(phase) if c.get("status") == "open"]
    if not cases:
        return []

    input_keywords = _extract_keywords(input_text)
    if not input_keywords:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        cases.sort(key=lambda c: severity_order.get(c.get("severity", "low"), 9))
        return cases[:max_cases]

    scored: list[tuple[float, dict[str, Any]]] = []
    for case in cases:
        score = _compute_relevance(case, input_keywords)
        severity_bonus = {"critical": 0.3, "high": 0.15, "medium": 0.05, "low": 0.0}
        score += severity_bonus.get(case.get("severity", "low"), 0)
        scored.append((score, case))

    scored.sort(key=lambda x: -x[0])

    result = []
    for score, case in scored:
        if len(result) >= max_cases:
            break
        if score >= min_relevance or case.get("severity") in ("critical", "high"):
            result.append(case)

    return result


def render_relevant_cases_for_prompt(
    phase: str,
    input_text: str,
    max_cases: int = 8,
) -> str:
    """渲染与当前输入相关的 bug 案例为 prompt markdown."""
    cases = select_relevant_cases(phase, input_text, max_cases)
    if not cases:
        return ""

    lines = [
        "## BUG_CASES — 已知判错案例（务必避免重犯）",
        "",
        f"以下是 Phase {phase} 与当前输入最相关的历史判错案例。",
        "",
    ]

    for i, c in enumerate(cases, 1):
        error_label = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(c.get("error_type", ""), c.get("error_type", ""))
        lines.append(f"### 反例 {i}: {c.get('title', '')[:80]} [{error_label}]")
        lines.append("")

        lesson = c.get("lesson", "")
        if lesson:
            lines.append(f"**教训**: {lesson}")
            lines.append("")

    return "\n".join(lines)
