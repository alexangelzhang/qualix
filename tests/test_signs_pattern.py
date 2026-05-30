"""Test Signs pattern (Trigger→Do→Why) for failure cases."""

from __future__ import annotations


def _make_case(
    case_id: str = "TEST-001",
    phase: str = "Q03",
    title: str = "Test case",
    error_type: str = "FN",
    severity: str = "high",
    status: str = "open",
    lesson: str = "",
    trigger_pattern: str = "",
    wrong_action: str = "",
    why_failed: str = "",
) -> dict:
    return {
        "case_id": case_id,
        "phase": phase,
        "title": title,
        "error_type": error_type,
        "severity": severity,
        "status": status,
        "lesson": lesson,
        "trigger_pattern": trigger_pattern,
        "wrong_action": wrong_action,
        "why_failed": why_failed,
        "_input_excerpt": "",
    }


def test_render_signs_format():
    """Cases with trigger/do/why should render in Signs format."""
    from qualix.tracking.bug_cases import _render_single_case

    case = _make_case(
        title="公共接口变更未更新调用方",
        trigger_pattern="修改了公共接口签名但没更新调用方",
        wrong_action="只检查了被修改文件本身的编译，未检查 impact 列表中的 d=1 调用方",
        why_failed="公共接口变更的爆炸半径通常被低估，需要检查所有直接调用方",
    )
    rendered = _render_single_case(case, index=1)
    assert "Trigger" in rendered
    assert "Do" in rendered
    assert "Why" in rendered
    assert "公共接口变更" in rendered
    assert "d=1 调用方" in rendered


def test_render_legacy_lesson_fallback():
    """Cases without trigger/do/why should fall back to lesson format."""
    from qualix.tracking.bug_cases import _render_single_case

    case = _make_case(
        title="遗漏异常处理分析",
        lesson="需要检查所有 catch 块是否有合理的错误处理",
    )
    rendered = _render_single_case(case, index=1)
    assert "教训" in rendered
    assert "catch 块" in rendered
    assert "Trigger:" not in rendered


def test_render_mixed_cases():
    """render_cases_for_prompt should handle mix of Signs and legacy cases."""
    from unittest.mock import patch

    from qualix.tracking.bug_cases import render_cases_for_prompt

    cases = [
        _make_case(
            case_id="SIGNS-001",
            severity="critical",
            title="Signs case",
            trigger_pattern="trigger-text",
            wrong_action="wrong-action-text",
            why_failed="why-text",
        ),
        _make_case(case_id="LEGACY-001", severity="high", title="Legacy case", lesson="legacy-lesson-text"),
    ]
    with patch("qualix.tracking.bug_cases.load_cases_by_phase", return_value=cases):
        rendered = render_cases_for_prompt("Q03")
    assert "Trigger:" in rendered
    assert "教训:" in rendered
    assert "trigger-text" in rendered
    assert "legacy-lesson-text" in rendered


def test_render_empty_signs_fields_uses_lesson():
    """If trigger/do/why are empty strings, fall back to lesson."""
    from qualix.tracking.bug_cases import _render_single_case

    case = _make_case(
        title="Partial case", trigger_pattern="", wrong_action="", why_failed="", lesson="fallback lesson"
    )
    rendered = _render_single_case(case, index=1)
    assert "教训" in rendered
    assert "fallback lesson" in rendered
    assert "Trigger:" not in rendered


def test_validate_case_schema_valid_signs():
    """Valid Signs case should pass validation."""
    from qualix.tracking.bug_cases import validate_case_schema

    case = _make_case(
        trigger_pattern="修改了公共接口",
        wrong_action="未检查调用方",
        why_failed="爆炸半径被低估",
    )
    errors = validate_case_schema(case)
    assert len(errors) == 0


def test_validate_case_schema_partial_signs():
    """Partial Signs fields (only trigger, missing do/why) should warn."""
    from qualix.tracking.bug_cases import validate_case_schema

    case = _make_case(
        trigger_pattern="有 trigger",
        wrong_action="",
        why_failed="",
    )
    errors = validate_case_schema(case)
    assert len(errors) == 1
    assert "incomplete" in errors[0].lower() or "Signs" in errors[0]


def test_validate_case_schema_legacy_ok():
    """Legacy case with lesson but no Signs fields is valid."""
    from qualix.tracking.bug_cases import validate_case_schema

    case = _make_case(lesson="some lesson")
    errors = validate_case_schema(case)
    assert len(errors) == 0


def test_validate_case_schema_no_lesson_no_signs():
    """Case with neither lesson nor Signs fields should warn."""
    from qualix.tracking.bug_cases import validate_case_schema

    case = _make_case()
    errors = validate_case_schema(case)
    assert len(errors) >= 1
    assert any("lesson" in e.lower() or "signs" in e.lower() for e in errors)
