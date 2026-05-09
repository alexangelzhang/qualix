import json
from pathlib import Path

from dqg.reporting.guard_precision_report import (
    build_guard_precision_summary,
    write_guard_precision_report,
)


def test_build_summary_counts(tmp_path: Path) -> None:
    proj = tmp_path / "output" / "demo" / "Q05" / "_internal"
    proj.mkdir(parents=True)
    payload = [
        {"guardrail": "finalize_checks", "passed": True, "level": "INFO"},
        {"guardrail": "finalize_checks", "passed": False, "level": "BLOCKED"},
    ]
    (proj / "_guardrail_results.json").write_text(json.dumps(payload), encoding="utf-8")
    s = build_guard_precision_summary(tmp_path / "output")
    assert s["guardrail_files_read"] >= 1
    assert s["by_guard"]["finalize_checks"]["pass"] == 1
    assert s["by_guard"]["finalize_checks"]["fail"] == 1


def test_write_report_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "gp.md"
    p = write_guard_precision_report(tmp_path / "missing_output", dest=dest)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Guard 精度周报" in text
