"""Eval Holdout 验证：检测 skill evolution 是否过拟合.

三条触发条件（任一触发即 overfitting_signal=True）:
1. coverage_gap > SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD and holdout_with_lesson >= SKILL_EVO_HOLDOUT_MIN_WITH_LESSON
2. distribution_divergence > SKILL_EVO_DIST_DIVERGENCE_THRESHOLD（training vs holdout root_cause 分布 L1 差）
3. holdout_hit_rate < SKILL_EVO_HIT_RATE_MIN and holdout_count >= SKILL_EVO_HOLDOUT_MIN_CASES

holdout_ready 字段表明 holdout 集是否足够做判定，上层 verify_with_holdout 根据它决定是否 auto-merge。
"""

from __future__ import annotations

from typing import Any


def _compute_l1_divergence(a: dict[str, int], b: dict[str, int]) -> float:
    """计算两个离散分布的 L1 差（归一化后）.

    Returns 0.0-2.0；0 表示完全一致，2 表示完全不相交。
    """
    total_a = sum(a.values()) or 1
    total_b = sum(b.values()) or 1
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0) / total_a - b.get(k, 0) / total_b) for k in keys)


def validate_against_holdout(phase_id: str) -> dict[str, Any]:
    """用 holdout cases 验证当前 skill 是否过拟合.

    对比训练集和 holdout 集的 bug case 特征分布 + suggestion 覆盖率，
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
            "holdout_with_lesson": int,
            "uncovered_by_suggestions": int,
            "coverage_gap": float,
            "holdout_hit_rate": float,             # 新增：1 - coverage_gap，直观
            "distribution_divergence": float,      # 新增：root_cause 分布 L1 差
            "holdout_ready": bool,                 # 新增：是否足够做判定
            "overfitting_signal": bool,
            "decision_reason": str,                # 新增：放行/拦截的可读原因
        }
    """
    from collections import Counter

    from qualix.constants import (
        SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD,
        SKILL_EVO_DIST_DIVERGENCE_THRESHOLD,
        SKILL_EVO_HIT_RATE_MIN,
        SKILL_EVO_HOLDOUT_MIN_CASES,
        SKILL_EVO_HOLDOUT_MIN_WITH_LESSON,
    )
    from qualix.tracking.bug_cases import load_cases_by_phase
    from qualix.tracking.skill_factory import generate_skill_suggestions

    training_cases = load_cases_by_phase(phase_id, exclude_holdout=True)
    holdout_cases = load_cases_by_phase(phase_id, holdout_only=True)

    base_payload: dict[str, Any] = {
        "phase": phase_id,
        "training_count": len(training_cases),
        "holdout_count": len(holdout_cases),
    }

    if not holdout_cases:
        return {
            **base_payload,
            "overfitting_signal": False,
            "holdout_ready": False,
            "decision_reason": "no_holdout_cases",
            "message": "No holdout cases available for validation",
        }

    # 分布对比
    train_rc = Counter(c.get("root_cause", "?") for c in training_cases)
    holdout_rc = Counter(c.get("root_cause", "?") for c in holdout_cases)
    train_et = Counter(c.get("error_type", "?") for c in training_cases)
    holdout_et = Counter(c.get("error_type", "?") for c in holdout_cases)
    distribution_divergence = _compute_l1_divergence(dict(train_rc), dict(holdout_rc))

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
    holdout_hit_rate = 1.0 - coverage_gap if holdout_with_lesson > 0 else 0.0

    holdout_ready = (
        len(holdout_cases) >= SKILL_EVO_HOLDOUT_MIN_CASES and holdout_with_lesson >= SKILL_EVO_HOLDOUT_MIN_WITH_LESSON
    )

    # 三条件任一触发 → overfitting
    signals: list[str] = []
    if (
        coverage_gap > SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD
        and holdout_with_lesson >= SKILL_EVO_HOLDOUT_MIN_WITH_LESSON
    ):
        signals.append(f"coverage_gap={coverage_gap:.2f} > {SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD}")
    if distribution_divergence > SKILL_EVO_DIST_DIVERGENCE_THRESHOLD:
        signals.append(f"dist_divergence={distribution_divergence:.2f} > {SKILL_EVO_DIST_DIVERGENCE_THRESHOLD}")
    if holdout_hit_rate < SKILL_EVO_HIT_RATE_MIN and len(holdout_cases) >= SKILL_EVO_HOLDOUT_MIN_CASES:
        signals.append(f"hit_rate={holdout_hit_rate:.2f} < {SKILL_EVO_HIT_RATE_MIN}")

    overfitting_signal = bool(signals)
    if overfitting_signal:
        decision_reason = "overfitting: " + "; ".join(signals)
    elif not holdout_ready:
        decision_reason = f"holdout_not_ready: count={len(holdout_cases)}, with_lesson={holdout_with_lesson}"
    else:
        decision_reason = "holdout_ok"

    return {
        **base_payload,
        "training_root_cause_dist": dict(train_rc),
        "holdout_root_cause_dist": dict(holdout_rc),
        "training_error_type_dist": dict(train_et),
        "holdout_error_type_dist": dict(holdout_et),
        "holdout_with_lesson": holdout_with_lesson,
        "uncovered_by_suggestions": uncovered,
        "coverage_gap": round(coverage_gap, 2),
        "holdout_hit_rate": round(holdout_hit_rate, 2),
        "distribution_divergence": round(distribution_divergence, 2),
        "holdout_ready": holdout_ready,
        "overfitting_signal": overfitting_signal,
        "decision_reason": decision_reason,
    }
