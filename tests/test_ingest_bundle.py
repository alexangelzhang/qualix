from pathlib import Path

import pytest

from qualix.ingest import LocalFileProvider, ingest_document
from qualix.json_utils import load_json


def test_local_file_provider_writes_standard_bundle(tmp_path: Path) -> None:
    source = tmp_path / "prd.md"
    source.write_text("# Requirement\n\nUser can approve expenses.\n", encoding="utf-8")

    bundle = ingest_document(str(source), tmp_path / "out")

    assert bundle.provider_id == "local-file"
    assert bundle.plain_text_path.read_text(encoding="utf-8").startswith("# Requirement")
    manifest = load_json(tmp_path / "out" / "manifest.json")
    source_map = load_json(tmp_path / "out" / "source_map.json")
    assert manifest["schema_version"] == 1
    assert manifest["provider_id"] == "local-file"
    assert manifest["plain_text_path"].endswith("plain_text.md")
    assert source_map["segments"][0]["segment_id"] == "SRC-001"


def test_local_file_provider_rejects_unsupported_suffix(tmp_path: Path) -> None:
    source = tmp_path / "prd.xlsx"
    source.write_text("not supported", encoding="utf-8")

    assert not LocalFileProvider().can_handle(str(source))
    with pytest.raises(ValueError, match="No document ingest provider"):
        ingest_document(str(source), tmp_path / "out")
