"""Q05a 结构合规 checks（T5）."""

import json
from pathlib import Path

from dqg.quality.checks.q05_structure_checks import run_q05_structure_checks


def _make_layout(tmp_path: Path, phase_dir: str) -> tuple[Path, str]:
    out = tmp_path / "output"
    pid = "P1"
    pd = out / pid / phase_dir
    pd.mkdir(parents=True)
    internal = pd / "_internal"
    internal.mkdir(parents=True)
    (internal / "_q05_target_modules.json").write_text(
        json.dumps({"se_mappings": [], "br_mappings": [], "git_diff_files": ["Dummy.java"], "target_repos": []}),
        encoding="utf-8",
    )
    return out, pid


def test_eut_missing_se_blocked(tmp_path: Path) -> None:
    out, pid = _make_layout(tmp_path, "Q05a")
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
    (out / pid / "Q05a" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False), encoding="utf-8"
    )
    errs = run_q05_structure_checks(out, pid, phase_id="Q05a")
    assert len(errs) == 1
    assert "eut_missing_se" in errs[0]


def test_wrong_directory_blocked(tmp_path: Path) -> None:
    out, pid = _make_layout(tmp_path, "Q05a")
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
    (out / pid / "Q05a" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False), encoding="utf-8"
    )
    errs = run_q05_structure_checks(out, pid, phase_id="Q05a")
    assert any("wrong_directory" in e for e in errs)


def test_mock_typo_blocked(tmp_path: Path) -> None:
    out, pid = _make_layout(tmp_path, "Q05a")
    structured = {"project_id": pid, "eut_items": [], "test_cases": []}
    (out / pid / "Q05a" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False), encoding="utf-8"
    )
    sup = out / pid / "Q05a" / "supplemental_tests"
    sup.mkdir(parents=True)
    (sup / "Bad.java").write_text("class X { void t() { when(m).getSucess(); } }\n", encoding="utf-8")
    errs = run_q05_structure_checks(out, pid, phase_id="Q05a")
    assert any("mock_wrong" in e for e in errs)


def test_no_structured_returns_empty(tmp_path: Path) -> None:
    assert run_q05_structure_checks(tmp_path / "output", "x") == []


def test_legacy_q05_path_still_works(tmp_path: Path) -> None:
    """Legacy Q05 directory path (backward compat)."""
    out, pid = _make_layout(tmp_path, "Q05")
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
    (out / pid / "Q05" / "phase_b_structured.json").write_text(json.dumps(structured, ensure_ascii=False))
    errs = run_q05_structure_checks(out, pid)  # default phase_id="Q05"
    assert len(errs) == 1
    assert "eut_missing_se" in errs[0]
