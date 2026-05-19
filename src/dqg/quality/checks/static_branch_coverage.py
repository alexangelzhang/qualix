"""静态分支覆盖率分析：无需运行 mvn test，基于 javalang AST + Mockito 模式推断.

核心流程：
  1. git diff --unified=0 → 变更行号
  2. javalang 解析生产代码 → 枚举变更行上的分支（if/else/catch/switch/ternary）
  3. 扫描测试代码 when().thenReturn() 模式 → 推断哪些分支路径被覆盖
  4. 计算投影行覆盖率 + 分支覆盖率（不依赖 JaCoCo/mvn）
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class Branch:
    """一个分支点（条件的 true/false 两侧各为一个 Branch）."""

    def __init__(
        self,
        file: str,
        line: int,
        branch_type: str,
        condition: str,
        side: str,  # "true" | "false" | "catch" | "case:<value>"
    ) -> None:
        self.file = file
        self.line = line
        self.branch_type = branch_type  # "if" | "try_catch" | "switch" | "ternary"
        self.condition = condition
        self.side = side
        self.covered = False
        self.covered_by: list[str] = []

    @property
    def id(self) -> str:
        return f"{self.file}:{self.line}:{self.side}"

    def __repr__(self) -> str:
        status = "✓" if self.covered else "✗"
        return f"{status} {self.file}:{self.line} [{self.branch_type}] {self.condition!r} → {self.side}"


# ---------------------------------------------------------------------------
# Step 1: git diff → 变更行
# ---------------------------------------------------------------------------


def parse_changed_lines(repo_path: Path, base_ref: str = "origin/master") -> dict[str, set[int]]:
    """返回 {relative_java_path: {行号, ...}}，只含新增/修改行（+行）."""
    result: dict[str, set[int]] = {}
    try:
        proc = subprocess.run(
            ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", "*.java"],
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=30,
        )
        if not proc.stdout:
            return result
    except Exception as exc:
        log.debug("git diff failed: %s", exc)
        return result

    current: str | None = None
    for raw in proc.stdout.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
            parts = path.split("/")
            for i, p in enumerate(parts):
                if p in ("java", "kotlin", "scala"):
                    current = "/".join(parts[i + 1 :])
                    result.setdefault(current, set())
                    break
            else:
                current = None
        elif raw.startswith("@@ ") and current is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                for nr in range(start, start + count):
                    result[current].add(nr)
    return result


# ---------------------------------------------------------------------------
# Step 2: javalang AST → 枚举变更行上的分支
# ---------------------------------------------------------------------------

_JAVALANG_AVAILABLE = False
try:
    import javalang  # type: ignore

    _JAVALANG_AVAILABLE = True
except ImportError:
    log.warning("javalang 未安装，静态分支分析不可用。pip install javalang")


def _node_line(node: Any) -> int | None:
    """从 javalang 节点获取行号."""
    pos = getattr(node, "position", None)
    if pos:
        return pos.line
    return None


def _condition_str(expr: Any) -> str:
    """将 javalang 表达式节点简化为字符串（用于识别条件中的方法调用）."""
    if expr is None:
        return ""
    if hasattr(expr, "member"):
        qualifier = getattr(expr, "qualifier", None)
        if qualifier:
            return f"{qualifier}.{expr.member}"
        return str(expr.member)
    if hasattr(expr, "operandr") and hasattr(expr, "operandl"):
        return f"{_condition_str(expr.operandl)} {getattr(expr, 'operator', '?')} {_condition_str(expr.operandr)}"
    if hasattr(expr, "value"):
        return str(expr.value)
    return type(expr).__name__


def extract_branches_from_source(
    java_source: str,
    relative_path: str,
    changed_lines: set[int],
) -> list[Branch]:
    """解析 Java 源文件，返回落在变更行上的所有分支."""
    if not _JAVALANG_AVAILABLE:
        return []

    try:
        tree = javalang.parse.parse(java_source)
    except Exception as exc:
        log.debug("javalang parse failed for %s: %s", relative_path, exc)
        return []

    branches: list[Branch] = []

    for _, node in tree:
        line = _node_line(node)
        if line is None or line not in changed_lines:
            continue

        # IfStatement
        if isinstance(node, javalang.tree.IfStatement):
            cond = _condition_str(node.condition)
            branches.append(Branch(relative_path, line, "if", cond, "true"))
            branches.append(Branch(relative_path, line, "if", cond, "false"))

        # TryStatement - 每个 catch 子句一个分支
        elif isinstance(node, javalang.tree.TryStatement):
            branches.append(Branch(relative_path, line, "try_catch", "try", "normal"))
            for catch in node.catches or []:
                raw_types = catch.parameter.types if hasattr(catch.parameter, "types") else []
                exc_types = ",".join(t.name if hasattr(t, "name") else str(t) for t in raw_types) or "Exception"
                branches.append(Branch(relative_path, line, "try_catch", "catch", f"catch:{exc_types}"))

        # SwitchStatement - 每个 case 一个分支
        elif isinstance(node, javalang.tree.SwitchStatement):
            expr = _condition_str(node.expression)
            for case in node.cases or []:
                val = str(case.case) if case.case else "default"
                branches.append(Branch(relative_path, line, "switch", expr, f"case:{val}"))

        # TernaryExpression
        elif isinstance(node, javalang.tree.TernaryExpression):
            cond = _condition_str(node.condition)
            branches.append(Branch(relative_path, line, "ternary", cond, "true"))
            branches.append(Branch(relative_path, line, "ternary", cond, "false"))

    return branches


# ---------------------------------------------------------------------------
# Step 3: 测试代码 Mockito 模式扫描
# ---------------------------------------------------------------------------

# 识别 when(xxx.method(...)).thenReturn(value) 中的 method 和 value
_WHEN_PATTERN = re.compile(r"when\s*\(\s*\w+\.(\w+)\s*\(", re.MULTILINE)
_THEN_RETURN_BOOL = re.compile(r"\.thenReturn\s*\(\s*(true|false|null)\s*\)", re.MULTILINE)
_THEN_RETURN_COLLECTION = re.compile(
    r"\.thenReturn\s*\(\s*(Collections\.emptyList|Collections\.singletonList|Arrays\.asList|new ArrayList|Lists\.newArrayList)",
    re.MULTILINE,
)
_THEN_THROW = re.compile(r"\.thenThrow\s*\(", re.MULTILINE)


class TestSignature:
    """测试方法的 Mockito 签名摘要."""

    def __init__(self, method_name: str, source: str) -> None:
        self.method_name = method_name
        self.mock_returns: dict[
            str, set[str]
        ] = {}  # method → {"true","false","null","non_null","non_empty","empty",...}
        self.has_throw: bool = bool(_THEN_THROW.search(source))
        self.has_empty_collection: bool = bool(re.search(r"emptyList|emptyMap|emptySet|Collections\.empty", source))
        self.has_non_empty_collection: bool = bool(
            re.search(r"singletonList|Arrays\.asList|new ArrayList|Lists\.new|ImmutableList", source)
        )

        # 扫描 when(xxx.method(...)).thenReturn(xxx) 中的方法和返回值
        for wm in _WHEN_PATTERN.finditer(source):
            mock_method = wm.group(1)
            after = source[wm.start() :][:500]  # 扩大搜索窗口
            # bool/null
            for tr in _THEN_RETURN_BOOL.finditer(after):
                self.mock_returns.setdefault(mock_method, set()).add(tr.group(1))
            # 空集合 → "empty"
            if _THEN_RETURN_COLLECTION.search(after):
                if re.search(r"empty", after[:300], re.IGNORECASE):
                    self.mock_returns.setdefault(mock_method, set()).add("empty")
                else:
                    self.mock_returns.setdefault(mock_method, set()).add("non_empty")
            # thenReturn(非 bool/null 的具体对象) = "non_null"
            if re.search(r"\.thenReturn\s*\(\s*(?!true|false|null)[^\)]+\)", after[:300]):
                self.mock_returns.setdefault(mock_method, set()).add("non_null")
            # thenThrow
            if _THEN_THROW.search(after[:300]):
                self.mock_returns.setdefault(mock_method, set()).add("throw")

    def returns_true_for(self, method: str) -> bool:
        return "true" in self.mock_returns.get(method, set())

    def returns_false_for(self, method: str) -> bool:
        return "false" in self.mock_returns.get(method, set())

    def returns_null_for(self, method: str) -> bool:
        return "null" in self.mock_returns.get(method, set())

    def returns_non_null_for(self, method: str) -> bool:
        vals = self.mock_returns.get(method, set())
        return bool(vals - {"null", "throw", "empty"})

    def throws_for(self, method: str) -> bool:
        return "throw" in self.mock_returns.get(method, set())

    def mocks_method(self, method: str) -> bool:
        """该测试是否 mock 了该方法（无论返回值）."""
        return method in self.mock_returns


def parse_test_signatures(test_source: str) -> list[TestSignature]:
    """从测试文件提取每个 @Test 方法的签名."""
    sigs: list[TestSignature] = []
    # 简单分割：找到 @Test 注解后的方法体
    parts = re.split(r"@Test\b", test_source)
    for part in parts[1:]:  # 第一个 part 是 @Test 前的内容
        m = re.search(r"public\s+\w+\s+(\w+)\s*\(", part)
        if not m:
            continue
        method_name = m.group(1)
        # 取方法体（到下一个 @Test 或文件结束）
        body_start = m.end()
        # 找方法体结束（简化：取到下一个双换行后的 "}" 或约 100 行）
        body = part[body_start : body_start + 3000]
        sigs.append(TestSignature(method_name, body))
    return sigs


# ---------------------------------------------------------------------------
# Step 4: 分支 → 测试匹配
# ---------------------------------------------------------------------------


def _extract_method_from_condition(condition: str) -> str:
    """从条件字符串提取最后一个方法名，如 'manager.isLogistic' → 'isLogistic'."""
    parts = condition.split(".")
    return parts[-1] if parts else condition


def infer_coverage(branches: list[Branch], test_sigs: list[TestSignature]) -> None:
    """根据 Mockito 模式推断哪些分支被测试覆盖（就地修改 branch.covered）."""
    for branch in branches:
        method = _extract_method_from_condition(branch.condition)
        cond_lower = branch.condition.lower()
        is_null_check = "null" in cond_lower
        is_empty_check = "empty" in cond_lower or "isempty" in cond_lower or "isnotempty" in cond_lower

        if branch.branch_type in ("if", "ternary"):
            if branch.side == "true":
                branch.covered = any(
                    sig.returns_true_for(method)
                    # null check: 有非 null 返回 → 条件中 != null 路径 = true
                    or (is_null_check and sig.returns_non_null_for(method))
                    # 非 empty: 有 non_empty → "isNotEmpty" 分支 = true
                    or (is_empty_check and sig.has_non_empty_collection)
                    # 任何有该方法 mock 的测试（宽松匹配：方法被测试过即认为 true 路径有机会被走到）
                    or sig.mocks_method(method)
                    for sig in test_sigs
                )
            else:  # false
                branch.covered = any(
                    sig.returns_false_for(method)
                    or sig.returns_null_for(method)
                    or (is_empty_check and sig.has_empty_collection)
                    or (is_null_check and sig.returns_null_for(method))
                    for sig in test_sigs
                )
            # 特殊：如果测试里有 (expected = Exception.class) 且 side=true，通常是异常路径 = true
            if not branch.covered and branch.side == "true":
                branch.covered = any("expected" in sig.method_name.lower() or sig.has_throw for sig in test_sigs)

        elif branch.branch_type == "try_catch":
            if branch.side == "normal":
                branch.covered = any(not sig.has_throw for sig in test_sigs)
            else:
                # catch 路径：有 thenThrow 或带 expected 的测试
                branch.covered = any(
                    sig.has_throw
                    or sig.throws_for(method)
                    or "exception" in sig.method_name.lower()
                    or "throw" in sig.method_name.lower()
                    or "error" in sig.method_name.lower()
                    for sig in test_sigs
                )

        elif branch.branch_type == "switch":
            case_val = branch.side.replace("case:", "").lower()
            branch.covered = any(case_val in (sig.method_name + str(sig.mock_returns)).lower() for sig in test_sigs)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def check_static_branch_coverage(
    code_repo: Path | str,
    test_dirs: list[Path | str] | None = None,
    base_ref: str = "origin/master",
) -> dict[str, Any]:
    """静态分析计算增量分支覆盖率，无需运行 mvn test.

    Args:
        code_repo: 代码仓库根目录
        test_dirs: 测试源码目录（默认在 code_repo 下扫描 **/src/test/java）
        base_ref: 基线分支

    Returns:
        {
            "line_coverage": {"rate": 0.95, "covered": N, "total": M},
            "branch_coverage": {"rate": 0.87, "covered": N, "total": M},
            "uncovered_branches": [...],
            "per_file": {...},
            "mode": "static_projection",
        }
    """
    repo = Path(code_repo).expanduser().resolve()

    if not _JAVALANG_AVAILABLE:
        return {
            "error": "javalang 未安装，无法做静态分析。pip install javalang",
            "mode": "static_projection",
        }

    # Step 1: 变更行
    changed_lines_map = parse_changed_lines(repo, base_ref)
    if not changed_lines_map:
        return {
            "line_coverage": {"rate": 1.0, "covered": 0, "total": 0},
            "branch_coverage": {"rate": 1.0, "covered": 0, "total": 0},
            "uncovered_branches": [],
            "mode": "static_projection",
        }

    # Step 2: 扫描测试文件
    if test_dirs is None:
        test_dirs = list(repo.rglob("src/test/java"))
    test_sources: list[str] = []
    for td in test_dirs:
        import contextlib

        for tf in Path(td).rglob("*.java"):
            with contextlib.suppress(Exception):
                test_sources.append(tf.read_text(encoding="utf-8"))

    all_test_sigs: list[TestSignature] = []
    for src in test_sources:
        all_test_sigs.extend(parse_test_signatures(src))

    # Step 3: 对每个变更文件提取分支
    all_branches: list[Branch] = []
    per_file: dict[str, dict[str, Any]] = {}

    for rel_path, changed_lines in changed_lines_map.items():
        # 找到实际文件路径
        java_file: Path | None = None
        candidates = list(repo.rglob(rel_path.split("/")[-1]))
        for c in candidates:
            if str(c).endswith(rel_path.replace("/", str(c.root.__class__.__name__)[-1])) or rel_path in str(c):
                java_file = c
                break
        if java_file is None:
            # 更宽松匹配
            filename = rel_path.split("/")[-1]
            for c in repo.rglob(filename):
                if "test" not in str(c).lower():
                    java_file = c
                    break

        if java_file is None or not java_file.exists():
            log.debug("Cannot find source file for %s", rel_path)
            continue

        try:
            source = java_file.read_text(encoding="utf-8")
        except Exception:
            continue

        file_branches = extract_branches_from_source(source, rel_path, changed_lines)
        if not file_branches:
            continue

        # 获取该文件对应的测试签名（通过类名匹配）
        class_name = rel_path.split("/")[-1].replace(".java", "")
        file_test_sigs = [
            s
            for s in all_test_sigs
            if class_name.lower() in s.method_name.lower() or class_name.lower() in "".join(str(s.mock_returns)).lower()
        ] or all_test_sigs  # fallback: 使用所有测试

        infer_coverage(file_branches, file_test_sigs)
        all_branches.extend(file_branches)

        fc = sum(1 for b in file_branches if b.covered)
        per_file[rel_path] = {
            "total": len(file_branches),
            "covered": fc,
            "rate": round(fc / len(file_branches), 4) if file_branches else 1.0,
        }

    # Step 4: 汇总
    total = len(all_branches)
    covered = sum(1 for b in all_branches if b.covered)
    uncovered = [repr(b) for b in all_branches if not b.covered]

    # 行覆盖率：变更行中有分支覆盖的行数 / 总变更可执行行数（估算）
    total_changed_lines = sum(len(ls) for ls in changed_lines_map.values())
    covered_lines = sum(
        len({b.line for b in all_branches if b.covered and b.file == f}) for f in {b.file for b in all_branches}
    )

    return {
        "line_coverage": {
            "covered": covered_lines,
            "total": total_changed_lines,
            "rate": round(covered_lines / total_changed_lines, 4) if total_changed_lines > 0 else 1.0,
        },
        "branch_coverage": {
            "covered": covered,
            "total": total,
            "rate": round(covered / total, 4) if total > 0 else 1.0,
        },
        "uncovered_branches": uncovered,
        "per_file": per_file,
        "mode": "static_projection",
    }
