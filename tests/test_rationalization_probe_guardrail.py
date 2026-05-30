"""T11: RationalizationProbeGuardrail on Q03/Q06 structured JSON."""

from __future__ import annotations

import json
from pathlib import Path

from qualix.quality.guardrail.guardrail import GuardrailContext
from qualix.quality.guardrail.guardrail_impl import get_guardrails
from qualix.quality.guardrail.rationalization_probe import RationalizationProbeGuardrail


def test_get_guardrails_q03_includes_probe() -> None:
    names = [g.name for g in get_guardrails("Q03")]
    assert "rationalization_probe_structured" in names


def test_get_guardrails_q06_includes_probe() -> None:
    names = [g.name for g in get_guardrails("Q06")]
    assert "rationalization_probe_structured" in names


def test_q03_probe_warns_when_failure_scenario_has_pattern(tmp_path: Path) -> None:
    phase_dir = tmp_path / "Q03"
    phase_dir.mkdir()
    payload = {
        "project_id": "probe-test",
        "failure_modes": [
            {
                "business_path": "/checkout",
                "failure_scenario": "偶发失败但影响不大",
                "has_exception_handling": False,
                "status": "SAFE",
            }
        ],
        "issues": [],
    }
    (phase_dir / "phase_a6_structured.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="probe-test",
        phase_id="Q03",
        phase_dir=phase_dir,
    )
    res = RationalizationProbeGuardrail().check(ctx)[0]
    assert res.passed is False
    assert res.level.value == "WARNING"


def test_q06_clean_structured_passes(tmp_path: Path) -> None:
    phase_dir = tmp_path / "Q06"
    phase_dir.mkdir()
    payload = {
        "project_id": "probe-test",
        "findings": [
            {
                "id": "F-1",
                "severity": "BLOCKER",
                "title": "Missing coverage",
                "description": "EUT-1 has no matching test method in FooTest.",
            }
        ],
        "audit_items": [],
    }
    (phase_dir / "phase_c_structured.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="probe-test",
        phase_id="Q06",
        phase_dir=phase_dir,
    )
    res = RationalizationProbeGuardrail().check(ctx)[0]
    assert res.passed is True
