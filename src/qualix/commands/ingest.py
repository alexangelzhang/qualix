"""Workspace-level document ingest command."""

from __future__ import annotations

from pathlib import Path

from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.exceptions import IngestError
from qualix.ingest import ingest_document
from qualix.json_utils import dump_json_str


def run_ingest(source: str, project_id: str, phase_id: str = "Q01", output_root: Path | None = None) -> int:
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        print(f"Unsupported phase for ingest: {phase_id}")
        return 1
    root = output_root or Path.cwd() / ".qualix" / "output"
    phase_root = _phase_dir(root, project_id, phase_def)
    try:
        bundle = ingest_document(source, phase_root / "ingest")
    except IngestError as exc:
        print(dump_json_str({"status": "error", "error_type": "ingest_error", "message": str(exc)}))
        return 1
    print(dump_json_str(bundle.to_manifest()))
    return 0
