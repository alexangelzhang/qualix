from __future__ import annotations

import json
from pathlib import Path

import yaml

from qualix.commands.check import _handle_workspace_check


def _stub_command_install(monkeypatch) -> None:
    monkeypatch.setattr("qualix.commands.init._install_claude_commands", lambda project_root: [])


def test_check_json_initializes_ingests_and_returns_phase_plan(tmp_path, monkeypatch, capsys):
    _stub_command_install(monkeypatch)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nA user can submit an order.\n", encoding="utf-8")
    code = tmp_path / "src"
    code.mkdir()
    monkeypatch.chdir(tmp_path)

    rc = _handle_workspace_check(
        ["demo", "--prd", "prd.md", "--code", "src", "--profile", "python-service", "--json"]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    data = payload["data"]
    assert payload["success"] is True
    assert data["model_required"] is False
    assert data["phase_reasoning_runs_in_agent"] is True
    assert data["profile_id"] == "python-service"
    assert data["code_repos"] == [str(code.resolve())]
    assert Path(data["project"]["state_path"]).exists()
    assert Path(data["prd"]["plain_text_path"]).exists()
    assert [phase["phase_id"] for phase in data["phase_plan"]] == ["Q01", "Q05a", "Q06"]
    assert data["phase_plan"][0]["commands"]["execute"] == "qualix-run demo execute Q01 --json"
    assert f"--code-repo {code.resolve()}" in data["phase_plan"][1]["commands"]["execute"]
    assert data["next_command"] == "qualix-run demo execute Q01 --json"

    settings = yaml.safe_load((tmp_path / ".qualix" / "settings.yaml").read_text(encoding="utf-8"))
    assert settings["profile"] == "python-service"
    assert settings["code_repos"] == [str(code.resolve())]


def test_check_json_is_rerunnable_and_reuses_state(tmp_path, monkeypatch, capsys):
    _stub_command_install(monkeypatch)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert _handle_workspace_check(["demo", "--prd", "prd.md", "--profile", "python-service", "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["data"]["project"]["state_created"] is True

    assert _handle_workspace_check(["demo", "--prd", "prd.md", "--profile", "python-service", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["data"]["workspace"]["initialized"] is False
    assert second["data"]["project"]["state_created"] is False
    assert second["data"]["project"]["state_existed_before"] is True


def test_check_json_reports_missing_prd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = _handle_workspace_check(["demo", "--prd", "missing.md", "--json"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "PRD not found" in payload["errors"][0]


def test_check_json_reports_missing_code_path(tmp_path, monkeypatch, capsys):
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = _handle_workspace_check(["demo", "--prd", "prd.md", "--code", "missing-src", "--json"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "code path is not a directory" in payload["errors"][0]
