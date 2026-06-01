import json
from pathlib import Path

from qualix.commands.ingest import run_ingest
from qualix.core.runner import _handle_workspace_ingest


def test_run_ingest_writes_q01_bundle(tmp_path: Path, capsys) -> None:
    source = tmp_path / "prd.md"
    source.write_text("# PRD\n", encoding="utf-8")
    output_root = tmp_path / "out"

    assert run_ingest(str(source), "demo", output_root=output_root) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["provider_id"] == "local-file"
    assert (output_root / "demo" / "Q01" / "ingest" / "plain_text.md").exists()
    assert (output_root / "demo" / "Q01" / "ingest" / "manifest.json").exists()


def test_run_ingest_reports_dingtalk_connector_gap(tmp_path: Path, capsys) -> None:
    assert run_ingest("https://alidocs.dingtalk.com/i/nodes/abc123", "demo", output_root=tmp_path / "out") == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert output["error_type"] == "ingest_error"
    assert "enterprise-url:dingtalk" in output["message"]


def test_workspace_ingest_uses_existing_project_output_root(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_project = project_root / "output" / "demo"
    legacy_project.mkdir(parents=True)
    (legacy_project / "state.json").write_text("{}", encoding="utf-8")
    source = tmp_path / "prd.md"
    source.write_text("# PRD\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    assert _handle_workspace_ingest([str(source), "--project", "demo"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["plain_text_path"].startswith(str(project_root / "output" / "demo"))
    assert (project_root / "output" / "demo" / "Q01" / "ingest" / "manifest.json").exists()
