"""cli_json / phase_spec / phase_contract_builder — 5 个 Gap 修复的单测."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# ============ Gap #4/#5: cli_envelope 新字段 ============


def test_envelope_always_has_schema_version() -> None:
    from dqg.commands.cli_json import CLI_ENVELOPE_SCHEMA_VERSION, cli_envelope

    e = cli_envelope(command="spec", project_id="p", success=True, exit_code=0)
    assert e["schema_version"] == CLI_ENVELOPE_SCHEMA_VERSION
    assert e["success"] is True
    assert e["command"] == "spec"


def test_envelope_errors_only_when_provided() -> None:
    from dqg.commands.cli_json import cli_envelope

    e_ok = cli_envelope(command="spec", project_id="p", success=True, exit_code=0)
    assert "errors" not in e_ok

    e_fail = cli_envelope(
        command="spec",
        project_id="p",
        success=False,
        exit_code=2,
        errors=["missing --phase"],
    )
    assert e_fail["errors"] == ["missing --phase"]


def test_envelope_warnings_and_notices() -> None:
    from dqg.commands.cli_json import cli_envelope

    e = cli_envelope(
        command="execute",
        project_id="p",
        success=True,
        exit_code=0,
        warnings=["Q04 未跑"],
        notices=["[worktree] output 重定向到 /main/output"],
    )
    assert e["warnings"] == ["Q04 未跑"]
    assert e["notices"] == ["[worktree] output 重定向到 /main/output"]


def test_envelope_empty_lists_not_included() -> None:
    """空列表视为未提供，不进 envelope，保持向后兼容."""
    from dqg.commands.cli_json import cli_envelope

    e = cli_envelope(
        command="spec",
        project_id="p",
        success=True,
        exit_code=0,
        errors=[],
        warnings=[],
    )
    assert "errors" not in e
    assert "warnings" not in e


# ============ Gap #2: spec 无副作用（build_phase_contract 纯函数）============


def test_build_phase_contract_does_not_write(tmp_path: Path) -> None:
    from dqg.runtime.phase_contract_builder import build_phase_contract

    c = build_phase_contract(tmp_path, "test-proj", "Q01")
    assert c is not None
    assert c["phase_id"] == "Q01"
    # 不应写盘
    internal = tmp_path / "test-proj" / "phaseA" / "_internal"
    assert not internal.exists() or not (internal / "_phase_contract.json").exists()


def test_build_phase_contract_unknown_phase_returns_none(tmp_path: Path) -> None:
    from dqg.runtime.phase_contract_builder import build_phase_contract

    assert build_phase_contract(tmp_path, "test-proj", "QXX") is None


def test_generate_phase_contract_still_writes(tmp_path: Path) -> None:
    """generate_phase_contract 必须仍然写盘（向后兼容 execute 流程）."""
    from dqg.runtime.phase_contract import generate_phase_contract

    p = generate_phase_contract(tmp_path, "test-proj", "Q01")
    assert p is not None
    assert p.exists()


# ============ Gap #3: JSON Schema mode + validator 说明 ============


def test_json_schema_uses_serialization_mode() -> None:
    from dqg.schemas.schema_export import json_schema_for_phase

    sc = json_schema_for_phase("Q01")
    assert sc is not None
    # serialization mode 生成的 schema 必有 properties（根 Model 是 object）
    assert "properties" in sc or "$ref" in sc or "$defs" in sc


def test_json_schema_unknown_phase() -> None:
    from dqg.schemas.schema_export import json_schema_for_phase

    assert json_schema_for_phase("QXX") is None


# ============ Gap #1: stderr 泄漏修复 ============


def test_resolve_output_dir_quiet_suppresses_stderr(tmp_path: Path, capsys) -> None:
    """非 git 目录不触发 worktree 分支；quiet=True 时不应有 stderr 输出."""
    from dqg.core.runner import _resolve_output_dir

    result = _resolve_output_dir(str(tmp_path), quiet=True)
    captured = capsys.readouterr()
    assert result == tmp_path.resolve() / "output"
    assert captured.err == ""


def test_resolve_output_dir_non_quiet_default(tmp_path: Path) -> None:
    """默认 quiet=False，不传也能正常用."""
    from dqg.core.runner import _resolve_output_dir

    result = _resolve_output_dir(str(tmp_path))
    assert result == tmp_path.resolve() / "output"


# ============ Gap #2 集成：cmd_spec 走 envelope + 不写 contract ============


def test_cmd_spec_missing_phase_returns_envelope_errors(tmp_path: Path) -> None:
    from dqg.commands.cli_json import CLI_ENVELOPE_SCHEMA_VERSION
    from dqg.commands.phase_spec import cmd_spec

    args = SimpleNamespace(project_id="p", phase=None)

    captured = []
    with patch("builtins.print", side_effect=lambda obj: captured.append(obj)):
        rc = cmd_spec(args, tmp_path)
    assert rc == 2
    payload = json.loads(captured[0])
    assert payload["schema_version"] == CLI_ENVELOPE_SCHEMA_VERSION
    assert payload["success"] is False
    assert "missing --phase" in payload["errors"]


def test_cmd_spec_unknown_phase_returns_envelope_errors(tmp_path: Path) -> None:
    from dqg.commands.phase_spec import cmd_spec

    args = SimpleNamespace(project_id="p", phase="QXX")

    captured = []
    with patch("builtins.print", side_effect=lambda obj: captured.append(obj)):
        rc = cmd_spec(args, tmp_path)
    assert rc == 1
    payload = json.loads(captured[0])
    assert payload["success"] is False
    assert any("unknown phase" in e for e in payload["errors"])


def test_cmd_spec_success_does_not_write_contract(tmp_path: Path) -> None:
    """spec 成功路径不应写盘 _phase_contract.json."""
    from dqg.commands.phase_spec import cmd_spec

    args = SimpleNamespace(project_id="p", phase="Q01")
    captured = []
    with patch("builtins.print", side_effect=lambda obj: captured.append(obj)):
        rc = cmd_spec(args, tmp_path)
    assert rc == 0
    payload = json.loads(captured[0])
    assert payload["success"] is True
    assert payload["phase_id"] == "Q01"
    assert "contract" in payload["data"]
    assert "json_schema" in payload["data"]

    # 关键：spec 不写盘
    contract_file = tmp_path / "p" / "phaseA" / "_internal" / "_phase_contract.json"
    assert not contract_file.exists()
