"""Tests for Q06 evidence locator context sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from qualix.context.context_loader import LoadedContext
from qualix.core.model_registry import get_model_profile
from qualix.core.state_machine import PhaseStatus, ProjectState, save_state


def _prepare_state(output_dir: Path, project_id: str = "demo") -> None:
    state = ProjectState(project_id=project_id)
    state.phases["Q01"].status = PhaseStatus.APPROVED
    state.phases["Q05a"].status = PhaseStatus.APPROVED
    state.phases["Q05b"].status = PhaseStatus.APPROVED
    save_state(output_dir, state)


def _empty_context() -> LoadedContext:
    from qualix.context.loading.context_loader import ContextChunk

    return LoadedContext(
        phase_id="Q06",
        model=get_model_profile(None),
        chunks=[
            ContextChunk(
                source="stub context",
                content="stub",
                token_estimate=1,
                priority=0,
            )
        ],
        total_tokens=1,
        budget_tokens=8_000,
    )


def _q06_args(code_repo: str) -> SimpleNamespace:
    return SimpleNamespace(
        project_id="demo",
        phase="Q06",
        profile=None,
        model=None,
        code_repo=code_repo,
        base_branch="master",
        feature_branch="HEAD",
        coverage_report=None,
    )


def test_write_q06_evidence_citation_context_is_eut_scoped(tmp_path: Path) -> None:
    from qualix.context.evidence_locator import (
        SIDECAR_CONTRACT,
        write_q06_evidence_citation_context,
    )

    output_dir = tmp_path / "output"
    q05a_dir = output_dir / "demo" / "Q05a"
    q05a_dir.mkdir(parents=True)
    (q05a_dir / "phase_b_structured.json").write_text(
        json.dumps(
            {
                "project_id": "demo",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_item": "SE-001",
                        "given": "amount is 500",
                        "when": "approve expense",
                        "then": "assertEquals(APPROVED, status)",
                        "route_type": "Happy Path",
                        "then_assertion_type": "assertEquals",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    test_dir = repo / "src/test/java/demo"
    test_dir.mkdir(parents=True)
    (test_dir / "ExpenseApprovalTest.java").write_text(
        "class ExpenseApprovalTest { void t(){ assertEquals(APPROVED, status); } }",
        encoding="utf-8",
    )

    paths = write_q06_evidence_citation_context(output_dir, "demo", [str(repo)])

    assert paths is not None
    json_path, md_path = paths
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["contract"] == SIDECAR_CONTRACT
    assert payload["items"][0]["eut_id"] == "EUT-001"
    assert payload["items"][0]["citations"]
    assert all(c["eut_id"] == "EUT-001" for c in payload["items"][0]["citations"])
    assert "candidate evidence only" in md_path.read_text(encoding="utf-8")


def test_q06_evidence_citation_query_uses_description_and_test_location(tmp_path: Path) -> None:
    from qualix.context.evidence_locator import write_q06_evidence_citation_context

    output_dir = tmp_path / "output"
    q05a_dir = output_dir / "demo" / "Q05a"
    q05a_dir.mkdir(parents=True)
    (q05a_dir / "phase_b_structured.json").write_text(
        json.dumps(
            {
                "project_id": "demo",
                "eut_items": [
                    {
                        "eut_id": "EUT-003",
                        "bound_se": "SE-003",
                        "description": "Above-threshold request waits for finance at 600.00 USD.",
                        "test_location": {
                            "file": "tests/test_expense_policy.py",
                            "line_start": 21,
                            "class_name": "",
                            "method_name": "test_large_request_waits_for_finance",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    test_dir = repo / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_expense_policy.py").write_text(
        "def test_large_request_waits_for_finance():\n"
        "    request = make_request(amount_usd='600.00')\n"
        "    approved = approve_by_manager(request)\n"
        "    assert approved.status == 'MANAGER_APPROVED'\n",
        encoding="utf-8",
    )

    paths = write_q06_evidence_citation_context(output_dir, "demo", [str(repo)], limit_per_eut=10)

    assert paths is not None
    json_path, _ = paths
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    item = payload["items"][0]
    assert "Above-threshold request waits for finance" in item["query"]
    assert "test_large_request_waits_for_finance" in item["query"]
    assert any(c["kind"] == "test" and c["path"] == "tests/test_expense_policy.py" for c in item["citations"])
    assert all(c["eut_id"] == "EUT-003" for c in item["citations"])


def test_q06_evidence_citations_sidecar_is_injected_into_context(tmp_path: Path) -> None:
    from qualix.context.loading.context_loader import load_context

    output_dir = tmp_path / "output"
    _prepare_state(output_dir)
    internal = output_dir / "demo" / "Q06" / "_internal"
    internal.mkdir(parents=True)
    (internal / "_evidence_citations.md").write_text(
        "# Q06 Evidence Citation Candidates\n\n- EUT-001 candidate evidence only\n",
        encoding="utf-8",
    )

    loaded = load_context(output_dir, "demo", "Q06")
    rendered = loaded.render_evidence_pack()

    assert "Q06 Evidence Citation Candidates" in rendered
    assert "candidate evidence only" in rendered


def test_phase_c_execute_generates_q06_evidence_citation_sidecar(monkeypatch, tmp_path: Path) -> None:
    from qualix.commands.phase import cmd_execute

    output_dir = tmp_path / "output"
    _prepare_state(output_dir)
    q05a_dir = output_dir / "demo" / "Q05a"
    q05a_dir.mkdir(parents=True, exist_ok=True)
    (q05a_dir / "phase_b_structured.json").write_text(
        json.dumps(
            {
                "project_id": "demo",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_item": "SE-001",
                        "given": "amount is 500",
                        "when": "approve expense",
                        "then": "assertEquals(APPROVED, status)",
                        "route_type": "Happy Path",
                        "then_assertion_type": "assertEquals",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    (repo / "src/test/java/demo").mkdir(parents=True)
    (repo / "src/test/java/demo/ExpenseApprovalTest.java").write_text(
        "class ExpenseApprovalTest { void t(){ assertEquals(APPROVED, status); } }",
        encoding="utf-8",
    )

    monkeypatch.setattr("qualix.context.context_loader.load_context", lambda *args, **kwargs: _empty_context())
    monkeypatch.setattr("qualix.reporting.telemetry.append_record", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.services.phase_service.write_phase_profile_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.context.doc_summary.generate_summary_file", lambda *args, **kwargs: None)

    exit_code = cmd_execute(_q06_args(str(repo)), output_dir)

    assert exit_code == 0
    internal = output_dir / "demo" / "Q06" / "_internal"
    assert (internal / "_evidence_citations.json").exists()
    assert (internal / "_evidence_citations.md").exists()


def test_cmd_execute_preloads_q06_evidence_citations_into_first_context(monkeypatch, tmp_path: Path) -> None:
    from qualix.commands.phase import cmd_execute

    output_dir = tmp_path / "output"
    _prepare_state(output_dir)
    q05a_dir = output_dir / "demo" / "Q05a"
    q05a_dir.mkdir(parents=True, exist_ok=True)
    (q05a_dir / "phase_b_structured.json").write_text(
        json.dumps(
            {
                "project_id": "demo",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_item": "SE-001",
                        "given": "amount is 500",
                        "when": "approve expense",
                        "then": "assertEquals(APPROVED, status)",
                        "route_type": "Happy Path",
                        "then_assertion_type": "assertEquals",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    (repo / "src/test/java/demo").mkdir(parents=True)
    (repo / "src/test/java/demo/ExpenseApprovalTest.java").write_text(
        "class ExpenseApprovalTest { void t(){ assertEquals(APPROVED, status); } }",
        encoding="utf-8",
    )

    monkeypatch.setattr("qualix.reporting.telemetry.append_record", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.services.phase_service.write_phase_profile_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.context.doc_summary.generate_summary_file", lambda *args, **kwargs: None)

    exit_code = cmd_execute(_q06_args(str(repo)), output_dir)

    assert exit_code == 0
    upstream_context = output_dir / "demo" / "Q06" / "_internal" / "_upstream_context.md"
    assert "Q06 Evidence Citation Candidates" in upstream_context.read_text(encoding="utf-8")
    assert "candidate evidence only" in upstream_context.read_text(encoding="utf-8")
