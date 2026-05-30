"""Tests for SkillReflector reflect→write→verify loop."""

from qualix.tracking.skill_reflector import (
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


# ---------------------------------------------------------------------------
# 2026-05-10 — absorb 闭环补强：NOOP_DEDUPED + REVERTED + trace 字段
# ---------------------------------------------------------------------------


def _make_writable_skill(tmp_path, phase: str = "Q01", initial_content: str | None = None):
    """构造一个可写 skill 文件并把 SKILL_FILE_MAP 指向它.

    `qualix.tracking.skill_reflector` 用 `from qualix.constants import SKILL_FILE_MAP` 做 module-level import，
    因此必须 patch reflector 模块上的 alias（而非 constants 原件）才能生效。
    """
    from qualix import constants

    skill = tmp_path / "SKILL.md"
    skill.write_text(
        initial_content
        if initial_content is not None
        else "# Phase\n\n## Anti-Rationalization\n\n| x | y |\n\n## 红线规则\n\n- existing rule\n",
        encoding="utf-8",
    )
    patched = dict(constants.SKILL_FILE_MAP)
    patched[phase] = str(skill)
    return skill, patched


def test_write_noop_deduped_when_all_rules_already_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _skill, patched = _make_writable_skill(
        tmp_path,
        initial_content='## Anti-Rationalization\n\n| "already there rule" | rebuttal |\n',
    )
    monkeypatch.setattr("qualix.tracking.skill_reflector.SKILL_FILE_MAP", patched)
    monkeypatch.setattr(
        "qualix.tracking.skill_auto_merge.verify_with_holdout",
        lambda phase, allow_fail_open=False: True,
    )

    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    result = reflector.write(
        ReflectResult(
            actionable=True,
            root_cause="SKILL_RULE",
            failure_patterns=["dup"],
            suggested_changes=["already there rule"],
        ),
        support_count=5,
    )
    assert result.mode == "NOOP_DEDUPED"
    assert result.skipped_duplicates == ["already there rule"]


def test_write_reverted_when_holdout_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill, patched = _make_writable_skill(tmp_path)
    monkeypatch.setattr("qualix.tracking.skill_reflector.SKILL_FILE_MAP", patched)
    monkeypatch.setattr(
        "qualix.tracking.skill_auto_merge.verify_with_holdout",
        lambda phase, allow_fail_open=False: False,
    )

    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    result = reflector.write(
        ReflectResult(
            actionable=True,
            root_cause="SKILL_RULE",
            failure_patterns=["p"],
            suggested_changes=["brand new rule that definitely is not there"],
        ),
        support_count=5,
    )
    assert result.mode == "REVERTED"
    content = skill.read_text(encoding="utf-8")
    assert "brand new rule that definitely is not there" not in content


def test_write_auto_apply_exposes_diff_and_inserted_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill, patched = _make_writable_skill(tmp_path)
    monkeypatch.setattr("qualix.tracking.skill_reflector.SKILL_FILE_MAP", patched)
    monkeypatch.setattr(
        "qualix.tracking.skill_auto_merge.verify_with_holdout",
        lambda phase, allow_fail_open=False: True,
    )

    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    result = reflector.write(
        ReflectResult(
            actionable=True,
            root_cause="SKILL_RULE",
            failure_patterns=["p"],
            suggested_changes=["fresh rule added"],
        ),
        support_count=5,
    )
    assert result.mode == "AUTO_APPLY"
    assert result.inserted_entries
    assert "fresh rule added" in result.rendered_diff
    assert "fresh rule added" in skill.read_text(encoding="utf-8")


def test_reflect_and_write_action_maps_noop_deduped(tmp_path, monkeypatch):
    """end-to-end: reflect_and_write 应当把 NOOP_DEDUPED 模式映射到 action='NOOP_DEDUPED'."""
    monkeypatch.chdir(tmp_path)
    _skill, patched = _make_writable_skill(
        tmp_path,
        initial_content='## Anti-Rationalization\n\n| "existing pattern" | rebut |\n',
    )
    monkeypatch.setattr("qualix.tracking.skill_reflector.SKILL_FILE_MAP", patched)
    monkeypatch.setattr(
        "qualix.tracking.skill_auto_merge.verify_with_holdout",
        lambda phase, allow_fail_open=False: True,
    )
    monkeypatch.setattr(
        SkillReflector,
        "_classify_root_cause",
        lambda self, issues: ("SKILL_RULE", "pattern", "existing pattern"),
    )
    monkeypatch.setattr(SkillReflector, "cluster_and_count_support", lambda self, case_id: 5)

    reflector = SkillReflector(phase="Q01", project_id="test-proj")
    outcome = reflector.reflect_and_write(
        [
            {"verdict": "FAIL", "overall": 2.0, "issues": [{"description": "existing pattern seen again"}]},
            {"verdict": "FAIL", "overall": 2.0, "issues": [{"description": "existing pattern seen once more"}]},
        ]
    )
    assert outcome.action == "NOOP_DEDUPED"
