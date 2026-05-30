"""Tests for qualix.quality.eval.eval_holdout.validate_against_holdout."""

from __future__ import annotations

from typing import Any

import pytest

from qualix.quality.eval.eval_holdout import _compute_l1_divergence, validate_against_holdout


def test_l1_divergence_identical() -> None:
    a = {"X": 3, "Y": 1}
    b = {"X": 6, "Y": 2}
    # 归一化后完全一致
    assert _compute_l1_divergence(a, b) == 0.0


def test_l1_divergence_disjoint() -> None:
    a = {"X": 5}
    b = {"Y": 5}
    # X 只在 a、Y 只在 b — L1 = 1 + 1 = 2
    assert _compute_l1_divergence(a, b) == pytest.approx(2.0)


def test_l1_divergence_empty() -> None:
    assert _compute_l1_divergence({}, {}) == 0.0


# ---------------------------------------------------------------------------
# validate_against_holdout
# ---------------------------------------------------------------------------


def _patch_cases(
    monkeypatch: pytest.MonkeyPatch,
    training: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
) -> None:
    def _loader(phase: str, base_dir=None, exclude_holdout: bool = False, holdout_only: bool = False):
        if holdout_only:
            return holdout
        return training

    monkeypatch.setattr("qualix.tracking.bug_cases.load_cases_by_phase", _loader)


def _patch_suggestions(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "qualix.tracking.skill_factory.generate_skill_suggestions",
        lambda phase: payload,
    )


def test_empty_holdout_returns_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cases(monkeypatch, training=[{"root_cause": "SKILL_RULE"}], holdout=[])
    _patch_suggestions(monkeypatch, {})

    result = validate_against_holdout("Q01")
    assert result["holdout_count"] == 0
    assert result["overfitting_signal"] is False
    assert result["holdout_ready"] is False
    assert result["decision_reason"] == "no_holdout_cases"


def test_holdout_not_ready_when_below_min_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    # 只有 2 条 holdout（< SKILL_EVO_HOLDOUT_MIN_CASES=3）
    training = [{"root_cause": "SKILL_RULE"} for _ in range(5)]
    holdout = [
        {"root_cause": "SKILL_RULE", "lesson": "lesson one"},
        {"root_cause": "SKILL_RULE", "lesson": "lesson two"},
    ]
    _patch_cases(monkeypatch, training, holdout)
    _patch_suggestions(
        monkeypatch,
        {
            "anti_rationalization_suggestions": [{"rebuttal": "lesson one fully covered"}],
            "red_line_suggestions": [],
        },
    )

    result = validate_against_holdout("Q01")
    assert result["holdout_ready"] is False
    # overfitting_signal 仍可能 False，但 holdout_ready=False 本身足够让 verify_with_holdout 拒绝
    assert "holdout_not_ready" in result["decision_reason"] or result["overfitting_signal"]


def test_overfitting_by_coverage_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    training = [{"root_cause": "SKILL_RULE"} for _ in range(10)]
    # 4 条 holdout 都带 lesson，suggestion 全不覆盖
    holdout = [{"root_cause": "SKILL_RULE", "lesson": f"uncovered lesson {i}"} for i in range(4)]
    _patch_cases(monkeypatch, training, holdout)
    _patch_suggestions(
        monkeypatch,
        {"anti_rationalization_suggestions": [{"rebuttal": "totally unrelated suggestion"}]},
    )

    result = validate_against_holdout("Q01")
    assert result["holdout_count"] == 4
    assert result["holdout_with_lesson"] == 4
    assert result["coverage_gap"] == pytest.approx(1.0, rel=0.01)
    assert result["overfitting_signal"] is True
    assert "coverage_gap" in result["decision_reason"]


def test_overfitting_by_distribution_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    # training 全是 SKILL_RULE，holdout 全是 KNOWLEDGE → L1 divergence = 2.0 > 0.3
    training = [{"root_cause": "SKILL_RULE"} for _ in range(10)]
    holdout = [{"root_cause": "KNOWLEDGE", "lesson": f"lesson {i}"} for i in range(3)]
    _patch_cases(monkeypatch, training, holdout)
    _patch_suggestions(
        monkeypatch,
        # 让 lesson 都被 suggestion 覆盖，排除 coverage_gap 触发
        {
            "anti_rationalization_suggestions": [
                {"rebuttal": f"lesson {i} fully covered by suggestion"} for i in range(3)
            ]
        },
    )

    result = validate_against_holdout("Q01")
    assert result["distribution_divergence"] > 0.3
    assert result["overfitting_signal"] is True
    assert "dist_divergence" in result["decision_reason"]


def test_overfitting_by_low_hit_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    training = [{"root_cause": "SKILL_RULE"} for _ in range(3)]
    # 5 条 holdout（满足 MIN_CASES=3），只有 1 条 lesson 被覆盖 → hit_rate = 0.2 < 0.3
    holdout = [
        {"root_cause": "SKILL_RULE", "lesson": "covered lesson A"},
        {"root_cause": "SKILL_RULE", "lesson": "uncovered 1"},
        {"root_cause": "SKILL_RULE", "lesson": "uncovered 2"},
        {"root_cause": "SKILL_RULE", "lesson": "uncovered 3"},
        {"root_cause": "SKILL_RULE", "lesson": "uncovered 4"},
    ]
    _patch_cases(monkeypatch, training, holdout)
    _patch_suggestions(
        monkeypatch,
        {"anti_rationalization_suggestions": [{"rebuttal": "covered lesson A is fully included"}]},
    )

    result = validate_against_holdout("Q01")
    assert result["holdout_count"] == 5
    assert result["holdout_hit_rate"] <= 0.3
    assert result["overfitting_signal"] is True


def test_holdout_ok_returns_clean_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    # training 和 holdout 同分布，suggestions 覆盖所有 lesson
    training = [{"root_cause": "SKILL_RULE"} for _ in range(6)]
    holdout = [{"root_cause": "SKILL_RULE", "lesson": f"lesson {i}"} for i in range(4)]
    _patch_cases(monkeypatch, training, holdout)
    _patch_suggestions(
        monkeypatch,
        {
            "anti_rationalization_suggestions": [
                {"rebuttal": f"lesson {i} is fully covered by this suggestion"} for i in range(4)
            ]
        },
    )

    result = validate_against_holdout("Q01")
    assert result["holdout_ready"] is True
    assert result["overfitting_signal"] is False
    assert result["decision_reason"] == "holdout_ok"
