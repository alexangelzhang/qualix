"""Tests for qualix-run <project> explain <se-id>."""

from __future__ import annotations

import json
import types
from pathlib import Path


def _make_args(se_id: str, json_mode: bool = False) -> types.SimpleNamespace:
    args = types.SimpleNamespace()
    args.project_id = "test-proj"
    args.se_id = se_id
    args.json = json_mode
    return args


def _write_fixtures(tmp_path: Path) -> Path:
    proj = tmp_path / "test-proj"
    q01 = proj / "Q01"
    q01.mkdir(parents=True)
    q05a = proj / "Q05a"
    q05a.mkdir(parents=True)
    q06 = proj / "Q06"
    q06.mkdir(parents=True)

    (q01 / "phase_a_structured.json").write_text(json.dumps({
        "semantic_expectations": [
            {
                "se_id": "SE-003",
                "description": "Requests at or above 500 USD require manager AND finance approval.",
                "bound_reqs": ["REQ-002"],
                "confidence": "High",
                "source": "prd.md:24",
            },
            {
                "se_id": "SE-001",
                "description": "Every status change sends exactly one requester notification.",
                "bound_reqs": ["REQ-001"],
                "confidence": "High",
                "source": "prd.md:16",
            },
        ]
    }))

    (q05a / "phase_b_structured.json").write_text(json.dumps({
        "eut_items": [
            {"eut_id": "EUT-005", "bound_se": "SE-003", "description": "test boundary at exactly 500 USD"},
            {"eut_id": "EUT-006", "bound_se": "SE-003", "description": "test above 500 USD"},
            {"eut_id": "EUT-001", "bound_se": "SE-001", "description": "notification sent on approval"},
        ]
    }))

    (q06 / "phase_c_structured.json").write_text(json.dumps({
        "audit_items": [
            {
                "eut_id": "EUT-005",
                "status": "MISSING",
                "severity": "HIGH",
                "finding": "Boundary at exactly 500 USD never tested.",
                "recommendation": "Add test with amount=Decimal('500')",
            },
            {
                "eut_id": "EUT-006",
                "status": "COVERED",
                "severity": "LOW",
                "finding": "",
                "recommendation": "",
            },
        ]
    }))

    return tmp_path


class TestExplainText:
    def test_se003_shows_euts_and_findings(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("SE-003"), output_dir)
        out = capsys.readouterr().out
        assert rc == 0
        assert "SE-003" in out
        assert "500 USD" in out
        assert "EUT-005" in out
        assert "EUT-006" in out
        assert "MISSING" in out
        assert "COVERED" in out
        # recommendation shown for non-covered items
        assert "Decimal" in out

    def test_se001_no_audit_items(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("SE-001"), output_dir)
        out = capsys.readouterr().out
        assert rc == 0
        assert "SE-001" in out
        assert "EUT-001" in out
        # no Q06 findings for SE-001 EUTs in fixture
        assert "MISSING" not in out

    def test_unknown_se_returns_1(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("SE-999"), output_dir)
        assert rc == 1
        err = capsys.readouterr().err
        assert "SE-999" in err
        assert "not found" in err

    def test_case_insensitive(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("se-003"), output_dir)
        assert rc == 0


class TestExplainJson:
    def test_json_output_structure(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("SE-003", json_mode=True), output_dir)
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["success"] is True
        assert data["data"]["se"]["se_id"] == "SE-003"
        assert len(data["data"]["euts"]) == 2
        assert any(a["eut_id"] == "EUT-005" for a in data["data"]["audit_items"])

    def test_json_error_on_missing_se(self, tmp_path, capsys):
        output_dir = _write_fixtures(tmp_path)
        from qualix.commands.explain import cmd_explain
        rc = cmd_explain(_make_args("SE-000", json_mode=True), output_dir)
        assert rc == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["success"] is False
        assert "SE-000" in data["errors"][0]
