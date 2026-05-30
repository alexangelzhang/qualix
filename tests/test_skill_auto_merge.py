"""Tests for qualix.tracking.skill_auto_merge."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qualix.tracking.skill_auto_merge import (
    ApplyResult,
    MarkdownSectionEditor,
    apply_to_skill_file,
    verify_with_holdout,
)

if TYPE_CHECKING:
    import pytest


# ---------------------------------------------------------------------------
# MarkdownSectionEditor
# ---------------------------------------------------------------------------


def test_editor_scans_atx_headings_and_bodies() -> None:
    lines = [
        "# Top",
        "line under top",
        "## Section A",
        "body-a1",
        "body-a2",
        "### Subsection A.1",
        "body-a11",
        "## Section B",
        "body-b",
    ]
    editor = MarkdownSectionEditor(lines)
    sec_a = editor.find_section("Section A")
    sec_b = editor.find_section("Section B")
    sub = editor.find_section("A.1")

    assert sec_a is not None and sec_b is not None and sub is not None
    # Section A body 覆盖 "body-a1" / "body-a2" / "### Subsection A.1" / "body-a11"，到 Section B 前停
    assert editor.section_body(sec_a) == [
        "body-a1",
        "body-a2",
        "### Subsection A.1",
        "body-a11",
    ]
    # Subsection A.1 body 仅 "body-a11"
    assert editor.section_body(sub) == ["body-a11"]
    # Section B body 仅 "body-b"
    assert editor.section_body(sec_b) == ["body-b"]


def test_editor_skips_headings_inside_fenced_code_blocks() -> None:
    lines = [
        "## Real Section",
        "```",
        "## Fake Heading Inside Code",
        "```",
        "real body",
        "## Another Real",
        "x",
    ]
    editor = MarkdownSectionEditor(lines)
    assert editor.find_section("Fake Heading Inside Code") is None
    assert editor.find_section("Real Section") is not None
    assert editor.find_section("Another Real") is not None


def test_editor_contains_in_body_idempotent_check() -> None:
    lines = [
        "## Anti-Rationalization",
        '| "already covered rule text" | rebuttal |',
    ]
    editor = MarkdownSectionEditor(lines)
    sec = editor.find_section("Anti-Rationalization")
    assert sec is not None
    assert editor.contains_in_body(sec, "already covered rule text") is True
    assert editor.contains_in_body(sec, "brand new rule that was never there") is False


# ---------------------------------------------------------------------------
# apply_to_skill_file — 基础
# ---------------------------------------------------------------------------


def _write_skill(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_apply_inserts_into_anti_rat_section(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        "# Phase Q01\n\n## Anti-Rationalization\n\n| excuse | rebuttal |\n|---|---|\n\n## 其他\n",
    )
    result = apply_to_skill_file(str(skill), ["边界值必须覆盖 null / 空字符串"])
    assert isinstance(result, ApplyResult)
    assert result.applied is True
    assert len(result.inserted_entries) == 1
    assert "Anti-Rationalization" in result.sections_touched
    content = skill.read_text(encoding="utf-8")
    assert "边界值必须覆盖 null / 空字符串" in content


def test_apply_falls_back_to_red_line_section(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "# Q01\n\n## 红线规则\n\n- 现有规则\n\n## 其他\n")
    result = apply_to_skill_file(str(skill), ["新的禁止事项"])
    assert result.applied is True
    assert "红线规则" in result.sections_touched
    assert "- 新的禁止事项" in skill.read_text(encoding="utf-8")


def test_apply_creates_auto_merged_section_at_eof(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "# Q01\n\n## 无匹配 section 的内容\n\n普通文本\n")
    result = apply_to_skill_file(str(skill), ["fallback 规则"])
    assert result.applied is True
    assert "Auto-merged Rules" in result.sections_touched
    content = skill.read_text(encoding="utf-8")
    assert "## Auto-merged Rules" in content
    assert "- fallback 规则" in content


# ---------------------------------------------------------------------------
# apply_to_skill_file — 幂等 / 长规则不截断 / dry_run
# ---------------------------------------------------------------------------


def test_apply_is_idempotent_second_call_skips_duplicate(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "## Anti-Rationalization\n\n| x | y |\n")
    rule = "完全相同的规则原文 X Y Z 必须不重复插入"
    first = apply_to_skill_file(str(skill), [rule])
    assert first.applied is True

    second = apply_to_skill_file(str(skill), [rule])
    assert second.applied is False
    assert second.skipped_duplicates == [rule]
    assert second.inserted_entries == []
    # 表格行本身含两次 rule（excuse + rebuttal 栏），但行数只有一条
    content = skill.read_text(encoding="utf-8")
    assert content.count(f'| "{rule}" | {rule} |') == 1


def test_apply_does_not_truncate_long_rule(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "## Anti-Rationalization\n\n| x | y |\n")
    long_rule = (
        "这是一个超过六十个字符的长规则描述，用来测试 rule_text[:60] 截断 bug 是否已经被修复，"
        "正确的行为应该是完整保留所有字符不做任何截断"
    )
    assert len(long_rule) > 60
    result = apply_to_skill_file(str(skill), [long_rule])
    assert result.applied is True
    content = skill.read_text(encoding="utf-8")
    assert long_rule in content


def test_apply_dry_run_does_not_write_but_returns_diff(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "## Anti-Rationalization\n\n| x | y |\n")
    original = skill.read_text(encoding="utf-8")
    result = apply_to_skill_file(str(skill), ["规则 A", "规则 B"], dry_run=True)
    assert result.applied is False  # dry_run 永远 False
    assert len(result.inserted_entries) == 2
    assert "Inserted:" in result.rendered_diff
    # 未写盘
    assert skill.read_text(encoding="utf-8") == original


def test_apply_multiple_rules_mix_of_new_and_duplicate(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        '## Anti-Rationalization\n\n| "already there" | already there |\n',
    )
    result = apply_to_skill_file(str(skill), ["already there", "brand new rule"])
    assert result.applied is True
    assert result.skipped_duplicates == ["already there"]
    assert len(result.inserted_entries) == 1
    assert "brand new rule" in result.rendered_diff


def test_apply_empty_changes_returns_not_applied(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "## Anti-Rationalization\n\n")
    result = apply_to_skill_file(str(skill), [])
    assert result.applied is False
    assert result.inserted_entries == []


def test_apply_missing_file_returns_not_applied(tmp_path: Path) -> None:
    result = apply_to_skill_file(str(tmp_path / "nonexistent.md"), ["rule"])
    assert result.applied is False


# ---------------------------------------------------------------------------
# verify_with_holdout — fail-open 关闭后的行为
# ---------------------------------------------------------------------------


def test_verify_rejects_on_exception_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(phase: str) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        _raise,
    )
    assert verify_with_holdout("Q01") is False


def test_verify_allows_fail_open_on_exception_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(phase: str) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        _raise,
    )
    assert verify_with_holdout("Q01", allow_fail_open=True) is True


def test_verify_rejects_when_holdout_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        lambda phase: {
            "overfitting_signal": False,
            "holdout_ready": False,
            "decision_reason": "no_holdout_cases",
        },
    )
    assert verify_with_holdout("Q01") is False


def test_verify_allows_when_holdout_not_ready_with_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        lambda phase: {
            "overfitting_signal": False,
            "holdout_ready": False,
            "decision_reason": "no_holdout_cases",
        },
    )
    assert verify_with_holdout("Q01", allow_fail_open=True) is True


def test_verify_rejects_on_overfitting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        lambda phase: {
            "overfitting_signal": True,
            "holdout_ready": True,
            "coverage_gap": 0.8,
            "distribution_divergence": 0.4,
            "holdout_hit_rate": 0.2,
            "decision_reason": "overfitting: coverage_gap=0.80 > 0.5",
        },
    )
    assert verify_with_holdout("Q01") is False


def test_verify_allows_when_holdout_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "qualix.quality.eval.eval_holdout.validate_against_holdout",
        lambda phase: {
            "overfitting_signal": False,
            "holdout_ready": True,
            "decision_reason": "holdout_ok",
        },
    )
    assert verify_with_holdout("Q01") is True
