"""Tests for qualix-run demo command."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_args():
    args = types.SimpleNamespace()
    args.project_id = ""
    args.json = False
    return args


def test_demo_prints_q01_content(tmp_path, capsys):
    q01 = tmp_path / "q01-summary.md"
    q01.write_text("# Q01 Summary\n- SE-001: threshold rule\n", encoding="utf-8")
    q05a = tmp_path / "q05a-eut-matrix.md"
    q05a.write_text("# Q05a EUT Matrix\n- EUT-001: test boundary\n", encoding="utf-8")
    q06 = tmp_path / "q06-audit.md"
    q06.write_text("# Q06 Audit\n- HIGH: missing boundary test\n", encoding="utf-8")

    def mock_resolve(category, relative):
        mapping = {
            "expense-approval/expected/q01-summary.md": q01,
            "expense-approval/expected/q05a-eut-matrix.md": q05a,
            "expense-approval/expected/q06-audit.md": q06,
        }
        return mapping[relative]

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = mock_resolve

    with patch("qualix.core.resource_resolver.ResourceResolver", return_value=mock_resolver):
        from qualix.commands.setup import cmd_demo

        rc = cmd_demo(_make_args(), Path(tmp_path))

    assert rc == 0
    captured = capsys.readouterr()
    assert "threshold rule" in captured.out
    assert "test boundary" in captured.out
    assert "missing boundary test" in captured.out
    assert "qualix-run ingest" in captured.out
    assert "explain" in captured.out


def test_demo_handles_missing_file(tmp_path, capsys):
    def mock_resolve(category, relative):
        raise FileNotFoundError(relative)

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = mock_resolve

    with patch("qualix.core.resource_resolver.ResourceResolver", return_value=mock_resolver):
        from qualix.commands.setup import cmd_demo

        rc = cmd_demo(_make_args(), Path(tmp_path))

    assert rc == 0
    captured = capsys.readouterr()
    assert "demo file not found" in captured.out
