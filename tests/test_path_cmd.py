from __future__ import annotations

from unittest.mock import patch

from qualix.commands.path_cmd import run_path


def test_path_skills(tmp_path, capsys):
    """Should print the resolved skills directory."""
    global_qualix = tmp_path / ".qualix"
    (global_qualix / "skills" / "Q01").mkdir(parents=True)
    with patch("qualix.commands.path_cmd.ResourceResolver") as MockResolver:
        instance = MockResolver.return_value
        instance.resolve_dir.return_value = global_qualix / "skills"
        rc = run_path("skills")
    assert rc == 0
    captured = capsys.readouterr()
    assert str(global_qualix / "skills") in captured.out


def test_path_unknown_category(capsys):
    """Unknown category should fail with helpful message."""
    rc = run_path("unknown-category")
    assert rc != 0
    captured = capsys.readouterr()
    assert "未知类别" in captured.out or "unknown" in captured.out.lower()


def test_path_not_found(capsys):
    """If resolve_dir raises FileNotFoundError, print error and exit non-zero."""
    with patch("qualix.commands.path_cmd.ResourceResolver") as MockResolver:
        instance = MockResolver.return_value
        instance.resolve_dir.side_effect = FileNotFoundError("not found")
        rc = run_path("skills")
    assert rc != 0
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "错误" in captured.out
