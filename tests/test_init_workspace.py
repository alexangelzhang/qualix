"""Tests for .qualix/ workspace creation and CLAUDE.md guardrail injection in cmd_init."""

from __future__ import annotations

import types
from pathlib import Path


def _make_args(project_id: str = "test-proj", profile: str = "python-service") -> types.SimpleNamespace:
    args = types.SimpleNamespace()
    args.project_id = project_id
    args.profile = profile
    args.json = False
    return args


def test_init_creates_qualix_workspace(tmp_path):
    from qualix.commands.setup import cmd_init

    output_dir = tmp_path / "output"
    cmd_init(_make_args(), output_dir)

    qualix_dir = tmp_path / ".qualix"
    assert qualix_dir.is_dir(), ".qualix/ should be created"
    assert (qualix_dir / "profiles").is_dir()
    assert (qualix_dir / "skill-overrides").is_dir()
    settings = qualix_dir / "settings.yaml"
    assert settings.exists(), "settings.yaml should be created"
    content = settings.read_text()
    assert "Qualix user workspace settings" in content


def test_init_workspace_idempotent(tmp_path):
    from qualix.commands.setup import cmd_init

    output_dir = tmp_path / "output"
    cmd_init(_make_args(), output_dir)

    # Write custom content to settings.yaml
    settings = tmp_path / ".qualix" / "settings.yaml"
    settings.write_text("profile: go-service\n")

    # Second init should not overwrite
    cmd_init(_make_args(), output_dir)
    assert settings.read_text() == "profile: go-service\n"


def test_init_appends_guardrail_to_claude_md(tmp_path):
    from qualix.commands.setup import cmd_init

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nExisting content.\n")

    output_dir = tmp_path / "output"
    cmd_init(_make_args(), output_dir)

    content = claude_md.read_text()
    assert "## Qualix Usage" in content
    assert "pip install qualix" in content
    assert "qualix-run doctor" in content


def test_init_guardrail_idempotent(tmp_path):
    from qualix.commands.setup import cmd_init

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\n## Qualix Usage\n\nAlready present.\n")

    output_dir = tmp_path / "output"
    cmd_init(_make_args(), output_dir)

    content = claude_md.read_text()
    # Should not duplicate the section
    assert content.count("## Qualix Usage") == 1


def test_init_skips_guardrail_when_no_claude_md(tmp_path):
    from qualix.commands.setup import cmd_init

    output_dir = tmp_path / "output"
    cmd_init(_make_args(), output_dir)

    # No CLAUDE.md should not be created automatically
    assert not (tmp_path / "CLAUDE.md").exists()
