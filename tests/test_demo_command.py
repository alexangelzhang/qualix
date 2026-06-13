"""Tests for qualix-run demo command."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_args():
    args = types.SimpleNamespace()
    args.project_id = ""
    args.json = False
    return args


def test_demo_prints_q01_content(tmp_path, capsys):
    q01 = tmp_path / "q01-summary.md"
    q01.write_text("# Q01 Summary\n- SE-001: threshold rule\n", encoding="utf-8")
    q05a = tmp_path / "q05a-eut-matrix.md"
    q05a.write_text("# Q05a EUT Matrix\n- EUT-001: test boundary\n", encoding="utf-8")
    q06 = tmp_path / "q06-audit.md"
    q06.write_text("# Q06 Audit\n- HIGH: missing boundary test\n", encoding="utf-8")

    def mock_resolve(category, relative):
        mapping = {
            "expense-approval/expected/q01-summary.md": q01,
            "expense-approval/expected/q05a-eut-matrix.md": q05a,
            "expense-approval/expected/q06-audit.md": q06,
        }
        return mapping[relative]

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = mock_resolve

    with patch("qualix.core.resource_resolver.ResourceResolver", return_value=mock_resolver):
        from qualix.commands.setup import cmd_demo

        rc = cmd_demo(_make_args(), Path(tmp_path))

    assert rc == 0
    captured = capsys.readouterr()
    assert "threshold rule" in captured.out
    assert "test boundary" in captured.out
    assert "missing boundary test" in captured.out
    assert "qualix-run ingest" in captured.out
    assert "explain" in captured.out


def test_demo_handles_missing_file(tmp_path, capsys):
    def mock_resolve(category, relative):
        raise FileNotFoundError(relative)

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = mock_resolve

    with patch("qualix.core.resource_resolver.ResourceResolver", return_value=mock_resolver):
        from qualix.commands.setup import cmd_demo

        rc = cmd_demo(_make_args(), Path(tmp_path))

    assert rc == 0
    captured = capsys.readouterr()
    assert "demo file not found" in captured.out


def test_run_demo_writes_static_proof_loop_outputs(tmp_path):
    from qualix.commands.demo_proof import cmd_run_demo
    from qualix.quality.evidence_graph import EvidenceGraph

    args = types.SimpleNamespace(project_id="expense-demo", json=False)

    rc = cmd_run_demo(args, tmp_path)

    assert rc == 0
    assert (tmp_path / "expense-demo" / "Q01" / "phase_a_structured.json").exists()
    assert (tmp_path / "expense-demo" / "Q05a" / "phase_b_structured.json").exists()
    assert (tmp_path / "expense-demo" / "Q06" / "phase_c_structured.json").exists()
    assert (tmp_path / "expense-demo" / "Q06" / "_semantic_coverage_report.json").exists()
    assert (tmp_path / "expense-demo" / "Q06" / "_evidence_graph.json").exists()

    graph = EvidenceGraph.build(tmp_path, "expense-demo")
    chain = graph.query_chain("SE-003")
    assert any(claim.claim_type == "has_eut" and claim.object_id == "EUT-002" for claim in chain)
    assert any(claim.claim_type == "has_audit" and claim.object_id == "MISSING" for claim in chain)


def test_run_demo_json_output_includes_proof_summary(tmp_path, capsys):
    from qualix.commands.demo_proof import cmd_run_demo

    args = types.SimpleNamespace(project_id="expense-demo", json=True)

    rc = cmd_run_demo(args, tmp_path)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["data"]["proof_loop"]["model_required"] is False
    assert payload["data"]["proof_loop"]["ordinary_tests"]["passed"] is True
    assert payload["data"]["proof_loop"]["ordinary_tests"]["line_coverage_rate"] == 0.95
    assert payload["data"]["proof_loop"]["semantic_coverage"]["missing_eut"] >= 1


def test_run_demo_test_signal_falls_back_when_pytest_missing(tmp_path):
    from qualix.commands import demo_proof

    prd = tmp_path / "expense-approval" / "prd.md"
    prd.parent.mkdir(parents=True)
    prd.write_text("demo", encoding="utf-8")
    resolver = MagicMock()
    resolver.resolve.return_value = prd
    result = types.SimpleNamespace(returncode=1, stdout="", stderr="No module named pytest")

    with patch("qualix.commands.demo_proof.subprocess.run", return_value=result):
        signal = demo_proof._run_expense_demo_tests(resolver)

    assert signal["passed"] is True
    assert signal["line_coverage_rate"] == 0.95
    assert signal["command"] == "precomputed"


def test_runner_dispatches_run_demo() -> None:
    from qualix.core.runner import _dispatch

    handler = _dispatch("run-demo")

    assert handler.__name__ == "cmd_run_demo"
