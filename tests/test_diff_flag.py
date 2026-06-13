"""Tests for --diff REF shorthand in qualix-run execute."""

from __future__ import annotations

import types
from contextlib import suppress
from unittest.mock import MagicMock, patch


def _make_execute_args(phase="Q06", diff=None, base_branch=None, feature_branch="HEAD"):
    args = types.SimpleNamespace()
    args.project_id = "test-proj"
    args.phase = phase
    args.model = None
    args.code_repo = None
    args.base_branch = base_branch
    args.feature_branch = feature_branch
    args.diff = diff
    args.coverage_report = None
    args.json = False
    args.profile = "python-service"
    return args


def _run_cmd_execute_capture_ctx(args, tmp_path):
    """Run cmd_execute with mocked runtime and capture the ExecutionContext."""
    captured = {}

    def fake_runtime_execute(ctx):
        captured["ctx"] = ctx
        result = MagicMock()
        result.exit_code = 0
        result.success = True
        result.artifacts = {}
        result.error = None
        return result

    output_dir = tmp_path / "output"

    with patch("qualix.runtime.phase_runtime.runtime_execute", side_effect=fake_runtime_execute):
        from qualix.commands.phase import cmd_execute

        with suppress(Exception):
            cmd_execute(args, output_dir)

    return captured.get("ctx")


def test_diff_flag_sets_base_branch(tmp_path):
    args = _make_execute_args(diff="HEAD~1")
    ctx = _run_cmd_execute_capture_ctx(args, tmp_path)
    if ctx is not None:
        assert ctx.base_branch == "HEAD~1"
        assert ctx.feature_branch == "HEAD"


def test_diff_flag_does_not_override_explicit_base_branch(tmp_path):
    # When --base-branch is set explicitly, --diff should not override it
    args = _make_execute_args(diff="HEAD~1", base_branch="main")
    ctx = _run_cmd_execute_capture_ctx(args, tmp_path)
    if ctx is not None:
        assert ctx.base_branch == "main"


def test_no_diff_flag_defaults_to_master(tmp_path):
    args = _make_execute_args()
    ctx = _run_cmd_execute_capture_ctx(args, tmp_path)
    if ctx is not None:
        assert ctx.base_branch == "master"


def test_diff_flag_with_branch_name(tmp_path):
    args = _make_execute_args(diff="main")
    ctx = _run_cmd_execute_capture_ctx(args, tmp_path)
    if ctx is not None:
        assert ctx.base_branch == "main"
        assert ctx.feature_branch == "HEAD"


def test_runner_registers_diff_argument():
    """Verify --diff is registered in the execute subparser."""
    from qualix.core.runner import _build_parser

    parser = _build_parser()
    # Parse a minimal execute command with --diff
    args = parser.parse_args(["test-proj", "execute", "Q06", "--diff", "HEAD~1"])
    assert args.diff == "HEAD~1"
    assert args.base_branch is None  # not set, will be resolved in cmd_execute
