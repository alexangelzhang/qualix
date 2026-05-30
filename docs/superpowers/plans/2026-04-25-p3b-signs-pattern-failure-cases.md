# P3-B: Signs Pattern — Structured Failure Cases with Trigger→Do→Why

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the bug case schema with `trigger_pattern`, `wrong_action`, and `why_failed` fields, then update `render_cases_for_prompt()` to output Trigger→Do→Why format — giving developers precise causal chains instead of flat "lesson" strings.

**Architecture:** The existing `case.json` schema has `lesson` (free text) but no structured causal chain. Add 3 optional fields to the schema. Update `render_cases_for_prompt()` to prefer Trigger→Do→Why when available, falling back to `lesson` for legacy cases. No migration needed — new fields are optional, old cases work unchanged.

**Tech Stack:** Python, existing `bug_cases.py` + `regression/failure-library/`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/dqg/tracking/bug_cases.py` | Add Signs-format rendering in `render_cases_for_prompt()` |
| Modify | `src/dqg/tracking/bug_cases.py` | Add `validate_case_schema()` for new fields |
| Create | `tests/test_signs_pattern.py` | Signs rendering + schema validation tests |

---

### Task 1: Add Signs-format rendering to `render_cases_for_prompt()`

**Files:**
- Modify: `src/dqg/tracking/bug_cases.py:146-181`
- Create: `tests/test_signs_pattern.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_signs_pattern.py`:

```python
"""Test Signs pattern (Trigger→Do→Why) for failure cases."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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
    from dqg.tracking.bug_cases import _render_single_case

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
    from dqg.tracking.bug_cases import _render_single_case

    case = _make_case(
        title="遗漏异常处理分析",
        lesson="需要检查所有 catch 块是否有合理的错误处理",
    )
    rendered = _render_single_case(case, index=1)

    assert "教训" in rendered
    assert "catch 块" in rendered
    # Should NOT have Signs headers
    assert "Trigger:" not in rendered


def test_render_mixed_cases():
    """render_cases_for_prompt should handle mix of Signs and legacy cases."""
    from unittest.mock import patch

    from dqg.tracking.bug_cases import render_cases_for_prompt

    cases = [
        _make_case(
            case_id="SIGNS-001",
            severity="critical",
            title="Signs case",
            trigger_pattern="trigger-text",
            wrong_action="wrong-action-text",
            why_failed="why-text",
        ),
        _make_case(
            case_id="LEGACY-001",
            severity="high",
            title="Legacy case",
            lesson="legacy-lesson-text",
        ),
    ]

    with patch("dqg.tracking.bug_cases.load_cases_by_phase", return_value=cases):
        rendered = render_cases_for_prompt("Q03")

    assert "Trigger:" in rendered  # Signs case
    assert "教训:" in rendered     # Legacy case
    assert "trigger-text" in rendered
    assert "legacy-lesson-text" in rendered


def test_render_empty_signs_fields_uses_lesson():
    """If trigger/do/why are empty strings, fall back to lesson."""
    from dqg.tracking.bug_cases import _render_single_case

    case = _make_case(
        title="Partial case",
        trigger_pattern="",
        wrong_action="",
        why_failed="",
        lesson="fallback lesson",
    )
    rendered = _render_single_case(case, index=1)

    assert "教训" in rendered
    assert "fallback lesson" in rendered
    assert "Trigger:" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/rd-gate && python -m pytest tests/test_signs_pattern.py -v`
Expected: FAIL — `_render_single_case` does not exist

- [ ] **Step 3: Implement Signs-format rendering**

In `src/dqg/tracking/bug_cases.py`, add a helper function before `render_cases_for_prompt()`:

```python
def _render_single_case(case: dict[str, Any], index: int) -> str:
    """Render a single bug case in Signs format (Trigger→Do→Why) or legacy lesson format."""
    error_label = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(
        case.get("error_type", ""), case.get("error_type", "")
    )
    lines = [f"### 反例 {index}: {case.get('title', '')} [{error_label}]", ""]

    input_text = case.get("_input_excerpt", "")
    if input_text:
        lines.append(input_text)
        lines.append("")

    # Prefer Signs format if all three fields are present
    trigger = case.get("trigger_pattern", "").strip()
    wrong_action = case.get("wrong_action", "").strip()
    why = case.get("why_failed", "").strip()

    if trigger and wrong_action and why:
        lines.append(f"**Trigger:** {trigger}")
        lines.append(f"**Do:** {wrong_action}")
        lines.append(f"**Why:** {why}")
        lines.append("")
    else:
        # Legacy fallback
        lesson = case.get("lesson", "").strip()
        if lesson:
            lines.append(f"**教训:** {lesson}")
            lines.append("")

    return "\n".join(lines)
```

Then update `render_cases_for_prompt()` to use it:

```python
def render_cases_for_prompt(phase: str, base_dir: Path | None = None, max_cases: int = 10) -> str:
    """将指定 Phase 的 open bug 案例渲染为 markdown，用于注入 skill prompt."""
    cases = [c for c in load_cases_by_phase(phase, base_dir) if c.get("status") == "open"]
    if not cases:
        return ""

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    cases.sort(key=lambda c: severity_order.get(c.get("severity", "low"), 9))
    cases = cases[:max_cases]

    lines = [
        "## BUG_CASES — 已知判错案例（务必避免重犯）",
        "",
        f"以下是 Phase {phase} 历史上出现过的判错案例。执行时请特别注意避免同类错误。",
        "",
    ]

    for i, c in enumerate(cases, 1):
        lines.append(_render_single_case(c, i))

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_signs_pattern.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/tracking/bug_cases.py tests/test_signs_pattern.py
git commit -m "feat(bug_cases): add Signs pattern (Trigger→Do→Why) rendering for failure cases"
```

---

### Task 2: Add `validate_case_schema()` for new fields

**Files:**
- Modify: `src/dqg/tracking/bug_cases.py`
- Test: `tests/test_signs_pattern.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signs_pattern.py`:

```python
def test_validate_case_schema_valid_signs():
    """Valid Signs case should pass validation."""
    from dqg.tracking.bug_cases import validate_case_schema

    case = _make_case(
        trigger_pattern="修改了公共接口",
        wrong_action="未检查调用方",
        why_failed="爆炸半径被低估",
    )
    errors = validate_case_schema(case)
    assert len(errors) == 0


def test_validate_case_schema_partial_signs():
    """Partial Signs fields (only trigger, missing do/why) should warn."""
    from dqg.tracking.bug_cases import validate_case_schema

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
    from dqg.tracking.bug_cases import validate_case_schema

    case = _make_case(lesson="some lesson")
    errors = validate_case_schema(case)
    assert len(errors) == 0


def test_validate_case_schema_no_lesson_no_signs():
    """Case with neither lesson nor Signs fields should warn."""
    from dqg.tracking.bug_cases import validate_case_schema

    case = _make_case()
    errors = validate_case_schema(case)
    assert len(errors) >= 1
    assert any("lesson" in e.lower() or "signs" in e.lower() for e in errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signs_pattern.py::test_validate_case_schema_valid_signs -v`
Expected: FAIL — `validate_case_schema` does not exist

- [ ] **Step 3: Implement validate_case_schema**

In `src/dqg/tracking/bug_cases.py`, add:

```python
_SIGNS_FIELDS = ("trigger_pattern", "wrong_action", "why_failed")


def validate_case_schema(case: dict[str, Any]) -> list[str]:
    """Validate bug case schema, including Signs fields consistency.

    Returns list of warning messages (empty = valid).
    """
    errors: list[str] = []

    # Check Signs fields consistency: all-or-none
    signs_present = [f for f in _SIGNS_FIELDS if case.get(f, "").strip()]
    if 0 < len(signs_present) < len(_SIGNS_FIELDS):
        missing = [f for f in _SIGNS_FIELDS if f not in signs_present]
        errors.append(
            f"Signs pattern incomplete: has {', '.join(signs_present)} "
            f"but missing {', '.join(missing)}"
        )

    # Must have either Signs or lesson
    has_signs = len(signs_present) == len(_SIGNS_FIELDS)
    has_lesson = bool(case.get("lesson", "").strip())
    if not has_signs and not has_lesson:
        errors.append("Case has neither lesson nor Signs fields (trigger_pattern/wrong_action/why_failed)")

    return errors
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_signs_pattern.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/tracking/bug_cases.py tests/test_signs_pattern.py
git commit -m "feat(bug_cases): add validate_case_schema for Signs field consistency checks"
```

---

## Expected Impact

- Developers get actionable causal chains: "Trigger: X happened → Do: system did Y wrong → Why: because Z" instead of flat "lesson: check X"
- Existing cases work unchanged (new fields are optional, `lesson` fallback preserved)
- Schema validation catches incomplete Signs entries during case creation
- Future: auto-generated cases from Adaptive Loop failures can populate Signs fields from Judge feedback
