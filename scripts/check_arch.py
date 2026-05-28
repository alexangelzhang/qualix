#!/usr/bin/env python3
"""代码架构铁律自动检查 — pre-commit hook 使用.

检查规则（来自 CLAUDE.md）：
1. 单文件不超过 400 行
2. 单函数不超过 80 行
3. 包内 .py 文件不超过 8 个（不含 __init__.py）
4. 禁止在业务代码中 import logging（应使用 dqg.log）
5. 禁止文件级 json.load(open(...)) 模式（应使用 dqg.json_utils）

pre-commit 模式只检查变更文件，不拦截存量债务。
全量模式（无参数）扫描整个 src/dqg/。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# 豁免列表：已知合理超限的文件（经审计确认为单一职责内聚模块）
LARGE_FILE_EXEMPTIONS: set[str] = {
    "agents/dag_scheduler.py",
    "media/parse_images.py",
    "context/analysis/java_ast_analyzer.py",  # 已迁移到 analysis/ 子包
    "agents/llm_backends.py",
    "store/core.py",
    "core/cli.py",
    "context/analysis/code_skeleton.py",  # 已迁移到 analysis/ 子包
    "quality/checks/_auto_checks_q01.py",  # Q01 专属检查，单一职责，459 行
}

# 豁免列表：允许 import logging 的工具模块
LOG_UTIL_FILES: set[str] = {
    "log.py",
}

# 长函数豁免：prompt builder 等合理超长的函数
LONG_FUNC_EXEMPTIONS: set[tuple[str, str]] = {
    ("tracking/experiment.py", "generate_experiment_prompt"),
}

# 包文件数豁免：存量超限包（待逐步拆分）
PACKAGE_EXEMPTIONS: set[str] = {
    "agents",
    "commands",
    "context",
    "memory",
    "quality",
    "runtime",
    "schemas",
    "store",
    "tracking",
}

# json.load(open(...)) / json.loads(path.read_text()) 文件读取模式
_JSON_FILE_READ_RE = re.compile(r"json\.loads?\s*\(\s*(open\s*\(|.*\.read|.*\.read_text)")

MAX_FILE_LINES = 400
MAX_FUNC_LINES = 80
MAX_PACKAGE_FILES = 8

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "dqg"

# 每条规则存在的原因（降低误报投诉，减少 --no-verify 冲动）
_ARCH_WHY: dict[str, str] = {
    "ARCH-001": "大文件容纳多个职责，难以阅读和单独测试——按功能域拆子模块",
    "ARCH-002": "长函数通常隐含多个逻辑分支，难以单测——提取子函数表达意图",
    "ARCH-003": "包内文件过多预示职责扩散——按功能域建子包，每子包单一关注点",
    "ARCH-004a": "json_utils.load_json 带缓存和错误处理；裸 json.load 在文件不存在时抛难以追踪的异常",
    "ARCH-005": "dqg.log 统一注入 project_id/phase 上下文；裸 import logging 的日志无法关联到具体执行的 Phase",
}


class Violation:
    def __init__(self, file: str, line: int, rule: str, message: str, *, blocking: bool = True):
        self.file = file
        self.line = line
        self.rule = rule
        self.message = message
        self.blocking = blocking  # False = WARNING（不阻塞提交）
        self.why: str = _ARCH_WHY.get(rule, "")

    def __str__(self) -> str:
        tag = "ERROR" if self.blocking else "WARNING"
        base = f"{self.file}:{self.line}: [{self.rule}] {tag}: {self.message}"
        return f"{base}\n    ↳ 原因: {self.why}" if self.why else base


def check_file_lines(path: Path, rel: str) -> list[Violation]:
    """Rule 1: 单文件不超过 400 行."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > MAX_FILE_LINES:
        # 检查豁免
        for exempt in LARGE_FILE_EXEMPTIONS:
            if rel.endswith(exempt):
                return []
        return [Violation(rel, 1, "ARCH-001", f"文件 {len(lines)} 行，超过 {MAX_FILE_LINES} 行上限", blocking=False)]
    return []


