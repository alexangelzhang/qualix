#!/usr/bin/env python3
"""Smoke-test the built wheel from a clean install location.

This catches packaging regressions that editable installs cannot see: missing
entry points, omitted package data, or commands that accidentally depend on the
source checkout as the current working directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/install the Qualix wheel and run first-run smoke checks.")
    parser.add_argument("--wheel", default=None, help="Path to an already-built wheel. Defaults to building one.")
    parser.add_argument("--skip-build", action="store_true", help="Use --wheel or dist/*.whl without building first.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary venv/workspace for debugging.")
    args = parser.parse_args()

    wheel = _resolve_wheel(args.wheel, args.skip_build)
    temp_root = Path(tempfile.mkdtemp(prefix="qualix-wheel-smoke-"))
    try:
        venv_dir = temp_root / "venv"
        workspace = temp_root / "workspace"
        workspace.mkdir()
        _create_venv(venv_dir)
        python = _venv_python(venv_dir)
        _run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd=temp_root)

        qualix_run = _venv_executable(venv_dir, "qualix-run")
        _smoke_check(qualix_run, workspace)
        _smoke_run_demo(qualix_run, workspace)
        print("installed wheel smoke passed")
        return 0
    finally:
        if args.keep_temp:
            print(f"kept temp dir: {temp_root}")
        else:
            shutil.rmtree(temp_root)


def _resolve_wheel(raw_wheel: str | None, skip_build: bool) -> Path:
    if raw_wheel:
        wheel = Path(raw_wheel).expanduser().resolve()
        if not wheel.is_file():
            raise SystemExit(f"wheel not found: {wheel}")
        return wheel

    if not skip_build:
        _run([sys.executable, "-m", "build", "--wheel"], cwd=ROOT)

    wheels = sorted((ROOT / "dist").glob("qualix-*.whl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not wheels:
        raise SystemExit("no qualix wheel found under dist/; run without --skip-build or pass --wheel")
    return wheels[0].resolve()


def _create_venv(venv_dir: Path) -> None:
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)


def _venv_python(venv_dir: Path) -> Path:
    return _venv_executable(venv_dir, "python")


def _venv_executable(venv_dir: Path, name: str) -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    executable = venv_dir / scripts_dir / f"{name}{suffix}"
    if not executable.exists():
        raise SystemExit(f"missing executable in venv: {executable}")
    return executable


def _smoke_check(qualix_run: Path, workspace: Path) -> None:
    prd = workspace / "prd.md"
    prd.write_text("# PRD\n\nA user can submit an expense request.\n", encoding="utf-8")
    code_dir = workspace / "src"
    code_dir.mkdir()
    (code_dir / "app.py").write_text("def submit_expense():\n    return True\n", encoding="utf-8")

    payload = _run_json(
        [
            str(qualix_run),
            "wheel-demo",
            "check",
            "--prd",
            str(prd),
            "--code",
            str(code_dir),
            "--profile",
            "python-service",
            "--json",
        ],
        cwd=workspace,
    )
    data = _expect_success(payload, command="check")
    _expect(data["model_required"] is False, "check should not require a model")
    _expect(data["profile_id"] == "python-service", "check should preserve the requested profile")
    _expect(data["code_repos"] == [str(code_dir.resolve())], "check should normalize code repos")
    _expect(Path(data["project"]["state_path"]).exists(), "check should create project state")
    _expect(Path(data["prd"]["plain_text_path"]).exists(), "check should ingest PRD text")
    _expect([phase["phase_id"] for phase in data["phase_plan"]] == ["Q01", "Q05a", "Q06"], "unexpected phase plan")
    q05a_execute = data["phase_plan"][1]["commands"]["execute"]
    q06_execute = data["phase_plan"][2]["commands"]["execute"]
    _expect("--json" in q05a_execute and "--code-repo" in q05a_execute, "Q05a command must include --json and --code-repo")
    _expect("--json" in q06_execute and "--code-repo" in q06_execute, "Q06 command must include --json and --code-repo")


def _smoke_run_demo(qualix_run: Path, workspace: Path) -> None:
    payload = _run_json([str(qualix_run), "expense-demo", "run-demo", "--json"], cwd=workspace)
    data = _expect_success(payload, command="run-demo")
    proof_loop = data["proof_loop"]
    _expect(proof_loop["model_required"] is False, "run-demo should not require a model")
    _expect(proof_loop["ordinary_tests"]["passed"] is True, "run-demo ordinary test signal should pass")
    _expect(proof_loop["semantic_coverage"]["missing_eut"] >= 1, "run-demo should expose a missing EUT")
    _expect(Path(proof_loop["evidence_graph_path"]).exists(), "run-demo should write an EvidenceGraph")
    _expect(proof_loop["next_command"].endswith("--json"), "run-demo next command must keep JSON contract")


def _run_json(command: list[str], cwd: Path) -> dict[str, Any]:
    result = _run(command, cwd=cwd)
    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"command did not emit pure JSON: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}") from exc
    return payload


def _expect_success(payload: dict[str, Any], *, command: str) -> dict[str, Any]:
    _expect(payload.get("schema_version") == "1", f"{command} returned unexpected schema_version")
    _expect(payload.get("command") == command, f"expected command={command}")
    _expect(payload.get("success") is True, f"{command} did not succeed: {payload}")
    _expect(payload.get("exit_code") == 0, f"{command} returned non-zero exit_code")
    data = payload.get("data")
    _expect(isinstance(data, dict), f"{command} should include data object")
    return data


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
