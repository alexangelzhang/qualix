#!/usr/bin/env python3
"""正则表达式静态检查 — pre-commit hook / CI 门禁.

检测规则（捕获最常见的误写类型）：

R1 字符类里含竖线（可能误将交替式写成字符类）
   示例误写: r"[来源:|source:]"  → 实为字符类，不是 r"来源:|source:"
   判断方法: [...] 内有 | 且 | 两侧任一侧包含 ≥2 个连续字母/CJK 字符
   （单字符集合如 [\\s\\-:|] 里的 | 是合意字面量，不报警）

用法:
    python scripts/check_regex.py                    # 扫描 src/qualix/ 全量
    python scripts/check_regex.py src/foo/bar.py     # 扫描指定文件
    python scripts/check_regex.py --staged           # 只扫描 git staged 文件

退出码:
    0 — 全部通过
    1 — 发现问题
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

SRC_ROOT = Path(__file__).parent.parent / "src" / "qualix"

# ---------------------------------------------------------------------------
# 正则 pattern 解析工具
# ---------------------------------------------------------------------------


def _iter_charclass_spans(pattern: str) -> list[tuple[int, int]]:
    """返回 pattern 内所有 [...] 字符类的 (start, end) 区间（end 为 ] 后一位）."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i] == "\\" and i + 1 < n:
            i += 2
            continue
        if pattern[i] == "[":
            j = i + 1
            # [^ 开头
            if j < n and pattern[j] == "^":
                j += 1
            # ] 作为首字符时是字面量，不闭合
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                if pattern[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            spans.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return spans


def _has_word_sequence(segment: str) -> bool:
    """该分段里是否含 ≥2 个连续字母/CJK 字符（暗示程序员意图写单词/词组而非字符集）.

    转义序列（\\s \\d \\w 等）和标点不算 word char，不会触发报警。
    这让 [\\s\\-:|] 里的 | 不被误报，但 [来源:|source:] 可被正确捕获。
    """
    _WORD_CHAR = re.compile(r"[A-Za-z0-9一-鿿]")
    run = 0
    i = 0
    while i < len(segment):
        if segment[i] == "\\" and i + 1 < len(segment):
            run = 0  # 转义序列不是 word char，重置连续计数
            i += 2
        elif _WORD_CHAR.match(segment[i]):
            run += 1
            if run >= 2:
                return True
            i += 1
        else:
            run = 0
            i += 1
    return False


def check_pipe_in_charclass(pattern: str) -> list[str]:
    """R1: 检测字符类内的竖线误用.

    仅当 | 两侧任一侧有 ≥2 个连续 word/CJK 字符时报告：
    - [来源:|source:]  → 报告（来源 是 2 个连续 CJK）
    - [foo|bar]        → 报告（foo 是 3 个连续 ASCII）
    - [\\s\\-:|]       → 不报告（| 两侧均无连续 word char）
    - [A-Za-z0-9]      → 无 |，不触发
    """
    findings: list[str] = []
    for start, end in _iter_charclass_spans(pattern):
        inner = pattern[start + 1 : end - 1]
        if inner.startswith("^"):
            inner = inner[1:]
        if "|" not in inner:
            continue
        segments = inner.split("|")
        if any(_has_word_sequence(seg) for seg in segments):
            findings.append(pattern[start:end])
    return findings




# ---------------------------------------------------------------------------
# AST 提取：找出所有 re.* 调用及其 pattern 参数
# ---------------------------------------------------------------------------


class RegexCall(NamedTuple):
    file: str
    line: int
    func: str       # compile / search / match / findall / sub ...
    pattern: str    # pattern 字符串（仅当能静态提取时）


_RE_FUNCS = frozenset(
    ["compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"]
)


def extract_regex_calls(source: str, filename: str) -> list[RegexCall]:
    """从 Python 源码中提取所有 re.* 调用及其 pattern 参数."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    results: list[RegexCall] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # re.xxx(pattern, ...) 形式
        func_name: str | None = None
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _RE_FUNCS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
        ):
            func_name = node.func.attr

        if func_name is None or not node.args:
            continue

        pattern_node = node.args[0]
        # 只处理字符串字面量（包括 r"..." 和拼接）
        pattern_val = _extract_str_literal(pattern_node)
        if pattern_val is None:
            continue

        results.append(RegexCall(filename, node.lineno, func_name, pattern_val))

    return results


def _extract_str_literal(node: ast.expr) -> str | None:
    """从 AST 节点提取字符串值（支持字面量和简单拼接）."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # f-string 或变量引用：无法静态分析，跳过
    return None


# ---------------------------------------------------------------------------
# 检查逻辑
# ---------------------------------------------------------------------------


class Issue(NamedTuple):
    file: str
    line: int
    rule: str
    detail: str


def check_file(path: Path) -> list[Issue]:
    source = path.read_text(encoding="utf-8", errors="ignore")
    calls = extract_regex_calls(source, str(path))
    issues: list[Issue] = []

    for call in calls:
        # R1/R2: 字符类里含竖线
        pipe_findings = check_pipe_in_charclass(call.pattern)
        for finding in pipe_findings:
            issues.append(
                Issue(
                    call.file,
                    call.line,
                    "R1",
                    f"字符类 {finding!r} 内含 | —— 本意是交替式吗？"
                    f"  误写: r\"[a|b]\"  正确: r\"(?:a|b)\" 或 r\"a|b\"",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# 文件收集
# ---------------------------------------------------------------------------


def collect_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            files.extend(p.rglob("*.py"))
    return files


def get_staged_py_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    return [Path(f) for f in result.stdout.splitlines() if f.endswith(".py") and Path(f).exists()]


# ---------------------------------------------------------------------------
# 白名单（历史遗留，不阻断 CI）
# ---------------------------------------------------------------------------

# 已确认为合意写法的（file_relative_path, line_no）或 (file_relative_path, None) 豁免整文件
_ALLOWLIST: set[tuple[str, int | None]] = set()


def _is_allowed(issue: Issue) -> bool:
    rel = str(Path(issue.file).resolve().relative_to(Path(__file__).parent.parent))
    return (rel, issue.line) in _ALLOWLIST or (rel, None) in _ALLOWLIST


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--staged" in args:
        files = get_staged_py_files()
        if not files:
            print("check_regex: no staged .py files, skipping")
            return 0
    elif args:
        files = collect_files([a for a in args if not a.startswith("--")])
    else:
        files = collect_files([str(SRC_ROOT)])

    all_issues: list[Issue] = []
    for f in files:
        all_issues.extend(check_file(f))

    real_issues = [i for i in all_issues if not _is_allowed(i)]

    if not real_issues:
        print(f"check_regex: {len(files)} 个文件全部通过")
        return 0

    print(f"check_regex: 发现 {len(real_issues)} 个问题\n")
    for issue in sorted(real_issues, key=lambda i: (i.file, i.line)):
        print(f"  {issue.file}:{issue.line}  [{issue.rule}]  {issue.detail}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
