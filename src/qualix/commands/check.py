"""`qualix-run <pid> check --prd <path>` — one-command quick start.

Collapses the manual init → ingest → execute-Q01/Q05a/Q06 sequence into a
single command. It does NOT run phase reasoning itself: phase skills execute
inside the AI coding agent, so `check` initializes the workspace, ingests the
PRD, and prints the ordered skill instructions for the agent to follow.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.settings import load_settings
from qualix.core.state_machine import load_state, save_state

# The minimal semantic-coverage path: structure requirements, design test
# targets around business behavior, then audit whether tests prove them.
CHECK_PHASES = ["Q01", "Q05a", "Q06"]


def _handle_workspace_check(argv: list[str]) -> int:
    """workspace-level `qualix-run <pid> check --prd <source> [--code <dir>]`."""
    parser = argparse.ArgumentParser(
        prog="qualix-run <pid> check",
        description="Quick start: init + ingest a PRD, then run the Q01→Q05a→Q06 semantic-coverage path.",
    )
    parser.add_argument("project_id", help="Project id, e.g. my-service")
    parser.add_argument("--prd", required=True, help="Path to the PRD document (Markdown/text/html)")
    parser.add_argument("--code", action="append", default=[], help="Path to a code directory under test (repeatable)")
    parser.add_argument("--profile", default=None, help="Language/domain profile, e.g. python-service")
    parser.add_argument("--json", action="store_true", help="Emit one JSON envelope on stdout")
    args = parser.parse_args(argv)

    project_root = Path.cwd()
    prd_path = _resolve_existing_file(args.prd, project_root)
    if prd_path is None:
        return _check_error(args, 2, f"PRD not found: {args.prd}")

    code_repos, code_errors = _resolve_code_repos(args.code, project_root)
    if code_errors:
        return _check_error(args, 2, "; ".join(code_errors))

    workspace_created, init_stdout, init_rc = _ensure_workspace(project_root, args.profile)
    if init_rc != 0:
        return _check_error(args, init_rc, "workspace init failed", warnings=_stdout_lines(init_stdout))

    settings_profile, settings_code_repos = _load_workspace_settings(project_root)
    profile_id = args.profile or settings_profile or "java-ddd-tmf"
    if code_repos:
        _write_workspace_settings(project_root, profile_id, code_repos)
    elif settings_code_repos:
        code_repos = settings_code_repos

    profile_id, profile_error = _resolve_profile_id(profile_id)
    if profile_error:
        return _check_error(args, 2, profile_error)

    output_dir = project_root / ".qualix" / "output"
    state_path = output_dir / args.project_id / "state.json"
    state_existed_before = state_path.exists()
    state = load_state(output_dir, args.project_id)
    state.profile_id = profile_id
    save_state(output_dir, state)

    ingest_rc, ingest_stdout = _capture_stdout(
        _run_ingest,
        str(prd_path),
        args.project_id,
        output_dir,
    )
    ingest_payload = _parse_json_stdout(ingest_stdout)
    if ingest_rc != 0:
        message = str(ingest_payload.get("message") or "PRD ingest failed") if ingest_payload else "PRD ingest failed"
        return _check_error(args, ingest_rc, message, warnings=_stdout_lines(init_stdout))

    phase_plan = _build_phase_plan(args.project_id, code_repos)
    payload = {
        "model_required": False,
        "phase_reasoning_runs_in_agent": True,
        "project_id": args.project_id,
        "profile_id": profile_id,
        "workspace": {
            "root": str(project_root),
            "initialized": workspace_created,
            "settings_path": str(project_root / ".qualix" / "settings.yaml"),
        },
        "project": {
            "output_dir": str(output_dir / args.project_id),
            "state_path": str(state_path),
            "state_created": not state_existed_before,
            "state_existed_before": state_existed_before,
        },
        "prd": {
            "input_path": str(prd_path),
            "ingested": True,
            "provider_id": ingest_payload.get("provider_id") if ingest_payload else None,
            "plain_text_path": ingest_payload.get("plain_text_path") if ingest_payload else None,
            "manifest_path": str(output_dir / args.project_id / "Q01" / "ingest" / "manifest.json"),
        },
        "code_repos": code_repos,
        "phase_plan": phase_plan,
        "next_command": phase_plan[0]["commands"]["execute"],
    }

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="check",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra=payload,
                notices=_stdout_lines(init_stdout),
            )
        )
        return 0

    _print_human_check(args.project_id, payload)
    return 0


def _check_error(args: argparse.Namespace, exit_code: int, message: str, warnings: list[str] | None = None) -> int:
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="check",
                project_id=args.project_id,
                success=False,
                exit_code=exit_code,
                errors=[message],
                warnings=warnings,
            )
        )
    else:
        print(f"error: {message}", file=sys.stderr)
    return exit_code


def _resolve_existing_file(raw_path: str, project_root: Path) -> Path | None:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    return path if path.is_file() else None


def _resolve_code_repos(raw_values: list[str], project_root: Path) -> tuple[list[str], list[str]]:
    repos: list[str] = []
    errors: list[str] = []
    for raw_value in raw_values:
        for part in raw_value.split(","):
            item = part.strip()
            if not item:
                continue
            path = Path(item).expanduser()
            if not path.is_absolute():
                path = project_root / path
            path = path.resolve()
            if not path.is_dir():
                errors.append(f"code path is not a directory: {item}")
                continue
            repos.append(str(path))
    return list(dict.fromkeys(repos)), errors


def _ensure_workspace(project_root: Path, profile: str | None) -> tuple[bool, str, int]:
    settings_path = project_root / ".qualix" / "settings.yaml"
    output_dir = project_root / ".qualix" / "output"
    if settings_path.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return False, "", 0

    from qualix.commands.init import run_init

    force = (project_root / ".qualix").exists()
    rc, stdout = _capture_stdout(run_init, project_root, profile, force)
    return rc == 0, stdout, rc


def _load_workspace_settings(project_root: Path) -> tuple[str | None, list[str]]:
    try:
        settings = load_settings(project_root)
    except FileNotFoundError:
        return None, []
    return settings.profile, settings.code_repos


def _write_workspace_settings(project_root: Path, profile_id: str, code_repos: list[str]) -> None:
    settings_path = project_root / ".qualix" / "settings.yaml"
    try:
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw["profile"] = profile_id
    raw["code_repos"] = code_repos
    if not raw.get("qualix_version"):
        from qualix.commands.init import _get_qualix_version

        raw["qualix_version"] = _get_qualix_version()
    settings_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _resolve_profile_id(profile_id: str) -> tuple[str, str | None]:
    try:
        from qualix.core.profiles import get_profile

        return get_profile(profile_id).profile_id, None
    except Exception as exc:
        return profile_id, str(exc)


def _run_ingest(prd_path: str, project_id: str, output_dir: Path) -> int:
    from qualix.commands.ingest import run_ingest

    return run_ingest(prd_path, project_id, phase_id="Q01", output_root=output_dir)


def _capture_stdout(func, *args) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = func(*args)
    return rc, buffer.getvalue()


def _parse_json_stdout(stdout: str) -> dict[str, Any]:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


def _stdout_lines(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _build_phase_plan(project_id: str, code_repos: list[str]) -> list[dict[str, Any]]:
    code_arg = f" --code-repo {','.join(code_repos)}" if code_repos else ""
    plan = []
    for phase_id in CHECK_PHASES:
        phase_def = PHASE_DEFS.get(phase_id, {})
        needs_code = phase_id in {"Q05a", "Q06"} and bool(code_arg)
        execute = f"qualix-run {project_id} execute {phase_id} --json{code_arg if needs_code else ''}"
        finalize = f"qualix-run {project_id} finalize {phase_id} --json{code_arg if needs_code else ''}"
        plan.append(
            {
                "phase_id": phase_id,
                "name": phase_def.get("name", phase_id),
                "commands": {
                    "execute": execute,
                    "finalize": finalize,
                    "approve": f"qualix-run {project_id} approve {phase_id} --json",
                },
            }
        )
    return plan


def _print_human_check(project_id: str, payload: dict[str, Any]) -> None:
    bar = "=" * 64
    print(f"\n{bar}")
    print(f"  Qualix check — {project_id}")
    print(bar)
    print(f"\nWorkspace: {payload['workspace']['root']}")
    print(f"Project output: {payload['project']['output_dir']}")
    print(f"PRD ingested: {payload['prd']['plain_text_path']}")
    if payload["code_repos"]:
        print("Code repos:")
        for repo in payload["code_repos"]:
            print(f"  - {repo}")

    print("\nRun these phases in order:")
    for index, phase in enumerate(payload["phase_plan"], 1):
        print(f"  {index}. {phase['phase_id']} — {phase['name']}")
        print(f"     {phase['commands']['execute']}")
        print(f"     {phase['commands']['finalize']}")
        print(f"     {phase['commands']['approve']}")
    print("\nAfter Q06, inspect a finding's evidence chain:")
    print(f"  qualix-run {project_id} explain SE-003 --json")
    print(f"{bar}\n")
