"""Tests for SkillReflector reflect→write→verify loop."""

from dqg.tracking.skill_reflector import (
    EvolutionOutcome,
    ReflectResult,
    SkillReflector,
    compute_case_fingerprint,
)


def test_compute_case_fingerprint():
    fp1 = compute_case_fingerprint("Q01", "FN", "SKILL_RULE", "missing boundary check")
    fp2 = compute_case_fingerprint("Q01", "FN", "SKILL_RULE", "missing boundary check")
    fp3 = compute_case_fingerprint("Q01", "FP", "SKILL_RULE", "missing boundary check")
    assert fp1 == fp2
    assert fp1 != fp3


def test_reflect_extracts_patterns():
    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    judge_results = [
        {
            "verdict": "FAIL",
            "overall": 2.0,
            "issues": [
                {"severity": "high", "description": "missing boundary test for concurrent access"},
            ],
        },
        {
            "verdict": "FAIL",
            "overall": 2.5,
            "issues": [
                {"severity": "high", "description": "missing boundary test for null input"},
            ],
        },
        {
            "verdict": "FAIL",
            "overall": 2.0,
            "issues": [
                {"severity": "high", "description": "missing boundary test for edge case"},
            ],
        },
    ]
    result = reflector.reflect(judge_results)
    assert result.actionable is True
    assert result.root_cause == "SKILL_RULE"
    assert len(result.failure_patterns) > 0


def test_reflect_not_actionable_on_empty():
    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    result = reflector.reflect([{"verdict": "PASS", "overall": 4.0, "issues": []}])
    assert result.actionable is False


def test_write_low_confidence_returns_human_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    reflect_result = ReflectResult(
        actionable=True,
        root_cause="SKILL_RULE",
        failure_patterns=["missing boundary"],
        suggested_changes=["add boundary check rule"],
    )
    result = reflector.write(reflect_result, support_count=1)
    assert result.mode == "HUMAN_REVIEW"


def test_write_context_root_cause_auto_applies(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    reflect_result = ReflectResult(
        actionable=True,
        root_cause="CONTEXT",
        failure_patterns=["token budget too low"],
        suggested_changes=["increase budget"],
    )
    result = reflector.write(reflect_result, support_count=5)
    assert result.mode == "AUTO_APPLY"


def test_evolution_outcome_to_dict():
    outcome = EvolutionOutcome(action="SKIP", reason="no pattern")
    d = outcome.to_dict()
    assert d["action"] == "SKIP"
    assert d["reason"] == "no pattern"
