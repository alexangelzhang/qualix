import json
from pathlib import Path

from qualix.commands.ingest import run_ingest


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
