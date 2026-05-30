"""Tests for qualix.regression."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from qualix.tracking.regression import (
    append_failure_history,
    build_failure_trend,
    classify_diff,
    compute_exit_code,
    discover_cases,
    run_case,
    summarize_failure_library,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_case(
    case_dir: Path,
    actual_dir: Path,
    expected_files: dict[str, str],
    include: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.json").write_text(
        json.dumps(
            {
                "case_id": case_dir.name,
                "sample_type": "fixture",
                "actual_dir": str(actual_dir),
                "include": include or list(expected_files.keys()),
            }
            | (metadata or {}),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    expected_dir = case_dir / "expected"
    expected_dir.mkdir()
    for name, content in expected_files.items():
        path = expected_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_classify_diff_variants() -> None:
    assert classify_diff(expected_exists=False, actual_exists=True, changed=False) == "新增"
    assert classify_diff(expected_exists=True, actual_exists=False, changed=False) == "回归"
    assert classify_diff(expected_exists=True, actual_exists=True, changed=True) == "偏移"
    assert classify_diff(expected_exists=True, actual_exists=True, changed=False) == "一致"


def test_discover_cases(tmp_path: Path) -> None:
    actual_dir = tmp_path / "actual"
    actual_dir.mkdir()
    _write_case(tmp_path / "cases" / "demo", actual_dir, {"a.txt": "x"})

    cases = discover_cases(tmp_path / "cases")

    assert len(cases) == 1
    assert cases[0]["case_id"] == "demo"


def test_discover_cases_recurses_into_failure_library(tmp_path: Path) -> None:
    actual_dir = tmp_path / "actual"
    actual_dir.mkdir()
    _write_case(tmp_path / "cases" / "failure-library" / "fp-001", actual_dir, {"a.txt": "x"})

    cases = discover_cases(tmp_path / "cases")

    assert len(cases) == 1
    assert cases[0]["case_id"] == "fp-001"
    assert "failure-library" in cases[0]["case_dir"]


def test_run_case_reports_new_regression_and_drift(tmp_path: Path) -> None:
    actual_dir = tmp_path / "actual"
    actual_dir.mkdir()
    (actual_dir / "same.txt").write_text("same", encoding="utf-8")
    (actual_dir / "changed.txt").write_text("new", encoding="utf-8")
    (actual_dir / "new_only.txt").write_text("new only", encoding="utf-8")

    case_dir = tmp_path / "cases" / "demo"
    _write_case(
        case_dir,
        actual_dir,
        {
            "same.txt": "same",
            "changed.txt": "old",
            "missing_now.txt": "missing",
        },
        include=["same.txt", "changed.txt", "missing_now.txt", "new_only.txt"],
    )

    result = run_case(case_dir)

    by_file = {item["file"]: item["status"] for item in result["diffs"]}
    assert by_file["same.txt"] == "一致"
    assert by_file["changed.txt"] == "偏移"
    assert by_file["missing_now.txt"] == "回归"
    assert by_file["new_only.txt"] == "新增"


def test_run_case_keeps_failure_library_metadata_and_marks_passed(tmp_path: Path) -> None:
    actual_dir = tmp_path / "actual"
    actual_dir.mkdir()
    (actual_dir / "report.md").write_text("ok", encoding="utf-8")
    case_dir = tmp_path / "cases" / "failure-library" / "fn-001"
    _write_case(
        case_dir,
        actual_dir,
        {"report.md": "ok"},
        metadata={
            "library": "failure-library",
            "error_type": "漏报",
            "case_kind": "弱文档输入",
            "trigger_condition": "PRD 只给摘要，没有边界条件",
            "fix_strategy": "补充弱文档兜底规则",
            "regression_case": "phase-a-weak-doc-regression",
        },
    )

    result = run_case(case_dir)

    assert result["passed"] is True
    assert result["library"] == "failure-library"
    assert result["error_type"] == "漏报"
    assert result["trigger_condition"] == "PRD 只给摘要，没有边界条件"


def test_compute_exit_code_fails_when_failure_library_case_fails() -> None:
    results = [
        {"case_id": "fp-001", "library": "failure-library", "passed": False},
        {"case_id": "demo", "library": "curated", "passed": True},
    ]
    assert compute_exit_code(results) == 1


def test_summarize_failure_library_counts_false_positive_and_negative() -> None:
    results = [
        {"library": "failure-library", "error_type": "误报", "passed": True},
        {"library": "failure-library", "error_type": "误报", "passed": False},
        {"library": "failure-library", "error_type": "漏报", "passed": False},
    ]

    summary = summarize_failure_library(results)

    assert summary["totals"]["cases"] == 3
    assert summary["by_error_type"]["误报"]["total"] == 2
    assert summary["by_error_type"]["误报"]["failed"] == 1
    assert summary["by_error_type"]["漏报"]["failed"] == 1


def test_append_failure_history_and_build_weekly_trend(tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"
    append_failure_history(
        [
            {"library": "failure-library", "case_id": "fp-001", "error_type": "误报", "passed": False},
            {"library": "failure-library", "case_id": "fn-001", "error_type": "漏报", "passed": True},
        ],
        history_path,
        "2026-03-31",
    )
    append_failure_history(
        [
            {"library": "failure-library", "case_id": "fp-001", "error_type": "误报", "passed": True},
            {"library": "failure-library", "case_id": "fn-001", "error_type": "漏报", "passed": False},
        ],
        history_path,
        "2026-04-02",
    )

    trend = build_failure_trend(history_path, period="weekly")

    assert trend["period"] == "weekly"
    assert len(trend["weeks"]) == 1
    week = trend["weeks"][0]
    assert week["by_error_type"]["误报"]["total"] == 2
    assert week["by_error_type"]["误报"]["failed"] == 1
    assert week["by_error_type"]["漏报"]["failed"] == 1
