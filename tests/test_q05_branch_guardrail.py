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
    assert r.passed
    assert "跳过" in r.message


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
