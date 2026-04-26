"""设置命令：init / doctor / update / version."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from dqg.core.phase_registry import PHASE_DEFS, PHASE_ORDER
from dqg.core.state_machine import ProjectState, load_state, save_state
from dqg.json_utils import load_json_strict, save_json

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

DQG_VERSION = "0.2.0"


def cmd_version(args, output_dir: Path) -> int:
    """显示 DQG 版本."""
    print(f"DQG (Dev Quality Gate) v{DQG_VERSION}")
    return 0


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args, output_dir: Path) -> int:
    """一键初始化项目：创建目录结构、state.json、version.json."""
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
    if state_path.exists():
        print(f"  state.json 已存在，跳过（使用 dqg-run {project_id} status 查看状态）")
        state = load_state(output_dir, project_id)
    else:
        from dqg.core.profiles import get_profile

        profile = get_profile(requested_profile_id)
        profile_id = profile.profile_id
        state = ProjectState(project_id=project_id, profile_id=profile_id)
        save_state(output_dir, state)
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
    print(f"  ✓ version.json 已创建 (v{DQG_VERSION})")

    # 汇总
    phase_dirs = [PHASE_DEFS[pid]["dir_suffix"] for pid in PHASE_ORDER]
    print(f"\n  项目 {project_id} 初始化完成:")
    print(f"    Profile: {profile_id}")
    print(f"    输出目录: {project_dir}")
    print(f"    Phase 目录: {', '.join(phase_dirs)}")
    print(f"\n  下一步: dqg-run {project_id} startup")
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

_REQUIRED_PACKAGES = ["pydantic", "jinja2"]
_OPTIONAL_PACKAGES = ["deepeval", "tree_sitter"]
_REQUIRED_SCRIPTS = [
    "scripts/feishu_direct_ingest.py",
    "scripts/parse_image_assets.py",
]


def cmd_doctor(args, output_dir: Path) -> int:
    """环境健康检查."""
    base_dir = output_dir.parent
    issues: list[str] = []
    warnings: list[str] = []

    print()
    print("=" * 50)
    print("  DQG Doctor — 环境健康检查")
    print("=" * 50)

    # 1. Python 版本
    v = sys.version_info
    py_ver = f"{v.major}.{v.minor}.{v.micro}"
    if v.minor >= 11:
        print(f"  ✓ Python {py_ver}")
    else:
        issues.append(f"Python {py_ver} < 3.11")
        print(f"  ✗ Python {py_ver} (需要 >= 3.11)")

    # 2. 必需依赖
    for pkg in _REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg}")
        except ImportError:
            issues.append(f"缺少依赖: {pkg}")
            print(f"  ✗ {pkg} (pip install {pkg})")

    # 3. 可选依赖
    for pkg in _OPTIONAL_PACKAGES:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg} (可选)")
        except ImportError:
            warnings.append(f"可选依赖未安装: {pkg}")
            print(f"  ⚠ {pkg} 未安装 (可选，pip install {pkg})")

    # 4. 关键脚本
    for script in _REQUIRED_SCRIPTS:
        script_path = base_dir / script
        if script_path.exists():
            print(f"  ✓ {script}")
        else:
            warnings.append(f"脚本不存在: {script}")
            print(f"  ⚠ {script} 不存在")

    # 5. profiles 目录 + schema 校验
    profiles_dir = base_dir / "profiles"
    if profiles_dir.exists():
        profiles = [d.name for d in profiles_dir.iterdir() if d.is_dir()]
        print(f"  ✓ profiles/ ({', '.join(profiles)})")
        from dqg.core.profiles import validate_all_profiles

        profile_issues = validate_all_profiles(profiles_root=profiles_dir, repo_root=base_dir)
        if profile_issues:
            for profile_id, profile_errors in profile_issues.items():
                for err in profile_errors:
                    issues.append(f"profile {profile_id}: {err}")
            print(f"  ✗ profile schema ({sum(len(v) for v in profile_issues.values())} issues)")
        else:
            print("  ✓ profile schema")
    else:
        issues.append("profiles/ 目录不存在")
        print("  ✗ profiles/ 目录不存在")

    # 6. skills 目录
    skills_dir = base_dir / "skills"
    if skills_dir.exists():
        skill_count = sum(1 for _ in skills_dir.rglob("SKILL.md"))
        print(f"  ✓ skills/ ({skill_count} SKILL.md)")
    else:
        issues.append("skills/ 目录不存在")
        print("  ✗ skills/ 目录不存在")

    # 7. 飞书 token
    try:
        result = subprocess.run(
            ["uvx", "larkkit", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("  ✓ 飞书 token 有效")
        else:
            warnings.append("飞书 token 无效或未配置")
            print("  ⚠ 飞书 token 无效 (uvx larkkit auth login)")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        warnings.append("larkkit 未安装或超时")
        print("  ⚠ larkkit 未安装 (pip install larkkit)")

    # 8. git
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=base_dir,
        )
        if result.returncode == 0:
            print("  ✓ git 仓库")
        else:
            warnings.append("当前目录不是 git 仓库")
            print("  ⚠ 当前目录不是 git 仓库")
    except FileNotFoundError:
        issues.append("git 未安装")
        print("  ✗ git 未安装")

    # 汇总
    print()
    print("-" * 50)
    if issues:
        print(f"  ✗ {len(issues)} 个问题需要修复:")
        for i in issues:
            print(f"    - {i}")
    if warnings:
        print(f"  ⚠ {len(warnings)} 个警告:")
        for w in warnings:
            print(f"    - {w}")
    if not issues and not warnings:
        print("  ✓ 环境健康，一切就绪")

    print()
    return 1 if issues else 0


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def cmd_update(args, output_dir: Path) -> int:
    """更新 DQG 到最新版本."""
    base_dir = output_dir.parent

    # git pull
    print("  拉取最新代码...")
    result = subprocess.run(
        ["git", "pull", "--rebase"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=base_dir,
    )
    if result.returncode != 0:
        print(f"  ✗ git pull 失败: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"  ✓ {result.stdout.strip()}")

    # 检查项目 version.json 是否需要更新
    project_id = args.project_id
    version_path = output_dir / project_id / "version.json"
    if version_path.exists():
        ver_data = load_json_strict(version_path)
        old_ver = ver_data.get("dqg_version", "unknown")
        if old_ver != DQG_VERSION:
            print(f"  版本变更: {old_ver} → {DQG_VERSION}")
            ver_data["dqg_version"] = DQG_VERSION
            ver_data["updated_at"] = datetime.now().isoformat()
            save_json(version_path, ver_data)
            print("  ✓ version.json 已更新")
        else:
            print(f"  ✓ 已是最新版本 (v{DQG_VERSION})")
    else:
        print(f"  ⚠ version.json 不存在，建议执行 dqg-run {project_id} init")

    return 0
