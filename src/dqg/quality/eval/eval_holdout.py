"""Eval Holdout 验证：检测 skill evolution 是否过拟合.

从 eval_baseline.py 拆分而来。
"""

from __future__ import annotations

from typing import Any


def validate_against_holdout(phase_id: str) -> dict[str, Any]:
    """用 holdout cases 验证当前 skill 是否过拟合.

    对比训练集和 holdout 集的 bug case 特征分布，
    检测 skill evolution 是否过度拟合到训练集的 error pattern。

    Returns:
        {
            "phase": str,
            "training_count": int,
            "holdout_count": int,
            "training_root_cause_dist": {"SKILL_RULE": 5, ...},
            "holdout_root_cause_dist": {"SKILL_RULE": 2, ...},
            "training_error_type_dist": {"FN": 3, ...},
            "holdout_error_type_dist": {"FN": 1, ...},
            "coverage_gap": float,
            "overfitting_signal": bool,
        }
    """
    from collections import Counter

    from dqg.tracking.bug_cases import load_cases_by_phase
    from dqg.tracking.skill_factory import generate_skill_suggestions

    training_cases = load_cases_by_phase(phase_id, exclude_holdout=True)
    holdout_cases = load_cases_by_phase(phase_id, holdout_only=True)

    if not holdout_cases:
        return {
            "phase": phase_id,
            "training_count": len(training_cases),
            "holdout_count": 0,
            "overfitting_signal": False,
            "message": "No holdout cases available for validation",
        }

    # 分布对比
    train_rc = Counter(c.get("root_cause", "?") for c in training_cases)
    holdout_rc = Counter(c.get("root_cause", "?") for c in holdout_cases)
    train_et = Counter(c.get("error_type", "?") for c in training_cases)
    holdout_et = Counter(c.get("error_type", "?") for c in holdout_cases)

    # 检测 skill suggestions 是否覆盖 holdout cases 的 lesson
    suggestions = generate_skill_suggestions(phase_id)
    suggestion_texts = set()
    for item in suggestions.get("anti_rationalization_suggestions", []):
        suggestion_texts.add(item.get("rebuttal", "").lower())
    for item in suggestions.get("red_line_suggestions", []):
        suggestion_texts.add(item.get("rule", "").lower())

    # 计算 holdout 中有 lesson 但未被 suggestion 覆盖的比例
    uncovered = 0
    holdout_with_lesson = 0
    for c in holdout_cases:
        lesson = c.get("lesson", "").strip().lower()
        if not lesson:
            continue
        holdout_with_lesson += 1
        if not any(lesson[:20] in s for s in suggestion_texts):
            uncovered += 1

    coverage_gap = uncovered / max(holdout_with_lesson, 1)
    overfitting_signal = coverage_gap > 0.5 and holdout_with_lesson >= 3

    return {
        "phase": phase_id,
        "training_count": len(training_cases),
        "holdout_count": len(holdout_cases),
        "training_root_cause_dist": dict(train_rc),
        "holdout_root_cause_dist": dict(holdout_rc),
        "training_error_type_dist": dict(train_et),
        "holdout_error_type_dist": dict(holdout_et),
        "holdout_with_lesson": holdout_with_lesson,
        "uncovered_by_suggestions": uncovered,
        "coverage_gap": round(coverage_gap, 2),
        "overfitting_signal": overfitting_signal,
    }
