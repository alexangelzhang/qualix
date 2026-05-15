"""Doctor 环境检查：收集结果 + 人类可读输出（供 setup.cmd_doctor 使用）."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REQUIRED_PACKAGES = ["pydantic", "jinja2"]
_OPTIONAL_PACKAGES = ["deepeval", "tree_sitter"]
_REQUIRED_SCRIPTS = [
    "scripts/feishu_direct_ingest.py",
    "scripts/parse_image_assets.py",
]


def run_doctor_checks(base_dir: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    """收集 doctor 结果（无 stdout 副作用）。"""
    issues: list[str] = []
    warnings: list[str] = []
    signals: dict[str, Any] = {}

    v = sys.version_info
    py_ver = f"{v.major}.{v.minor}.{v.micro}"
    signals["python_version"] = py_ver
    if v.minor >= 11:
        signals["python_ok"] = True
    else:
        signals["python_ok"] = False
        issues.append(f"Python {py_ver} < 3.11")

    for pkg in _REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            signals[f"pkg_{pkg}"] = True
        except ImportError:
            signals[f"pkg_{pkg}"] = False
            issues.append(f"缺少依赖: {pkg}")

    for pkg in _OPTIONAL_PACKAGES:
        try:
            __import__(pkg)
            signals[f"pkg_optional_{pkg}"] = True
        except ImportError:
            signals[f"pkg_optional_{pkg}"] = False
            warnings.append(f"可选依赖未安装: {pkg}")

    for script in _REQUIRED_SCRIPTS:
        script_path = base_dir / script
        exists = script_path.exists()
        signals[f"script_{script}"] = exists
        if not exists:
            warnings.append(f"脚本不存在: {script}")

    profiles_dir = base_dir / "profiles"
    if profiles_dir.exists():
        profiles = [d.name for d in profiles_dir.iterdir() if d.is_dir()]
        signals["profiles_dir"] = profiles
        from dqg.core.profiles import validate_all_profiles

        profile_issues = validate_all_profiles(profiles_root=profiles_dir, repo_root=base_dir)
        signals["profile_issues"] = profile_issues
        if profile_issues:
            for profile_id, profile_errors in profile_issues.items():
                for err in profile_errors:
                    issues.append(f"profile {profile_id}: {err}")
    else:
        signals["profiles_dir"] = None
        issues.append("profiles/ 目录不存在")

    skills_dir = base_dir / "skills"
    if skills_dir.exists():
        skill_count = sum(1 for _ in skills_dir.rglob("SKILL.md"))
        signals["skills_skill_md_count"] = skill_count
    else:
        signals["skills_skill_md_count"] = 0
        issues.append("skills/ 目录不存在")

    try:
        result = subprocess.run(
            ["uvx", "larkkit", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        signals["larkkit_auth_ok"] = result.returncode == 0
        if result.returncode != 0:
            warnings.append("飞书 token 无效或未配置")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        signals["larkkit_auth_ok"] = False
        warnings.append("larkkit 未安装或超时")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=base_dir,
        )
        signals["git_repo"] = result.returncode == 0
        if result.returncode != 0:
            warnings.append("当前目录不是 git 仓库")
    except FileNotFoundError:
        signals["git_repo"] = False
        issues.append("git 未安装")

    vlm_keys = {
        "ANTHROPIC_API_KEY": "Anthropic Claude",
        "OPENAI_API_KEY": "OpenAI GPT-4V",
        "DASHSCOPE_API_KEY": "DashScope 通义千问",
    }
    vlm_found: list[str] = []
    for env_var, name in vlm_keys.items():
        if os.getenv(env_var):
            vlm_found.append(name)
    signals["vlm_configured"] = vlm_found

    ab_path = shutil.which("agent-browser")
    signals["agent_browser_path"] = ab_path
    if ab_path:
        try:
            ver = subprocess.run([ab_path, "--version"], capture_output=True, text=True, timeout=5)
            signals["agent_browser_version"] = ver.stdout.strip() or "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            signals["agent_browser_version"] = str(ab_path)

    return issues, warnings, signals


def print_doctor_human(base_dir: Path, issues: list[str], warnings: list[str], signals: dict[str, Any]) -> None:
    """人类可读的 doctor 输出（与旧版文案对齐）。"""
    print()
    print("=" * 50)
    print("  DQG Doctor — 环境健康检查")
    print("=" * 50)

    py_ver = signals["python_version"]
    if signals.get("python_ok"):
        print(f"  ✓ Python {py_ver}")
    else:
        print(f"  ✗ Python {py_ver} (需要 >= 3.11)")

    for pkg in _REQUIRED_PACKAGES:
        if signals.get(f"pkg_{pkg}"):
            print(f"  ✓ {pkg}")
        else:
            print(f"  ✗ {pkg} (pip install {pkg})")

    for pkg in _OPTIONAL_PACKAGES:
        if signals.get(f"pkg_optional_{pkg}"):
            print(f"  ✓ {pkg} (可选)")
        else:
            print(f"  ⚠ {pkg} 未安装 (可选，pip install {pkg})")

    for script in _REQUIRED_SCRIPTS:
        if signals.get(f"script_{script}"):
            print(f"  ✓ {script}")
        else:
            print(f"  ⚠ {script} 不存在")

    pd = signals.get("profiles_dir")
    if pd is not None:
        print(f"  ✓ profiles/ ({', '.join(pd)})")
        if signals.get("profile_issues"):
            pi = signals["profile_issues"]
            print(f"  ✗ profile schema ({sum(len(v) for v in pi.values())} issues)")
        else:
            print("  ✓ profile schema")
    else:
        print("  ✗ profiles/ 目录不存在")

    sc = signals.get("skills_skill_md_count", 0)
    if sc > 0:
        print(f"  ✓ skills/ ({sc} SKILL.md)")
    else:
        print("  ✗ skills/ 目录不存在")

    if signals.get("larkkit_auth_ok"):
        print("  ✓ 飞书 token 有效")
    else:
        print("  ⚠ 飞书 token 无效 (uvx larkkit auth login)")

    if not shutil.which("git"):
        print("  ✗ git 未安装")
    elif signals.get("git_repo"):
        print("  ✓ git 仓库")
    else:
        print("  ⚠ 当前目录不是 git 仓库")

    vlm_keys = {
        "ANTHROPIC_API_KEY": "Anthropic Claude",
        "OPENAI_API_KEY": "OpenAI GPT-4V",
        "DASHSCOPE_API_KEY": "DashScope 通义千问",
    }
    vlm_found = False
    for env_var, name in vlm_keys.items():
        if os.getenv(env_var):
            print(f"  ✓ {name} ({env_var})")
            vlm_found = True
    if not vlm_found:
        print("  - VLM API Key 未配置 (可选，用于图片深度解析)")

    ab_path = signals.get("agent_browser_path")
    if ab_path:
        print(f"  ✓ agent-browser ({signals.get('agent_browser_version', '')})")
    else:
        print("  - agent-browser 未安装 (可选，npm install -g agent-browser && agent-browser install)")

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
