"""Tests for P1 loop quality improvements."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Task 1: data_patterns sidecar
# ---------------------------------------------------------------------------


def test_write_data_patterns_uses_phase_id():
    """write_data_patterns 必须用 phase_id 调用 analyze_data_patterns，而非硬编码 'Q06'."""
    from pathlib import Path
    from unittest.mock import patch as _patch

    from dqg.tracking.data_patterns import write_data_patterns

    captured_phase = []

    def _fake_analyze(phase=None):
        captured_phase.append(phase)
        return {"top_patterns": [], "total_cases": 0, "pattern_distribution": {}, "cases_by_pattern": {}}

    with _patch("dqg.tracking.data_patterns.analyze_data_patterns", side_effect=_fake_analyze):
        write_data_patterns(Path("/tmp"), "proj", "Q05")

    assert captured_phase == ["Q05"], f"Expected ['Q05'], got {captured_phase}"


def test_analyze_data_patterns_includes_top_lessons():
    """analyze_data_patterns 返回的 top_patterns 每条应包含 top_lessons 列表."""
    from unittest.mock import patch as _patch

    from dqg.tracking.data_patterns import analyze_data_patterns

    fake_cases = [
        {
            "case_id": "c1",
            "phase": "Q05",
            "lesson": "字段映射必须显式转换枚举值",
            "title": "字段映射错误",
            "description": "金额字段未转换",
            "error_type": "field_mapping",
        },
    ]

    with (
        _patch("dqg.tracking.data_patterns.load_cases_by_phase", return_value=fake_cases),
        _patch("dqg.tracking.data_patterns.get_case_with_inferred_lesson", side_effect=lambda c: c),
    ):
        result = analyze_data_patterns("Q05")

    for pattern in result.get("top_patterns", []):
        assert "top_lessons" in pattern, f"Pattern {pattern['id']} missing top_lessons"
        assert isinstance(pattern["top_lessons"], list)
