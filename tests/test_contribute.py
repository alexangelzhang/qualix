"""Tests for dqg.commands.contribute."""

import json
import time
from pathlib import Path

from dqg.commands.contribute import mark_contributed, run_contribute, scan_new_cases


def _make_case(cases_root: Path, case_id: str, status: str = "new") -> Path:
    case_dir = cases_root / case_id
    case_dir.mkdir(parents=True)
    case_file = case_dir / "case.json"
    case_file.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "phase": "Q01",
                "error_type": "FN",
                "severity": "P1",
                "title": f"Test case {case_id}",
                "root_cause": "test",
                "fix_target": "SKILL.md",
                "tags": [],
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status": status,
                "source": "test",
                "expected": "",
                "actual": "",
                "lesson": "",
                "case_category": "test",
            }
        )
    )
    return case_file


def test_scan_new_cases_finds_uncontributed(tmp_path):
    cases_root = tmp_path / "cases"
    _make_case(cases_root, "case-001", status="new")
    _make_case(cases_root, "case-002", status="contributed")
    _make_case(cases_root, "case-003", status="new")

    results = scan_new_cases(cases_root)
    ids = [r["case_id"] for r in results]
    assert "case-001" in ids
    assert "case-003" in ids
    assert "case-002" not in ids


def test_scan_new_cases_empty_when_all_contributed(tmp_path):
    cases_root = tmp_path / "cases"
    _make_case(cases_root, "case-001", status="contributed")
    assert scan_new_cases(cases_root) == []


def test_scan_new_cases_empty_when_dir_missing(tmp_path):
    assert scan_new_cases(tmp_path / "nonexistent") == []


def test_mark_contributed_updates_status(tmp_path):
    cases_root = tmp_path / "cases"
    f = _make_case(cases_root, "case-001", status="new")
    mark_contributed([str(f)])
    data = json.loads(f.read_text())
    assert data["status"] == "contributed"
    assert "contributed_at" in data


def test_run_contribute_no_upload_returns_cases(tmp_path):
    cases_root = tmp_path / "cases"
    _make_case(cases_root, "case-001", status="new")
    rc, cases = run_contribute(cases_root=cases_root, no_upload=True, silent=True)
    assert rc == 0
    assert len(cases) == 1
    assert cases[0]["case_id"] == "case-001"


def test_run_contribute_no_cases_returns_zero(tmp_path):
    cases_root = tmp_path / "cases"
    rc, cases = run_contribute(cases_root=cases_root, no_upload=True, silent=True)
    assert rc == 0
    assert cases == []
