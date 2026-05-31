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
