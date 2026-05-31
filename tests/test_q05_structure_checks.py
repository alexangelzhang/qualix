"""Q05a 结构合规 checks（T5）."""

import json
from pathlib import Path

from qualix.quality.checks.q05_checks._checks_coverage import (
    _check_q05_git_diff_coverage,
    _check_target_code_symbol_coverage,
)
from qualix.quality.checks.q05_structure_checks import run_q05_structure_checks
from qualix.schemas.q05_target_modules import Q05TargetModules


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


def test_target_modules_schema_accepts_legacy_keys() -> None:
    target = Q05TargetModules.model_validate(
        {
            "target_repos": ["repo"],
            "git_diff_files": ["src/policy/expense_policy.py"],
            "language_id": "python",
            "se_mappings": [{"se_id": "SE-001", "found": True, "impl_class": "ExpensePolicy"}],
            "br_mappings": [{"br_id": "BR-001", "found": False, "gap_reason": "no backend code"}],
        }
    )

    assert target.se_mappings[0].item_id == "SE-001"
    assert target.br_mappings[0].item_id == "BR-001"


def test_target_symbol_coverage_warns_when_eut_when_misses_symbol() -> None:
    target = Q05TargetModules.model_validate(
        {
            "git_diff_files": ["src/policy/expense_policy.py"],
            "code_symbols": [
                {
                    "name": "approve",
                    "kind": "function",
                    "file": "src/policy/expense_policy.py",
                    "language": "python",
                }
            ],
        }
    )

    errors = _check_target_code_symbol_coverage(
        target,
        {"eut_items": [{"eut_id": "EUT-001", "when": "ExpensePolicy.reject(request)"}]},
    )

    assert any("target_symbols_not_covered" in error for error in errors)


def test_git_diff_coverage_matches_code_symbols_per_file() -> None:
    errors = _check_q05_git_diff_coverage(
        {
            "eut_items": [
                {
                    "eut_id": "EUT-001",
                    "given": "cart request",
                    "when": "priceCart calculates discount",
                }
            ]
        },
        {
            "git_diff_files": ["src/pricing/cart.py", "src/shipping/rate.py"],
            "code_symbols": [
                {"name": "priceCart", "kind": "function", "file": "/repo/src/pricing/cart.py"},
                {"name": "quoteRate", "kind": "function", "file": "/repo/src/shipping/rate.py"},
            ],
        },
    )

    assert len(errors) == 1
    assert "rate" in errors[0]
    assert "cart" not in errors[0]


def test_q05_structure_enriches_target_modules_with_tree_sitter_symbols(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "expense_policy.py"
    src.write_text(
        """
class ExpensePolicy:
    def approve(self, request):
        return request
""".strip(),
        encoding="utf-8",
    )

    out, pid = _make_layout(tmp_path, "Q05a")
    internal = out / pid / "Q05a" / "_internal"
    (internal / "_inputs.json").write_text(json.dumps({"code_repos": [str(repo)]}), encoding="utf-8")
    (internal / "_q05_target_modules.json").write_text(
        json.dumps(
            {
                "target_repos": [str(repo)],
                "git_diff_files": ["expense_policy.py"],
                "language_id": "python",
                "se_mappings": [{"se_id": "SE-001", "found": True, "impl_class": "ExpensePolicy"}],
                "br_mappings": [{"br_id": "BR-001", "found": True, "impl_class": "ExpensePolicy"}],
            }
        ),
        encoding="utf-8",
    )
    structured = {
        "project_id": pid,
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_item": "SE-001",
                "route_type": "Happy Path",
                "given": "approved request",
                "when": "ExpensePolicy.approve(request)",
                "then": "assert result.status == 'APPROVED'",
                "then_assertion_type": "pytest_assert",
            }
        ],
        "test_cases": [],
    }
    (out / pid / "Q05a" / "phase_b_structured.json").write_text(
        json.dumps(structured, ensure_ascii=False), encoding="utf-8"
    )

    run_q05_structure_checks(out, pid, phase_id="Q05a")

    enriched = json.loads((internal / "_q05_target_modules.json").read_text(encoding="utf-8"))
    names = {symbol["name"] for symbol in enriched.get("code_symbols", [])}
    assert {"ExpensePolicy", "approve"}.issubset(names)
