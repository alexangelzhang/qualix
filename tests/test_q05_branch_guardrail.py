"""Q05 分支覆盖 Guardrail."""

import json
from pathlib import Path

from dqg.quality.guardrail.guardrail import GuardrailContext
from dqg.quality.guardrail.q05_branch_coverage import Q05BranchCoverageGuardrail


def test_skips_when_no_inventory(tmp_path: Path) -> None:
    q5 = tmp_path / "P" / "Q05"
    q5.mkdir(parents=True)
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="P",
        phase_id="Q05",
        phase_dir=q5,
    )
    r = Q05BranchCoverageGuardrail().check(ctx)[0]
    assert not r.passed  # 无分支清单 = WARNING，不能当作 pass
    assert "Step A" in r.message or "分支清单" in r.message


def test_blocks_when_exception_branch_but_no_exception_eut(tmp_path: Path) -> None:
    q5 = tmp_path / "P" / "Q05"
    internal = q5 / "_internal"
    internal.mkdir(parents=True)
    inv = {
        "targets": [
            {
                "branches": [
                    {"id": "b1", "kind": "happy"},
                    {"id": "b2", "kind": "exception"},
                ]
            }
        ]
    }
    (internal / "_q05_branch_inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    structured = {
        "project_id": "P",
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_se": "SE-001",
                "route_type": "Happy Path",
                "given": "g",
                "when": "w",
                "then": "assertEquals(1,1)",
            }
        ],
    }
    (q5 / "phase_b_structured.json").write_text(json.dumps(structured), encoding="utf-8")
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="P",
        phase_id="Q05",
        phase_dir=q5,
    )
    r = Q05BranchCoverageGuardrail().check(ctx)[0]
    assert not r.passed
    assert "Exception" in r.message


def test_blocks_when_boundary_branch_but_no_boundary_eut(tmp_path: Path) -> None:
    q5 = tmp_path / "P" / "Q05"
    internal = q5 / "_internal"
    internal.mkdir(parents=True)
    inv = {
        "targets": [
            {
                "branches": [
                    {"id": "b1", "kind": "happy"},
                    {"id": "b2", "kind": "boundary"},
                ]
            }
        ]
    }
    (internal / "_q05_branch_inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    structured = {
        "project_id": "P",
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_se": "SE-001",
                "route_type": "Happy Path",
                "given": "g",
                "when": "w",
                "then": "assertEquals(1,1)",
            }
        ],
    }
    (q5 / "phase_b_structured.json").write_text(json.dumps(structured), encoding="utf-8")
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="P",
        phase_id="Q05",
        phase_dir=q5,
    )
    results = Q05BranchCoverageGuardrail().check(ctx)
    boundary_result = next((r for r in results if "边界" in r.message or "Boundary" in r.message), None)
    assert boundary_result is not None
    assert not boundary_result.passed


def test_passes_when_both_exception_and_boundary_covered(tmp_path: Path) -> None:
    q5 = tmp_path / "P" / "Q05"
    internal = q5 / "_internal"
    internal.mkdir(parents=True)
    inv = {
        "targets": [
            {
                "branches": [
                    {"id": "b1", "kind": "exception"},
                    {"id": "b2", "kind": "boundary"},
                ]
            }
        ]
    }
    (internal / "_q05_branch_inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    structured = {
        "project_id": "P",
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_se": "SE-001",
                "route_type": "Exception",
                "given": "g",
                "when": "w",
                "then": "assertThrows(Exception.class, () -> sut.call())",
            },
            {
                "eut_id": "EUT-002",
                "bound_se": "SE-001",
                "route_type": "Boundary",
                "given": "null input",
                "when": "w",
                "then": "assertEquals('', result)",
            },
        ],
    }
    (q5 / "phase_b_structured.json").write_text(json.dumps(structured), encoding="utf-8")
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="P",
        phase_id="Q05",
        phase_dir=q5,
    )
    results = Q05BranchCoverageGuardrail().check(ctx)
    assert all(r.passed for r in results)
