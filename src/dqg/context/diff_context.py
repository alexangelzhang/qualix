"""增量分析模块：基于 git diff 收集变更范围.

在 Phase C/D 执行时，自动收集变更文件列表和 diff 内容，
注入到 skill prompt 中，避免全量扫描。

用法:
    # 在 runner 中
    diff = collect_diff_context(repo_path, base_branch, feature_branch)
    # diff.changed_files, diff.diff_text, diff.summary
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _is_remote_url(path: str) -> bool:
    """判断是否是远程 Git URL."""
    s = str(path).strip()
    return (
        s.startswith("git@")
        or s.startswith("https://")
        or s.startswith("http://")
        or s.startswith("ssh://")
        or s.endswith(".git")
    )


def _cleanup(tmp_dir: Path | None) -> None:
    """清理临时目录."""
    if tmp_dir and tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)


@dataclass
class DiffContext:
    """Git diff 变更上下文."""

    repo_path: str = ""
    base_branch: str = "master"
    feature_branch: str = "HEAD"
    changed_files: list[str] = field(default_factory=list)
    added_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    diff_stat: str = ""
    diff_text: str = ""
    total_additions: int = 0
    total_deletions: int = 0
    error: str = ""

    @property
    def has_changes(self) -> bool:
        return len(self.changed_files) > 0

    @property
    def summary(self) -> str:
        if self.error:
            return f"diff 收集失败: {self.error}"
        if not self.has_changes:
            return "无变更文件"
        return (
            f"{len(self.changed_files)} 个文件变更 "
            f"(+{len(self.added_files)} 新增, "
            f"~{len(self.modified_files)} 修改, "
            f"-{len(self.deleted_files)} 删除), "
            f"+{self.total_additions}/-{self.total_deletions} 行"
        )

    def java_files(self) -> list[str]:
        """只返回 Java 文件."""
        return [f for f in self.changed_files if f.endswith(".java")]

    def test_files(self) -> list[str]:
        """只返回测试文件."""
        return [f for f in self.changed_files if "test" in f.lower() or "Test" in f]

    def source_files(self) -> list[str]:
        """只返回非测试的源文件."""
        test_set = set(self.test_files())
        return [f for f in self.changed_files if f not in test_set]


def _run_git(repo_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """执行 git 命令."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return False, str(e)


def collect_diff_context(
    repo_path: str | Path,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
    max_diff_lines: int = 5000,
) -> DiffContext:
    """收集 git diff 变更上下文.

    Args:
        repo_path: 代码仓库路径（本地路径或远程 Git URL）
        base_branch: 基线分支（默认 master）
        feature_branch: 特性分支（默认 HEAD）
        max_diff_lines: diff 文本最大行数（防止过大）

    Returns:
        DiffContext 包含变更文件列表和 diff 内容
    """
    path_str = str(repo_path).strip()
    cleanup_dir: Path | None = None

    # 远程 URL: clone 到临时目录
    if _is_remote_url(path_str):
        tmp = Path(tempfile.mkdtemp(prefix="dqg_diff_"))
        cleanup_dir = tmp
        ok, out = _run_git(
            tmp.parent,
            ["clone", "--no-checkout", "--filter=blob:none", path_str, str(tmp)],
            timeout=120,
        )
        if not ok:
            ctx = DiffContext(repo_path=path_str, base_branch=base_branch, feature_branch=feature_branch)
            ctx.error = f"clone 失败: {out[:200]}"
            return ctx
        # fetch both branches
        _run_git(tmp, ["fetch", "origin", base_branch, feature_branch], timeout=60)
        repo = tmp
        # 远程分支需要加 origin/ 前缀
        if not base_branch.startswith("origin/"):
            base_branch = f"origin/{base_branch}"
        if feature_branch != "HEAD" and not feature_branch.startswith("origin/"):
            feature_branch = f"origin/{feature_branch}"
    else:
        repo = Path(path_str).resolve()

    ctx = DiffContext(
        repo_path=path_str,
        base_branch=base_branch,
        feature_branch=feature_branch,
    )

    if not repo.exists():
        ctx.error = f"路径不存在: {repo}"
        _cleanup(cleanup_dir)
        return ctx

    # 检查是否在 git 仓库中
    ok, _ = _run_git(repo, ["rev-parse", "--git-dir"])
    if not ok:
        ctx.error = f"不是 git 仓库: {repo}"
        _cleanup(cleanup_dir)
        return ctx

    # 获取 merge-base
    ok, merge_base = _run_git(repo, ["merge-base", base_branch, feature_branch])
    if not ok:
        # fallback: 直接用 base_branch
        merge_base = base_branch
    else:
        merge_base = merge_base.strip()

    # 并行执行三个独立的 git 命令
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_name_status = pool.submit(
            _run_git,
            repo,
            ["diff", "--name-status", merge_base, feature_branch],
        )
        fut_stat = pool.submit(
            _run_git,
            repo,
            ["diff", "--stat", merge_base, feature_branch],
        )
        fut_diff = pool.submit(
            _run_git,
            repo,
            ["diff", merge_base, feature_branch],
            60,
        )

        ok, name_status = fut_name_status.result()
        if not ok:
            ctx.error = f"git diff 失败: {name_status[:200]}"
            return ctx

        _parse_name_status(ctx, name_status)
        _parse_diff_stat(ctx, fut_stat.result())
        _parse_diff_text(ctx, fut_diff.result(), max_diff_lines)

    _cleanup(cleanup_dir)
    return ctx


