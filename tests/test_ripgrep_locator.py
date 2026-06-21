from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_ripgrep_locator_returns_eut_scoped_file_line_candidates(tmp_path: Path) -> None:
    from qualix.locator import EvidenceKind, RipgrepLocator

    repo = tmp_path / "repo"
    src = repo / "src"
    tests = repo / "tests"
    src.mkdir(parents=True)
    tests.mkdir()
    (src / "approval.py").write_text(
        "def approve(amount):\n"
        "    if amount > 500:\n"
        "        return 'FINANCE_REQUIRED'\n"
        "    return 'MANAGER_ONLY'\n",
        encoding="utf-8",
    )
    (tests / "test_approval.py").write_text(
        "from src.approval import approve\n\n"
        "def test_600_requires_finance():\n"
        "    assert approve(600) == 'FINANCE_REQUIRED'\n",
        encoding="utf-8",
    )

    citations = RipgrepLocator().locate(
        query="approval 500 FINANCE_REQUIRED",
        code_repos=[repo],
        phase="Q06",
        se_id="SE-003",
        eut_id="EUT-005",
        limit=10,
        context_lines=1,
    )

    assert citations
    assert {c.eut_id for c in citations} == {"EUT-005"}
    assert any(c.kind == EvidenceKind.TEST and c.path == "tests/test_approval.py" for c in citations)
    assert any(c.kind == EvidenceKind.IMPLEMENTATION and c.path == "src/approval.py" for c in citations)
    assert all(c.line_start >= 1 for c in citations)
    assert all(c.locator == "ripgrep" for c in citations)


def test_ripgrep_locator_does_not_emit_se_aggregated_citations(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from qualix.locator import EvidenceCitation

    try:
        EvidenceCitation(path="x.py", line_start=1, eut_id="SE-003")
    except ValidationError as exc:
        assert "EUT-" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("EvidenceCitation accepted a non-EUT id")


def test_cmd_locate_json_output_is_candidate_only(tmp_path: Path, capsys) -> None:
    from qualix.commands.locate import cmd_locate

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "policy.py").write_text("THRESHOLD = 500\n", encoding="utf-8")

    args = SimpleNamespace(
        project_id="demo",
        phase="Q06",
        eut_id="EUT-003",
        se_id="SE-003",
        query="THRESHOLD 500",
        code_repo=str(repo),
        limit=5,
        context_lines=0,
        json=True,
    )

    rc = cmd_locate(args, tmp_path)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["data"]["contract"] == "candidate_evidence_only"
    assert payload["data"]["eut_id"] == "EUT-003"
    assert payload["data"]["citations"][0]["eut_id"] == "EUT-003"
    assert payload["data"]["citations"][0]["path"] == "policy.py"


def test_cmd_locate_reports_missing_repo_as_json_error(tmp_path: Path, capsys) -> None:
    from qualix.commands.locate import cmd_locate

    args = SimpleNamespace(
        project_id="demo",
        phase="Q06",
        eut_id="EUT-003",
        se_id="",
        query="threshold",
        code_repo=str(tmp_path / "missing"),
        limit=5,
        context_lines=0,
        json=True,
    )

    rc = cmd_locate(args, tmp_path)

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "code repo is not a directory" in payload["errors"][0]
