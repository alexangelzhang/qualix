"""Q05 结构合规 checks（T5）."""

import json
from pathlib import Path

import pytest

from dqg.quality.checks.q05_structure_checks import run_q05_structure_checks


@pytest.fixture
def q05_layout(tmp_path: Path) -> tuple[Path, str]:
    out = tmp_path / "output"
    pid = "P1"
    q05 = out / pid / "Q05"
    q05.mkdir(parents=True)
    return out, pid


def test_eut_missing_se_blocked(q05_layout: tuple[Path, str]) -> None:
    out, pid = q05_layout
    structured = {
        "project_id": pid,
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_se": "",
                "route_type": "Happy Path",
                "given": "g",
                "when": "w",
                "then": "assertEquals(1, x)",
            }
        ],
        "test_cases": [],
    }
    (out / pid / "Q05" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False),
        encoding="utf-8",
    )
    errs = run_q05_structure_checks(out, pid)
    assert len(errs) == 1
    assert "eut_missing_se" in errs[0]


def test_wrong_directory_blocked(q05_layout: tuple[Path, str]) -> None:
    out, pid = q05_layout
    structured = {
        "project_id": pid,
        "eut_items": [],
        "test_cases": [
            {
                "id": "tc1",
                "repo": "r",
                "test_location": {"file": "mod/src/main/java/com/foo/FooTest.java", "line_start": 1},
            }
        ],
    }
    (out / pid / "Q05" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False),
        encoding="utf-8",
    )
    errs = run_q05_structure_checks(out, pid)
    assert any("wrong_directory" in e for e in errs)


def test_mock_typo_blocked(q05_layout: tuple[Path, str]) -> None:
    out, pid = q05_layout
    structured = {"project_id": pid, "eut_items": [], "test_cases": []}
    (out / pid / "Q05" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False),
        encoding="utf-8",
    )
    sup = out / pid / "Q05" / "supplemental_tests"
    sup.mkdir(parents=True)
    (sup / "Bad.java").write_text(
        "class X { void t() { when(m).getSucess(); } }\n",
        encoding="utf-8",
    )
    errs = run_q05_structure_checks(out, pid)
    assert any("mock_wrong" in e for e in errs)


def test_no_structured_returns_empty(tmp_path: Path) -> None:
    assert run_q05_structure_checks(tmp_path / "output", "x") == []
