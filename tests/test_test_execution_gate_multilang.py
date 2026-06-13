"""Multi-language dispatch tests for test_execution_gate.

Covers:
  - Java path (language_provider=None) — unchanged behavior
  - TypeScript: success and failure paths
  - Go: compile failure, test success, test failure with failing test names
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from qualix.quality.checks.test_execution_gate import (
    _run_go_gate,
    _run_python_gate,
    _run_ts_gate,
    check_q05_test_execution,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_inputs(tmp_path: Path, code_repos: list[str]) -> None:
    """Write a minimal _inputs.json for Q05b into the expected internal dir."""
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import internal_dir as _internal_dir

    phase_def = PHASE_DEFS["Q05b"]
    int_dir = _internal_dir(tmp_path, "proj", phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)
    (int_dir / "_inputs.json").write_text(
        json.dumps({"code_repos": code_repos}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test 1: language_provider=None → Java path called
# ---------------------------------------------------------------------------


def test_java_path_no_provider(tmp_path: Path) -> None:
    """When language_provider is None and repos list is empty, gate should return
    a WARNING (no repos found), not raise, and the Java path is taken."""
    # Write inputs with empty repos list
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import internal_dir as _internal_dir

    phase_def = PHASE_DEFS["Q05b"]
    int_dir = _internal_dir(tmp_path, "proj", phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)
    (int_dir / "_inputs.json").write_text(
        json.dumps({"code_repos": []}),
        encoding="utf-8",
    )

    result = check_q05_test_execution(tmp_path, "proj", language_provider=None)
    # Empty repos → WARNING message, no BLOCKED
    assert any("WARNING" in r for r in result)
    assert not any("BLOCKED" in r for r in result)


# ---------------------------------------------------------------------------
# Test 2: TS provider run_tests() returns success → []
# ---------------------------------------------------------------------------


def test_ts_gate_success(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    with patch(
        "qualix.languages.typescript.provider.TypeScriptProvider.run_tests",
        return_value={
            "success": True,
            "stdout": "Test Suites: 1 passed",
            "stderr": "",
            "returncode": 0,
        },
    ):
        errors = _run_ts_gate([str(repo_dir)])

    assert errors == []


# ---------------------------------------------------------------------------
# Test 3: TS provider run_tests() returns failure → BLOCKED with "TypeScript tests failed"
# ---------------------------------------------------------------------------


def test_ts_gate_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    with patch(
        "qualix.languages.typescript.provider.TypeScriptProvider.run_tests",
        return_value={
            "success": False,
            "stdout": "FAIL OrderService",
            "stderr": "",
            "returncode": 1,
        },
    ):
        errors = _run_ts_gate([str(repo_dir)])

    assert len(errors) == 1
    assert "BLOCKED" in errors[0]
    assert "TypeScript tests failed" in errors[0]


# ---------------------------------------------------------------------------
# Test 4: Go compile_check fails → BLOCKED compile error
# ---------------------------------------------------------------------------


def test_go_gate_compile_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example\n\ngo 1.21\n")

    from qualix.languages.base import CompileResult

    with patch(
        "qualix.languages.go.provider.GoProvider.compile_check",
        return_value=CompileResult(
            passed=False,
            build_tool="go",
            error_summary="build failed: undefined: Foo",
        ),
    ):
        errors = _run_go_gate([str(repo_dir)])

    assert len(errors) == 1
    assert "BLOCKED" in errors[0]
    assert "compile" in errors[0].lower()
    assert "build failed" in errors[0]


# ---------------------------------------------------------------------------
# Test 5: Go compile passes, go test exits 0 with no failures → []
# ---------------------------------------------------------------------------


def test_go_gate_test_success(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example\n\ngo 1.21\n")

    from qualix.languages.base import CompileResult

    success_json_lines = "\n".join(
        [
            json.dumps({"Action": "run", "Test": "TestFoo"}),
            json.dumps({"Action": "pass", "Test": "TestFoo", "Elapsed": 0.001}),
            json.dumps({"Action": "pass", "Elapsed": 0.001}),
        ]
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = success_json_lines
    mock_proc.stderr = ""

    with patch(
        "qualix.languages.go.provider.GoProvider.compile_check",
        return_value=CompileResult(passed=True, build_tool="go", error_summary=""),
    ), patch(
        "qualix.quality.checks.test_execution_gate.subprocess.run",
        return_value=mock_proc,
    ):
        errors = _run_go_gate([str(repo_dir)])

    assert errors == []


# ---------------------------------------------------------------------------
# Test 6: Go compile passes, go test JSON has Action=fail → BLOCKED with test name
# ---------------------------------------------------------------------------


def test_go_gate_test_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example\n\ngo 1.21\n")

    from qualix.languages.base import CompileResult

    fail_json_lines = "\n".join(
        [
            json.dumps({"Action": "run", "Test": "TestFoo"}),
            json.dumps({"Action": "fail", "Test": "TestFoo", "Elapsed": 0.001}),
            json.dumps({"Action": "fail", "Elapsed": 0.001}),  # package-level fail, no Test key
        ]
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = fail_json_lines
    mock_proc.stderr = ""

    with patch(
        "qualix.languages.go.provider.GoProvider.compile_check",
        return_value=CompileResult(passed=True, build_tool="go", error_summary=""),
    ), patch(
        "qualix.quality.checks.test_execution_gate.subprocess.run",
        return_value=mock_proc,
    ):
        errors = _run_go_gate([str(repo_dir)])

    assert len(errors) == 1
    assert "BLOCKED" in errors[0]
    assert "TestFoo" in errors[0]


# ---------------------------------------------------------------------------
# Test 7: Go compile passes, go test exits non-zero with empty stdout → BLOCKED
# ---------------------------------------------------------------------------


def test_go_gate_nonzero_exit_empty_stdout(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example\n\ngo 1.21\n")

    from qualix.languages.base import CompileResult

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "linker error"

    with patch(
        "qualix.languages.go.provider.GoProvider.compile_check",
        return_value=CompileResult(passed=True, build_tool="go", error_summary=""),
    ), patch(
        "qualix.quality.checks.test_execution_gate.subprocess.run",
        return_value=mock_proc,
    ):
        errors = _run_go_gate([str(repo_dir)])

    assert len(errors) == 1
    assert "BLOCKED" in errors[0]
    assert "go test exited with code 1" in errors[0]


# ---------------------------------------------------------------------------
# Test 8: Python compile/import gate success and failure paths
# ---------------------------------------------------------------------------


def test_python_gate_success_with_src_layout(tmp_path: Path) -> None:
    repo_dir = tmp_path / "pyrepo"
    (repo_dir / "src" / "app").mkdir(parents=True)
    (repo_dir / "src" / "app" / "service.py").write_text("VALUE = 42\n", encoding="utf-8")
    (repo_dir / "tests").mkdir()
    (repo_dir / "tests" / "test_service.py").write_text(
        "from app.service import VALUE\n\n"
        "def test_value():\n"
        "    assert VALUE == 42\n",
        encoding="utf-8",
    )

    errors = _run_python_gate([str(repo_dir)])

    assert errors == []


def test_python_gate_blocks_import_error(tmp_path: Path) -> None:
    repo_dir = tmp_path / "pyrepo"
    repo_dir.mkdir()
    (repo_dir / "test_bad.py").write_text("from missing_dependency_xyz import Thing\n", encoding="utf-8")

    errors = _run_python_gate([str(repo_dir)])

    assert len(errors) == 1
    assert "BLOCKED" in errors[0]
    assert "ModuleNotFoundError" in errors[0]


def test_check_q05_dispatches_python_provider(tmp_path: Path) -> None:
    repo_dir = tmp_path / "pyrepo"
    repo_dir.mkdir()
    _write_inputs(tmp_path, [str(repo_dir)])

    provider = MagicMock()
    provider.language_id = "python"
    with patch("qualix.quality.checks.test_execution_gate._run_python_gate", return_value=[]) as run_python:
        errors = check_q05_test_execution(tmp_path, "proj", language_provider=provider)

    assert errors == []
    run_python.assert_called_once_with([str(repo_dir)])
