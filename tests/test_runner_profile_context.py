"""Tests for runner profile context checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.services.phase_service import profile_context_warnings as _profile_context_warnings

if TYPE_CHECKING:
    from pathlib import Path


def test_warns_when_report_missing_profile_context(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_dir = output_dir / "demo" / "Q07"
    phase_dir.mkdir(parents=True)
    (phase_dir / "_profile_context.md").write_text("## PROFILE_CONTEXT\n", encoding="utf-8")
    (phase_dir / "review_report.md").write_text("# Review\nNo profile section\n", encoding="utf-8")

    warnings = _profile_context_warnings(output_dir, "demo", "Q07")
    assert any("报告未包含 PROFILE_CONTEXT" in item for item in warnings)


def test_no_warning_when_report_contains_profile_context(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_dir = output_dir / "demo" / "Q06"
    phase_dir.mkdir(parents=True)
    (phase_dir / "_profile_context.md").write_text("## PROFILE_CONTEXT\n", encoding="utf-8")
    (phase_dir / "ut_audit_report.md").write_text("## PROFILE_CONTEXT\n\n# Audit\n", encoding="utf-8")

    warnings = _profile_context_warnings(output_dir, "demo", "Q06")
    assert warnings == []
