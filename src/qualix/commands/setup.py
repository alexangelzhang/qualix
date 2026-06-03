"""设置命令：init / doctor / update / version."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.core.phase_registry import PHASE_DEFS, PHASE_ORDER
from qualix.core.state_machine import ProjectState, load_state, save_state
from qualix.json_utils import load_json_strict, save_json

# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

QUALIX_VERSION = "0.2.0"


def cmd_version(args, output_dir: Path) -> int:
    """显示 Qualix 版本."""
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="version",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"qualix_version": QUALIX_VERSION},
            )
        )
    else:
        print(f"Qualix v{QUALIX_VERSION}")
    return 0


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args, output_dir: Path) -> int:
    """一键初始化项目：创建目录结构、state.json、version.json."""
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

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
            print(f"  state.json 已存在，跳过（使用 qualix-run {project_id} status 查看状态）")
        state = load_state(output_dir, project_id)
    else:
        from qualix.core.profiles import get_profile

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
            "qualix_version": QUALIX_VERSION,
            "initialized_at": datetime.now().isoformat(),
            "profile_id": profile_id,
        },
    )
    if not cli_json_mode(args):
        print(f"  ✓ version.json 已创建 (v{QUALIX_VERSION})")

    # L2: 创建用户工作区 .qualix/
    project_root = output_dir.parent
    qualix_dir = project_root / ".qualix"
    workspace_created = False
    if not qualix_dir.exists():
        (qualix_dir / "profiles").mkdir(parents=True, exist_ok=True)
        (qualix_dir / "skill-overrides").mkdir(exist_ok=True)
        settings_path = qualix_dir / "settings.yaml"
        settings_path.write_text(
            "# Qualix user workspace settings\n"
            "# Docs: https://github.com/alexangelzhang/qualix/blob/main/docs/custom-profile.md\n"
            "\n"
            "# profile: java-ddd-tmf   # override default profile\n"
            "# skill_overrides: true   # enable skill-overrides/ directory\n",
            encoding="utf-8",
        )
        workspace_created = True

    # L3: 在用户 CLAUDE.md 末尾追加 guardrail（幂等）
    guardrail_added = False
    _GUARDRAIL_MARKER = "## Qualix Usage"
    claude_md_path = project_root / "CLAUDE.md"
    if claude_md_path.exists():
        existing = claude_md_path.read_text(encoding="utf-8")
        if _GUARDRAIL_MARKER not in existing:
            guardrail_text = (
                "\n\n## Qualix Usage\n\n"
                "Qualix is installed as a tool (`pip install qualix`). Do not modify its source code.\n\n"
                "If Qualix reports an error:\n"
                "1. Run `qualix-run doctor` to generate a diagnostic bundle\n"
                "2. Report the bundle at https://github.com/alexangelzhang/qualix/issues"
                " — do not patch the tool directly\n"
                "3. To customize behavior, edit `.qualix/` (profiles, skill overrides, settings)\n"
            )
            with claude_md_path.open("a", encoding="utf-8") as f:
                f.write(guardrail_text)
            guardrail_added = True

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
                    "workspace_created": workspace_created,
                    "guardrail_added": guardrail_added,
                },
            )
        )
    else:
        print(f"\n  项目 {project_id} 初始化完成:")
        print(f"    Profile: {profile_id}")
        print(f"    输出目录: {project_dir}")
        print(f"    Phase 目录: {', '.join(phase_dirs)}")
        if workspace_created:
            print(f"  ✓ .qualix/ workspace created")
            print(f"    .qualix/profiles/        — custom profile overrides")
            print(f"    .qualix/skill-overrides/ — skill customizations")
            print(f"    .qualix/settings.yaml    — user preferences")
        if guardrail_added:
            print(f"  ✓ CLAUDE.md guardrail added")
        print(f"\n  下一步: qualix-run {project_id} startup")
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args, output_dir: Path) -> int:
    """环境健康检查."""
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.commands.doctor_checks import print_doctor_human, run_doctor_checks

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
    """更新 Qualix 到最新版本."""
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

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
        old_ver = ver_data.get("qualix_version", "unknown")
        version_bump["old_qualix_version"] = old_ver
        if old_ver != QUALIX_VERSION:
            version_bump["updated"] = True
            version_bump["new_qualix_version"] = QUALIX_VERSION
            ver_data["qualix_version"] = QUALIX_VERSION
            ver_data["updated_at"] = datetime.now().isoformat()
            save_json(version_path, ver_data)
            if not cli_json_mode(args):
                print(f"  版本变更: {old_ver} → {QUALIX_VERSION}")
                print("  ✓ version.json 已更新")
        else:
            version_bump["updated"] = False
            if not cli_json_mode(args):
                print(f"  ✓ 已是最新版本 (v{QUALIX_VERSION})")
    else:
        version_bump["hint"] = f"qualix-run {project_id} init"
        if not cli_json_mode(args):
            print(f"  ⚠ version.json 不存在，建议执行 qualix-run {project_id} init")

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="update",
                project_id=project_id,
                success=True,
                exit_code=0,
                extra={"git_pull_stdout": pull_out, "version": version_bump, "qualix_version": QUALIX_VERSION},
            )
        )


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------


def cmd_demo(args, output_dir: Path) -> int:  # noqa: ARG001
    """Show a demo of Qualix output without requiring an API key."""
    from qualix.core.resource_resolver import ResourceResolver

    resolver = ResourceResolver()

    def _read(relative: str) -> str:
        try:
            path = resolver.resolve("examples", f"expense-approval/{relative}")
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"[demo file not found: examples/expense-approval/{relative}]"

    bar = "=" * 60
    print(f"\n{bar}")
    print("  Qualix Demo — Expense Approval")
    print("  No API key required. These are pre-computed expected outputs.")
    print(bar)

    print("\n── Q01: Requirements Structuring ──────────────────────────\n")
    print(_read("expected/q01-summary.md"))

    print(f"\n{bar}")
    print("\n── Q05a: EUT Matrix Design ─────────────────────────────────\n")
    print(_read("expected/q05a-eut-matrix.md"))

    print(f"\n{bar}")
    print("\n── Q06: Unit Test Coverage Audit ──────────────────────────\n")
    print(_read("expected/q06-audit.md"))

    print(f"\n{bar}")
    print("\nKey finding: both tests pass and branch coverage is green.")
    print("The implementation uses '> 500' instead of '>= 500'.")
    print("The boundary at exactly 500 USD — which the PRD explicitly defines —")
    print("is never tested. Q06 flags it as MISSING regardless of coverage numbers.")
    print(f"\n{bar}")
    print("\nTo run on your own PRD (requires an API key):")
    print("  export ANTHROPIC_API_KEY=...")
    print("  qualix-run --profile python-service <project> init")
    print("  qualix-run ingest <prd.md> --project <project>")
    print("  qualix-run <project> startup --json")
    print("\nTo drill into a specific SE finding after running the pipeline:")
    print("  qualix-run <project> explain SE-003")
    print(f"{bar}\n")
    return 0
