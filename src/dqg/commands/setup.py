"""设置命令：init / doctor / update / version."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.core.phase_registry import PHASE_DEFS, PHASE_ORDER
from dqg.core.state_machine import ProjectState, load_state, save_state
from dqg.json_utils import load_json_strict, save_json

# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

DQG_VERSION = "0.2.0"


def cmd_version(args, output_dir: Path) -> int:
    """显示 DQG 版本."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="version",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"dqg_version": DQG_VERSION},
            )
        )
    else:
        print(f"DQG (Dev Quality Gate) v{DQG_VERSION}")
    return 0


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args, output_dir: Path) -> int:
    """一键初始化项目：创建目录结构、state.json、version.json."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    project_id = args.project_id
    requested_profile_id = getattr(args, "profile", None) or "java-ddd-tmf"

    project_dir = output_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # 创建各 Phase 输出目录
    for phase_id in PHASE_ORDER:
        phase_def = PHASE_DEFS[phase_id]
        phase_path = project_dir / phase_def["dir_suffix"]
        phase_path.mkdir(exist_ok=True)
        internal = phase_path / "_internal"
        internal.mkdir(exist_ok=True)

    # 初始化 state.json
    state_path = project_dir / "state.json"
    had_state_before = state_path.exists()
    state_json_created = False
    if had_state_before:
        if not cli_json_mode(args):
            print(f"  state.json 已存在，跳过（使用 dqg-run {project_id} status 查看状态）")
        state = load_state(output_dir, project_id)
    else:
        from dqg.core.profiles import get_profile

        profile = get_profile(requested_profile_id)
        profile_id = profile.profile_id
        state = ProjectState(project_id=project_id, profile_id=profile_id)
        save_state(output_dir, state)
        state_json_created = True
        if not cli_json_mode(args):
            print("  ✓ state.json 已创建")

    profile_id = state.profile_id

    # 写入 version.json
    version_path = project_dir / "version.json"
    save_json(
        version_path,
        {
            "dqg_version": DQG_VERSION,
            "initialized_at": datetime.now().isoformat(),
            "profile_id": profile_id,
        },
    )
    if not cli_json_mode(args):
        print(f"  ✓ version.json 已创建 (v{DQG_VERSION})")

    # 汇总
    phase_dirs = [PHASE_DEFS[pid]["dir_suffix"] for pid in PHASE_ORDER]
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="init",
                project_id=project_id,
                success=True,
                exit_code=0,
                extra={
                    "profile_id": profile_id,
                    "project_dir": str(project_dir),
                    "phase_dirs": phase_dirs,
                    "state_json_created": state_json_created,
                    "state_existed_before": had_state_before,
                    "version_path": str(version_path),
                },
            )
        )
    else:
        print(f"\n  项目 {project_id} 初始化完成:")
        print(f"    Profile: {profile_id}")
        print(f"    输出目录: {project_dir}")
        print(f"    Phase 目录: {', '.join(phase_dirs)}")
        print(f"\n  下一步: dqg-run {project_id} startup")
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args, output_dir: Path) -> int:
    """环境健康检查."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.commands.doctor_checks import print_doctor_human, run_doctor_checks

    base_dir = output_dir.parent
    issues, warnings, signals = run_doctor_checks(base_dir)
    if cli_json_mode(args):
        ec = 1 if issues else 0
        print_cli_json(
            cli_envelope(
                command="doctor",
                project_id=args.project_id,
                success=ec == 0,
                exit_code=ec,
                extra={"issues": issues, "warnings": warnings, "signals": signals},
            )
        )
        return ec
    print_doctor_human(base_dir, issues, warnings, signals)
    return 1 if issues else 0


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def cmd_update(args, output_dir: Path) -> int:
    """更新 DQG 到最新版本."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    base_dir = output_dir.parent

    # git pull
    if not cli_json_mode(args):
        print("  拉取最新代码...")
    result = subprocess.run(
        ["git", "pull", "--rebase"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=base_dir,
    )
    if result.returncode != 0:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="update",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    extra={"error": "git_pull_failed", "stderr": (result.stderr or "").strip()},
                )
            )
        else:
            print(f"  ✗ git pull 失败: {result.stderr.strip()}", file=sys.stderr)
        return 1
    pull_out = (result.stdout or "").strip()
    if not cli_json_mode(args):
        print(f"  ✓ {pull_out}")

    # 检查项目 version.json 是否需要更新
    project_id = args.project_id
    version_path = output_dir / project_id / "version.json"
    version_bump: dict[str, Any] = {"version_path_exists": version_path.exists()}
    if version_path.exists():
        ver_data = load_json_strict(version_path)
        old_ver = ver_data.get("dqg_version", "unknown")
        version_bump["old_dqg_version"] = old_ver
        if old_ver != DQG_VERSION:
            version_bump["updated"] = True
            version_bump["new_dqg_version"] = DQG_VERSION
            ver_data["dqg_version"] = DQG_VERSION
            ver_data["updated_at"] = datetime.now().isoformat()
            save_json(version_path, ver_data)
            if not cli_json_mode(args):
                print(f"  版本变更: {old_ver} → {DQG_VERSION}")
                print("  ✓ version.json 已更新")
        else:
            version_bump["updated"] = False
            if not cli_json_mode(args):
                print(f"  ✓ 已是最新版本 (v{DQG_VERSION})")
    else:
        version_bump["hint"] = f"dqg-run {project_id} init"
        if not cli_json_mode(args):
            print(f"  ⚠ version.json 不存在，建议执行 dqg-run {project_id} init")

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="update",
                project_id=project_id,
                success=True,
                exit_code=0,
                extra={"git_pull_stdout": pull_out, "version": version_bump, "dqg_version": DQG_VERSION},
            )
        )
    return 0
