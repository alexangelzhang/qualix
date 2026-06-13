"""Tests for the public phase failure patterns benchmark."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.check_phase_failure_patterns import DEFAULT_MANIFEST, validate_manifest


def test_phase_failure_patterns_manifest_is_valid() -> None:
    result = validate_manifest(DEFAULT_MANIFEST)

    assert result["issues"] == []
    assert result["patterns"] == 3
    assert result["phases"] == ["Q01", "Q05a", "Q06"]


def test_phase_failure_patterns_script_outputs_json() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_phase_failure_patterns.py"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["issues"] == []
    assert payload["patterns"] == 3


def test_phase_failure_patterns_rejects_case_phase_mismatch(tmp_path: Path) -> None:
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    manifest["patterns"][0]["phase"] = "Q06"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_manifest(manifest_path)

    assert any("phase mismatch" in issue for issue in result["issues"])