def _parse_name_status(ctx: DiffContext, name_status: str) -> None:
    for line in name_status.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status, filepath = parts[0].strip(), parts[1].strip()
        ctx.changed_files.append(filepath)
        if status.startswith("A"):
            ctx.added_files.append(filepath)
        elif status.startswith("M"):
            ctx.modified_files.append(filepath)
        elif status.startswith("D"):
            ctx.deleted_files.append(filepath)


def _parse_diff_stat(ctx: DiffContext, result: tuple[bool, str]) -> None:
    ok, stat = result
    if not ok:
        return
    ctx.diff_stat = stat.strip()
    for line in stat.strip().split("\n"):
        if "insertion" in line or "deletion" in line:
            adds = re.search(r"(\d+) insertion", line)
            dels = re.search(r"(\d+) deletion", line)
            if adds:
                ctx.total_additions = int(adds.group(1))
            if dels:
                ctx.total_deletions = int(dels.group(1))


def _parse_diff_text(ctx: DiffContext, result: tuple[bool, str], max_diff_lines: int) -> None:
    ok, diff = result
    if not ok:
        return
    lines = diff.split("\n")
    if len(lines) > max_diff_lines:
        ctx.diff_text = "\n".join(lines[:max_diff_lines]) + f"\n\n... (截断，共 {len(lines)} 行)"
    else:
        ctx.diff_text = diff


def render_diff_context_for_prompt(ctx: DiffContext) -> str:
    """将 diff context 渲染为 skill prompt 可用的 markdown."""
    if not ctx.has_changes:
        return ""

    lines = [
        "## DIFF_CONTEXT — 增量变更范围",
        "",
        f"基线: `{ctx.base_branch}` → 特性: `{ctx.feature_branch}`",
        f"变更: {ctx.summary}",
        "",
    ]

    # Java 文件分类
    java_src = [f for f in ctx.source_files() if f.endswith(".java")]
    java_test = [f for f in ctx.test_files() if f.endswith(".java")]

    if java_src:
        lines.append(f"### 变更源文件 ({len(java_src)} 个)")
        lines.append("")
        for f in java_src:
            status = "新增" if f in ctx.added_files else ("删除" if f in ctx.deleted_files else "修改")
            lines.append(f"- `{f}` [{status}]")
        lines.append("")

    if java_test:
        lines.append(f"### 变更测试文件 ({len(java_test)} 个)")
        lines.append("")
        for f in java_test:
            status = "新增" if f in ctx.added_files else ("删除" if f in ctx.deleted_files else "修改")
            lines.append(f"- `{f}` [{status}]")
        lines.append("")

    # 非 Java 文件
    other = [f for f in ctx.changed_files if not f.endswith(".java")]
    if other:
        lines.append(f"### 其他变更文件 ({len(other)} 个)")
        lines.append("")
        for f in other[:20]:
            lines.append(f"- `{f}`")
        if len(other) > 20:
            lines.append(f"- ... 共 {len(other)} 个")
        lines.append("")

    lines.extend(
        [
            "### 审计范围说明",
            "",
            "本次为增量分析模式，只需审计上述变更文件涉及的功能点。",
            "对于未变更的文件，沿用上次审计结论。",
        ]
    )

    return "\n".join(lines)


def write_diff_context(
    output_dir: Path,
    project_id: str,
    phase_dir_name: str,
    ctx: DiffContext,
) -> Path | None:
    """将 diff context 写入 phase 目录."""
    if not ctx.has_changes:
        return None

    md = render_diff_context_for_prompt(ctx)
    if not md:
        return None

    pd = output_dir / project_id / phase_dir_name
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_diff_context.md"
    path.write_text(md, encoding="utf-8")
    return path