def check_func_lines(path: Path, rel: str) -> list[Violation]:
    """Rule 2: 单函数不超过 80 行."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"  WARNING: {rel}: SyntaxError at line {e.lineno}, skipping function length check")
        return []

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_name = node.name
            # 豁免检查
            for exempt_file, exempt_func in LONG_FUNC_EXEMPTIONS:
                if rel.endswith(exempt_file) and func_name == exempt_func:
                    break
            else:
                end = node.end_lineno or node.lineno
                length = end - node.lineno + 1
                if length > MAX_FUNC_LINES:
                    violations.append(
                        Violation(
                            rel,
                            node.lineno,
                            "ARCH-002",
                            f"函数 {func_name}() {length} 行，超过 {MAX_FUNC_LINES} 行上限",
                            blocking=False,
                        )
                    )
    return violations


def check_package_files() -> list[Violation]:
    """Rule 3: 包内 .py 文件不超过 8 个."""
    violations = []
    for pkg_dir in SRC_ROOT.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
            continue
        if pkg_dir.name in PACKAGE_EXEMPTIONS:
            continue
        py_files = [f for f in pkg_dir.glob("*.py") if f.name != "__init__.py"]
        if len(py_files) > MAX_PACKAGE_FILES:
            rel = str(pkg_dir.relative_to(SRC_ROOT.parent.parent))
            violations.append(
                Violation(
                    rel,
                    0,
                    "ARCH-003",
                    f"包内 {len(py_files)} 个 .py 文件，超过 {MAX_PACKAGE_FILES} 个上限",
                    blocking=False,
                )
            )
    return violations


def check_bare_json_file_read(path: Path, rel: str) -> list[Violation]:
    """Rule 4a: 禁止 json.load(open(...)) / json.loads(path.read_text()) 文件读取模式."""
    if rel.endswith("json_utils.py"):
        return []

    violations = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _JSON_FILE_READ_RE.search(line):
            violations.append(Violation(rel, i, "ARCH-004", "json.load/loads 直接读文件，应使用 dqg.json_utils"))
    return violations


def check_bare_logging(path: Path, rel: str) -> list[Violation]:
    """Rule 4b: 禁止在业务代码中 import logging."""
    if any(rel.endswith(f) for f in LOG_UTIL_FILES):
        return []

    violations = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped == "import logging" or stripped.startswith("from logging import"):
            violations.append(Violation(rel, i, "ARCH-005", "裸写 import logging，应使用 dqg.log.get_logger"))
    return violations


def main() -> int:
    # 如果传入了文件列表（pre-commit 模式），只检查这些文件
    files_to_check = sys.argv[1:] if len(sys.argv) > 1 else []

    all_violations: list[Violation] = []

    if files_to_check:
        # pre-commit 模式：只检查传入的文件
        for f in files_to_check:
            path = Path(f).resolve()
            if path.suffix != ".py" or not path.exists():
                continue
            try:
                rel = str(path.relative_to(SRC_ROOT.parent.parent))
            except ValueError:
                continue
            all_violations.extend(check_file_lines(path, rel))
            all_violations.extend(check_func_lines(path, rel))
            all_violations.extend(check_bare_json_file_read(path, rel))
            all_violations.extend(check_bare_logging(path, rel))
    else:
        # 全量模式：扫描整个 src/dqg/
        for path in sorted(SRC_ROOT.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            rel = str(path.relative_to(SRC_ROOT.parent.parent))
            all_violations.extend(check_file_lines(path, rel))
            all_violations.extend(check_func_lines(path, rel))
            all_violations.extend(check_bare_json_file_read(path, rel))
            all_violations.extend(check_bare_logging(path, rel))

    # 包文件数检查（始终全量）
    all_violations.extend(check_package_files())

    if all_violations:
        warnings = [v for v in all_violations if not v.blocking]
        errors = [v for v in all_violations if v.blocking]

        if warnings:
            print("\n架构检查 WARNING（不阻塞提交，建议修复）：\n")
            for v in sorted(warnings, key=lambda x: (x.rule, x.file)):
                print(f"  {v}")

        if errors:
            print("\n架构检查 ERROR（阻塞提交，必须修复）：\n")
            for v in sorted(errors, key=lambda x: (x.rule, x.file)):
                print(f"  {v}")
            print()
            return 1

        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
