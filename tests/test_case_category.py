"""case_category 推断与 lesson 兜底."""

from qualix.tracking.case_category import CASE_CATEGORIES, infer_case_category
from qualix.tracking.lesson_inference import infer_lesson_with_fallback


def test_case_categories_five() -> None:
    assert len(CASE_CATEGORIES) == 5


def test_infer_structured_from_validation_title() -> None:
    c = {"title": "validation errors for Phase Q03", "phase": "Q03", "root_cause": "SCHEMA"}
    assert infer_case_category(c) == "STRUCTURED_SCHEMA"


def test_infer_cross_phase() -> None:
    c = {"title": "Phase Q06 审计了 EUT-999 但 Q05 不存在", "phase": "Q06", "root_cause": "SCHEMA"}
    assert infer_case_category(c) == "CROSS_PHASE_IDS"


def test_infer_lesson_with_fallback_never_empty() -> None:
    c = {"title": "unknown", "phase": "Q01", "root_cause": "KNOWLEDGE", "tags": []}
    s = infer_lesson_with_fallback(c)
    assert len(s) > 10


def test_validate_case_category_invalid() -> None:
    from qualix.tracking.bug_cases import validate_case_schema

    errs = validate_case_schema({"lesson": "x", "case_category": "NOT_A_REAL_CATEGORY"})
    assert any("case_category" in e for e in errs)
