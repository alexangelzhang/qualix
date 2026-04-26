"""Tests for setup commands."""

from __future__ import annotations

from types import SimpleNamespace

from dqg.commands.setup import cmd_init
from dqg.core.state_machine import load_state
from dqg.json_utils import load_json_strict


def test_init_rejects_unknown_profile(tmp_path) -> None:
    args = SimpleNamespace(project_id="demo", profile="missing-profile")

    try:
        cmd_init(args, tmp_path / "output")
    except ValueError as exc:
        assert "Unknown profile" in str(exc)
    else:
        raise AssertionError("Expected unknown profile to fail before writing state")


def test_init_reuses_existing_state_profile_for_version_file(tmp_path) -> None:
    output_dir = tmp_path / "output"
    cmd_init(SimpleNamespace(project_id="demo", profile="go-service"), output_dir)

    result = cmd_init(SimpleNamespace(project_id="demo", profile="typescript-service"), output_dir)

    state = load_state(output_dir, "demo")
    version = load_json_strict(output_dir / "demo" / "version.json")
    assert result == 0
    assert state.profile_id == "go-service"
    assert version["profile_id"] == "go-service"
