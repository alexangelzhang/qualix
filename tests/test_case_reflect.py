"""T10: case_reflect.apply_reflect_metadata."""

from __future__ import annotations

from dqg.tracking.case_category import CASE_CATEGORIES
from dqg.tracking.case_reflect import REFLECT_LESSON_MAX_LEN, apply_reflect_metadata


def test_apply_reflect_fills_empty_lesson_and_category() -> None:
    case = {
        "case_id": "T-REFLECT-1",
        "phase": "Q05",
        "error_type": "WRONG",
        "severity": "medium",
        "title": "missing required field x",
        "root_cause": "SCHEMA",
        "fix_target": "",
        "tags": [],
        "lesson": "",
        "source": {},
    }
    out = apply_reflect_metadata(case)
    assert out["lesson"].strip()
    assert len(out["lesson"]) <= REFLECT_LESSON_MAX_LEN
    assert out["case_category"] in CASE_CATEGORIES


def test_apply_reflect_preserves_existing_lesson() -> None:
    case = {
        "case_id": "T-REFLECT-2",
        "phase": "Q05",
        "title": "x",
        "root_cause": "SCHEMA",
        "lesson": "已有人工教训" * 20,
        "case_category": "STRUCTURED_SCHEMA",
    }
    out = apply_reflect_metadata(case)
    assert out["lesson"] == case["lesson"]
    assert out["case_category"] == "STRUCTURED_SCHEMA"
