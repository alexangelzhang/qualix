"""Q05a 테스트 파일 수집 및 git diff 도우미."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from qualix.log import get_logger

log = get_logger(__name__)

# ────────────────────────────────────────────────────────────
_TYPO_METHOD_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\.getSucess\s*\(",
        r"\.getSccess\s*\(",
        r"\.isSucccess\s*\(",
        r"\.isSeccess\s*\(",
    )
)

# 可疑「幽灵方法」：when(mockX.foo()) 中 foo 过短或全大写缩写（启发式，低噪音）
_PHANTOM_METHOD = re.compile(
    r"\bwhen\s*\(\s*[^)]+\)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
)


_TEST_FILE_SUFFIXES = frozenset((".java", ".kt", ".ts", ".tsx"))


def _collect_new_test_files_from_repos(code_repos: list[str]) -> list[Path]:
    """从业务仓库收集新增/修改的测试文件.

    两路来源（取并集）：
    1. git status --porcelain：未提交的新增/修改文件（含 untracked）
    2. git diff origin/master...HEAD --name-only：已提交但相对 master 新增的文件

    SKILL.md 要求测试代码直接写到业务仓库的 src/test/java。
    """

    def _is_test_path(norm: str, name: str) -> bool:
        return (
            "src/test/" in norm
            or name.endswith("test.java")
            or name.endswith("test.kt")
            or ".test." in name
            or ".spec." in name
        )

    test_paths: list[Path] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        candidate_paths: set[str] = set()
        try:
            # 路径 1：未提交变更（含 untracked）
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    candidate_paths.add(line[3:].strip())

            # 路径 2：已提交但相对 origin/master 新增的文件
            r2 = subprocess.run(
                ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r2.returncode == 0:
                for line in r2.stdout.splitlines():
                    candidate_paths.add(line.strip())
        except (subprocess.TimeoutExpired, OSError):
            continue

        for path_str in candidate_paths:
            if not path_str:
                continue
            p = repo / path_str
            if not p.is_file() or p.suffix not in _TEST_FILE_SUFFIXES:
                continue
            norm = path_str.replace("\\", "/")
            if _is_test_path(norm, p.name.lower()):
                test_paths.append(p)

    return test_paths


def _collect_supplemental_files(phase_root: Path) -> list[Path]:
    """向后兼容：扫描 supplemental_tests/ 目录.

    生产环境下应通过 code_repos + git status 扫描（_collect_new_test_files_from_repos）。
    无 code_repos 时（如单元测试场景）回落到此目录。
    """
    d = phase_root / "supplemental_tests"
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix in _TEST_FILE_SUFFIXES)


# 向后兼容别名
_collect_supplemental_java = _collect_supplemental_files


def _collect_git_diff_basenames(code_repos: list[str]) -> set[str]:
    """收集所有仓库 git diff 变更文件的 basename（不含路径）."""
    basenames: set[str] = set()
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        for cmd in [
            ["git", "diff", "--name-only", "origin/master...HEAD"],
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            ["git", "status", "--porcelain"],
        ]:
            try:
                r = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=10)
                if r.returncode != 0 or not r.stdout.strip():
                    continue
                for line in r.stdout.splitlines():
                    name = line[3:].strip() if cmd[0] == "git" and "status" in cmd else line.strip()
                    if name.endswith(".java"):
                        basenames.add(Path(name).name)
                if basenames:
                    break
            except (subprocess.TimeoutExpired, OSError):
                continue
    return basenames
