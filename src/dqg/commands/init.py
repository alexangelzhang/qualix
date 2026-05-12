"""dqg-run init — workspace-level 初始化命令.

在用户项目目录创建 .dqg/ 工作区：
- .dqg/output/        运行时输出
- .dqg/settings.yaml  版本 pin + profile + code_repos
- CLAUDE.md           guardrail 章节（marker 包裹, 幂等替换）
- .gitignore          追加 .dqg/output/
"""

from __future__ import annotations

import shutil
from pathlib import Path

GUARDRAIL_BEGIN = "<!-- DQG-GUARDRAIL-BEGIN -->"
GUARDRAIL_END = "<!-- DQG-GUARDRAIL-END -->"

_GUARDRAIL_BODY = """\
## DQG 使用规约

DQG 是通过 install.sh 安装的工具，**不要修改它的源码**。

遇到 DQG 报错时：
1. 跑 `dqg-run doctor` 生成 issue bundle
2. 把 bundle 提交给 DQG 维护者

相关资源：
- `dqg-run --help` — CLI 完整参数
- `dqg-run path <skills|references|profiles>` — 查看内置资源"""


def _get_dqg_version() -> str:
    """获取已安装的 DQG 版本号."""
    try:
        from importlib.metadata import version as _version

        return _version("dev-quality-gate")
    except Exception:
        pass
    # fallback: 从 setup.py 常量读
    try:
        from dqg.commands.setup import DQG_VERSION

        return DQG_VERSION
    except Exception:
        return "unknown"


def _install_claude_commands(project_root: Path) -> list[str]:
    """把 DQG 内置 claude_commands 复制到 project_root/.claude/commands/，返回已安装文件名列表."""
    from dqg.core.resource_resolver import ResourceResolver

    try:
        src_dir = ResourceResolver().resolve_dir("claude_commands")
    except FileNotFoundError:
        return []

    dest_dir = project_root / ".claude" / "commands"
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for f in src_dir.iterdir():
        if f.suffix == ".md":
            shutil.copy2(f, dest_dir / f.name)
            installed.append(f.name)
    return installed


def _detect_code_repos(project_root: Path) -> list[str]:
    """扫描 project_root 直接子目录，返回包含 .git/ 的目录绝对路径列表."""
    repos = []
    for child in sorted(project_root.iterdir()):
        if child.is_dir() and (child / ".git").exists():
            repos.append(str(child))
    return repos


def _detect_profile(project_root: Path, code_repos: list[str]) -> str:
    """从 project_root 和子仓库特征文件推断 profile，推断不出则返回 None."""
    candidates = [project_root] + [Path(r) for r in code_repos]
    for root in candidates:
        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            return "java-ddd-tmf"
        if (root / "go.mod").exists():
            return "go-service"
        if (root / "tsconfig.json").exists():
            return "ts-service"
        if (root / "package.json").exists():
            return "ts-service"
    return None


def _settings_yaml(profile: str, dqg_version: str, code_repos: list[str] | None = None) -> str:
    if code_repos:
        repos_lines = "\n".join(f"  - {r}" for r in code_repos)
        repos_block = f"code_repos:\n{repos_lines}\n"
    else:
        repos_block = "code_repos: []   # 填写代码仓绝对路径\n"
    return (
        "# DQG 项目配置 — 由 dqg-run init 生成\n"
        f'dqg_version: "{dqg_version}"   # 自动写入，勿手改\n'
        f"profile: {profile}\n"
        f"{repos_block}"
    )


def _inject_guardrail(claude_md: Path) -> None:
    """注入或替换 CLAUDE.md 中的 guardrail marker 块."""
    marker_block = f"{GUARDRAIL_BEGIN}\n{_GUARDRAIL_BODY}\n{GUARDRAIL_END}\n"
    if not claude_md.exists():
        claude_md.write_text(marker_block)
        return
    content = claude_md.read_text()
    if GUARDRAIL_BEGIN in content and GUARDRAIL_END in content:
        # 替换已有 block（幂等）
        before, _, rest = content.partition(GUARDRAIL_BEGIN)
        _, _, after = rest.partition(GUARDRAIL_END)
        # 保留 before 末尾换行 + marker block + after 开头内容
        before_stripped = before.rstrip("\n")
        after_stripped = after.lstrip("\n")
        parts = [before_stripped, "\n\n", marker_block]
        if after_stripped:
            parts.append("\n")
            parts.append(after_stripped)
        claude_md.write_text("".join(parts))
    else:
        # 追加到末尾
        sep = "" if content.endswith("\n") else "\n"
        claude_md.write_text(content + sep + "\n" + marker_block)


def _append_gitignore(gitignore: Path, entry: str) -> None:
    """追加 entry 到 .gitignore（幂等）."""
    if not gitignore.exists():
        gitignore.write_text(entry + "\n")
        return
    content = gitignore.read_text()
    if entry in content.splitlines():
        return
    sep = "" if content.endswith("\n") else "\n"
    gitignore.write_text(content + sep + entry + "\n")


def run_init(project_root: Path, profile: str | None, force: bool) -> int:
    """执行 workspace 初始化，返回 exit code."""
    dqg_root = project_root / ".dqg"

    if dqg_root.exists() and not force:
        print(f"错误: {dqg_root} 已存在。使用 --force 覆盖（只重置配置文件，output/ 产物不受影响）")
        return 1

    if dqg_root.exists() and force:
        # 只删配置文件，保留 output/（项目产物）
        for name in ("settings.yaml", "last-run.json"):
            f = dqg_root / name
            if f.exists():
                f.unlink()

    # 创建 .dqg/output/（幂等）
    (dqg_root / "output").mkdir(parents=True, exist_ok=True)

    # 自动扫描子目录 git 仓库
    dqg_version = _get_dqg_version()
    code_repos = _detect_code_repos(project_root)

    # 自动推断 profile
    detected_profile = _detect_profile(project_root, code_repos)
    if profile is None:
        profile = detected_profile or "java-ddd-tmf"
        auto_detected = detected_profile is not None
    else:
        auto_detected = False

    (dqg_root / "settings.yaml").write_text(_settings_yaml(profile, dqg_version, code_repos))

    # 注入 CLAUDE.md guardrail
    _inject_guardrail(project_root / "CLAUDE.md")

    # 追加 .gitignore
    _append_gitignore(project_root / ".gitignore", ".dqg/output/")

    # 安装 Claude Code slash commands
    installed_commands = _install_claude_commands(project_root)

    print("✓ .dqg/ 工作区已创建")
    print("✓ CLAUDE.md guardrail 已注入")
    print("✓ .gitignore 已追加 .dqg/output/")
    if auto_detected:
        print(f"✓ 自动识别技术栈: {profile}")
    else:
        print(f"✓ profile: {profile}")
    if code_repos:
        print(f"✓ 自动检测到 {len(code_repos)} 个代码仓库，已写入 code_repos：")
        for r in code_repos:
            print(f"    - {r}")
    else:
        print("  未检测到子目录 git 仓库，请手动编辑 .dqg/settings.yaml 填写 code_repos")
    if installed_commands:
        print(f"✓ Claude Code slash commands 已安装: {', '.join(installed_commands)}")
    print("\n下一步：")
    if not code_repos:
        print("  1. 编辑 .dqg/settings.yaml 填写 code_repos")
        print("  2. 运行 dqg-run <project_id> startup 开始")
    else:
        print("  1. 确认 .dqg/settings.yaml 中的 profile 和 code_repos 是否正确")
        print("  2. 运行 dqg-run <project_id> startup 开始")
    return 0
