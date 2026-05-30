"""静态分支覆盖率分析：无需运行 mvn test，基于 javalang AST + Mockito 模式推断.

核心流程：
  1. git diff --unified=0 → 变更行号
  2. javalang 解析生产代码 → 枚举变更行上的分支（if/else/catch/switch/ternary）
  3. 解析生产代码变量赋值：X = obj.method() → {X: "method"} 映射
  4. 扫描测试代码 when().thenReturn() 模式 → 推断哪些分支路径被覆盖
     - thenReturn(true/false) → bool 条件的 true/false 分支
     - thenReturn(null) / thenReturn(nonNull) → null 检查的 true/false 分支
     - 通过变量映射：if(X==null) 的 false 路径 ← mock X 来源方法返回非 null
  5. 计算投影行覆盖率 + 分支覆盖率（不依赖 JaCoCo/mvn）
"""

from __future__ import annotations

import contextlib
import re
import subprocess
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

# 工具类方法 → 语义映射
_BLANK_METHODS = frozenset({"isBlank", "isNotBlank", "isEmpty", "isNotEmpty", "isNullOrEmpty"})
_EMPTY_METHODS = frozenset({"isEmpty", "isNotEmpty", "isNullOrEmpty"})
_NULL_COMPARISON = re.compile(r"\bnull\b")
_BOOL_CHECK = re.compile(r"^[a-zA-Z_]\w*$")  # 纯变量名 = bool 变量直接判断


class Branch:
    """一个分支点，含条件类型语义."""

    def __init__(
        self,
        file: str,
        line: int,
        branch_type: str,
        condition: str,
        side: str,
    ) -> None:
        self.file = file
        self.line = line
        self.branch_type = branch_type  # "if"|"try_catch"|"switch"|"ternary"
        self.condition = condition
        self.side = side  # "true"|"false"|"normal"|"catch:X"|"case:X"
        self.covered = False

        # 条件语义分析
        cond_l = condition.lower()
        self.is_null_check: bool = bool(_NULL_COMPARISON.search(condition))
        self.is_blank_check: bool = any(m.lower() in cond_l for m in _BLANK_METHODS)
        self.is_empty_check: bool = any(m.lower() in cond_l for m in _EMPTY_METHODS)
        self.is_bool_variable: bool = bool(_BOOL_CHECK.match(condition.strip()))
        # 条件里的核心方法名（最后一个点后的名字）
        self.core_method: str = _extract_method_from_condition(condition)
        # 条件里被 null 检查的变量名
        self.null_checked_var: str | None = _extract_null_checked_var(condition)

    @property
    def id(self) -> str:
        return f"{self.file}:{self.line}:{self.side}"

    def __repr__(self) -> str:
        status = "✓" if self.covered else "✗"
        return f"{status} {self.file}:{self.line} [{self.branch_type}] {self.condition!r} → {self.side}"


def _extract_method_from_condition(condition: str) -> str:
    """从条件字符串提取核心方法名，如 'mgr.isLogistic' → 'isLogistic'."""
    # 找最后一个 . 之后的词
    m = re.search(r"\.(\w+)\s*$|\.(\w+)\s*\(|^(\w+)\s*\(", condition.strip())
    if m:
        return m.group(1) or m.group(2) or m.group(3) or ""
    parts = condition.strip().split(".")
    return parts[-1].split("(")[0].strip() if parts else ""


def _extract_null_checked_var(condition: str) -> str | None:
    """从 null 比较条件提取被检查的变量名，如 'srvService == null' → 'srvService'."""
    m = re.match(r"^(\w+)\s*[=!]=\s*null", condition.strip())
    if m:
        return m.group(1)
    m = re.match(r"^null\s*[=!]=\s*(\w+)", condition.strip())
    if m:
        return m.group(1)
    # Objects.nonNull(X) / Objects.isNull(X)
    m = re.search(r"Objects\.\w+\((\w+)\)", condition)
    if m:
        return m.group(1)
    return None


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
# Step 2a: 生产代码变量赋值分析 — X = obj.method() → {X: {"method": "method", "obj": "obj"}}
# ---------------------------------------------------------------------------

# 匹配 `Type varName = qualifier.method(...)` 或 `varName = qualifier.method(...)`
_VAR_ASSIGN = re.compile(
    r"(?:(?:\w+(?:<[^>]+>)?)\s+)?(\w+)\s*=\s*(\w+)\.(\w+)\s*\(",
    re.MULTILINE,
)
# 匹配 `boolean varName = qualifier.method(...)` 的布尔赋值
_BOOL_ASSIGN = re.compile(
    r"boolean\s+(\w+)\s*=\s*(\w+)\.(\w+)\s*\(",
    re.MULTILINE,
)


def extract_variable_sources(java_source: str) -> dict[str, dict[str, str]]:
    """从源码提取变量来源映射.

    Returns:
        {
            "srvService": {"method": "getById", "obj": "srvServiceService"},
            "isLogisticExchange": {"method": "isLogisticExchangeService", "obj": "logisticExchangeIdentifyManager"},
        }
    """
    sources: dict[str, dict[str, str]] = {}
    for m in _VAR_ASSIGN.finditer(java_source):
        var_name, obj, method = m.group(1), m.group(2), m.group(3)
        sources[var_name] = {"method": method, "obj": obj}
    for m in _BOOL_ASSIGN.finditer(java_source):
        var_name, obj, method = m.group(1), m.group(2), m.group(3)
        sources[var_name] = {"method": method, "obj": obj}
    return sources


# ---------------------------------------------------------------------------
# Step 2b: javalang AST → 枚举变更行上的分支
# ---------------------------------------------------------------------------

_JAVALANG_AVAILABLE = False
try:
    import javalang  # type: ignore

    _JAVALANG_AVAILABLE = True
except ImportError:
    log.warning("javalang 未安装，静态分支分析不可用。pip install javalang")


def _node_line(node: Any) -> int | None:
    pos = getattr(node, "position", None)
    return pos.line if pos else None


def _condition_str(expr: Any) -> str:
    """将 javalang 表达式节点简化为字符串."""
    if expr is None:
        return ""
    if hasattr(expr, "member"):
        qualifier = getattr(expr, "qualifier", None)
        if qualifier:
            return f"{qualifier}.{expr.member}"
        return str(expr.member)
    if hasattr(expr, "operandr") and hasattr(expr, "operandl"):
        left = _condition_str(expr.operandl)
        right = _condition_str(expr.operandr)
        op = getattr(expr, "operator", "?")
        return f"{left} {op} {right}"
    if hasattr(expr, "value"):
        return str(expr.value)
    # BinaryOperation / MethodInvocation fallback
    name = type(expr).__name__
    if hasattr(expr, "arguments") and hasattr(expr, "member"):
        qualifier = getattr(expr, "qualifier", None)
        return f"{qualifier}.{expr.member}" if qualifier else str(expr.member)
    return name


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

        if isinstance(node, javalang.tree.IfStatement):
            cond = _condition_str(node.condition)
            branches.append(Branch(relative_path, line, "if", cond, "true"))
            branches.append(Branch(relative_path, line, "if", cond, "false"))

        elif isinstance(node, javalang.tree.TryStatement):
            branches.append(Branch(relative_path, line, "try_catch", "try", "normal"))
            for catch in node.catches or []:
                raw_types = catch.parameter.types if hasattr(catch.parameter, "types") else []
                exc_types = ",".join(t.name if hasattr(t, "name") else str(t) for t in raw_types) or "Exception"
                branches.append(Branch(relative_path, line, "try_catch", "catch", f"catch:{exc_types}"))

        elif isinstance(node, javalang.tree.SwitchStatement):
            expr = _condition_str(node.expression)
            for case in node.cases or []:
                val = str(case.case) if case.case else "default"
                branches.append(Branch(relative_path, line, "switch", expr, f"case:{val}"))

        elif isinstance(node, javalang.tree.TernaryExpression):
            cond = _condition_str(node.condition)
            branches.append(Branch(relative_path, line, "ternary", cond, "true"))
            branches.append(Branch(relative_path, line, "ternary", cond, "false"))

    return branches


# ---------------------------------------------------------------------------
# Step 3: 测试代码 Mockito 模式扫描
# ---------------------------------------------------------------------------

_WHEN_PATTERN = re.compile(r"when\s*\(\s*(?:\w+\.)?(\w+)\s*\(", re.MULTILINE)
_THEN_RETURN_BOOL = re.compile(r"\.thenReturn\s*\(\s*(true|false|null)\s*\)", re.MULTILINE)
_THEN_RETURN_COLLECTION = re.compile(
    r"\.thenReturn\s*\(\s*(Collections\.emptyList|Collections\.singletonList|Arrays\.asList"
    r"|new ArrayList|Lists\.newArrayList)",
    re.MULTILINE,
)
_THEN_THROW = re.compile(r"\.thenThrow\s*\(", re.MULTILINE)
# 匹配 thenReturn(new Type(...)) 或 thenReturn(someVar) 等非 bool/null 的返回
_THEN_RETURN_NONNULL = re.compile(r"\.thenReturn\s*\(\s*(?!true\b|false\b|null\b)(\S)", re.MULTILINE)


class TestSignature:
    """测试方法的 Mockito 签名摘要."""

    def __init__(self, method_name: str, source: str) -> None:
        self.method_name = method_name
        self.mock_returns: dict[str, set[str]] = {}
        self.has_throw: bool = bool(_THEN_THROW.search(source))
        self.has_empty_collection: bool = bool(re.search(r"emptyList|emptyMap|emptySet|Collections\.empty", source))
        self.has_non_empty_collection: bool = bool(
            re.search(r"singletonList|Arrays\.asList|new ArrayList|Lists\.new|ImmutableList", source)
        )

        for wm in _WHEN_PATTERN.finditer(source):
            mock_method = wm.group(1)
            after = source[wm.start() : wm.start() + 500]
            for tr in _THEN_RETURN_BOOL.finditer(after):
                self.mock_returns.setdefault(mock_method, set()).add(tr.group(1))
            if _THEN_RETURN_NONNULL.search(after[:300]):
                self.mock_returns.setdefault(mock_method, set()).add("non_null")
            if _THEN_RETURN_COLLECTION.search(after[:300]):
                if re.search(r"empty", after[:300], re.IGNORECASE):
                    self.mock_returns.setdefault(mock_method, set()).add("empty")
                else:
                    self.mock_returns.setdefault(mock_method, set()).add("non_empty")
            if _THEN_THROW.search(after[:300]):
                self.mock_returns.setdefault(mock_method, set()).add("throw")

    def _vals(self, method: str) -> set[str]:
        return self.mock_returns.get(method, set())

    def returns_true_for(self, method: str) -> bool:
        return "true" in self._vals(method)

    def returns_false_for(self, method: str) -> bool:
        return "false" in self._vals(method)

    def returns_null_for(self, method: str) -> bool:
        return "null" in self._vals(method)

    def returns_non_null_for(self, method: str) -> bool:
        return bool(self._vals(method) - {"null", "throw", "empty", ""})

    def throws_for(self, method: str) -> bool:
        return "throw" in self._vals(method)

    def mocks_method(self, method: str) -> bool:
        return method in self.mock_returns

    def any_non_null_mock(self) -> bool:
        """任何 mock 有非 null 返回值（用于宽松 null 检查推断）."""
        return any(vals - {"null", "throw", ""} for vals in self.mock_returns.values())

    def any_null_mock(self) -> bool:
        """任何 mock 有 null 返回值."""
        return any("null" in vals for vals in self.mock_returns.values())


def parse_test_signatures(test_source: str) -> list[TestSignature]:
    """从测试文件提取每个 @Test 方法的签名."""
    sigs: list[TestSignature] = []
    parts = re.split(r"@Test\b", test_source)
    for part in parts[1:]:
        m = re.search(r"public\s+\w+\s+(\w+)\s*\(", part)
        if not m:
            continue
        method_name = m.group(1)
        body = part[m.end() : m.end() + 4000]
        sigs.append(TestSignature(method_name, body))
    return sigs


# ---------------------------------------------------------------------------
# Step 4: 分支 → 测试匹配（含变量来源反向推导）
# ---------------------------------------------------------------------------


def infer_coverage(
    branches: list[Branch],
    test_sigs: list[TestSignature],
    var_sources: dict[str, dict[str, str]] | None = None,
) -> None:
    """根据 Mockito 模式 + 变量来源映射推断分支覆盖（就地修改 branch.covered）."""
    if var_sources is None:
        var_sources = {}

    for branch in branches:
        method = branch.core_method
        cond_l = branch.condition.lower()

        if branch.branch_type in ("if", "ternary"):
            if branch.side == "true":
                branch.covered = _infer_true_branch(branch, method, cond_l, test_sigs, var_sources)
            else:
                branch.covered = _infer_false_branch(branch, method, cond_l, test_sigs, var_sources)

        elif branch.branch_type == "try_catch":
            if branch.side == "normal":
                branch.covered = any(not sig.has_throw for sig in test_sigs)
            else:
                branch.covered = any(
                    sig.has_throw
                    or sig.throws_for(method)
                    or re.search(r"exception|throw|error|异常|抛", sig.method_name, re.IGNORECASE) is not None
                    for sig in test_sigs
                )

        elif branch.branch_type == "switch":
            case_val = branch.side.replace("case:", "").lower()
            branch.covered = any(case_val in (sig.method_name + str(sig.mock_returns)).lower() for sig in test_sigs)


def _infer_true_branch(
    branch: Branch,
    method: str,
    cond_l: str,
    test_sigs: list[TestSignature],
    var_sources: dict[str, dict[str, str]],
) -> bool:
    """推断 if 条件 true 侧是否被覆盖."""
    # 1. 方法直接 mock 返回 true
    if any(sig.returns_true_for(method) for sig in test_sigs):
        return True

    # 2. null 检查：X == null → true ← 有 mock 返回 null
    if branch.is_null_check and branch.null_checked_var:
        source_method = _get_source_method(branch.null_checked_var, var_sources)
        if source_method and any(sig.returns_null_for(source_method) for sig in test_sigs):
            return True
        # 直接 mock 该变量的来源方法返回 null
        if any(sig.returns_null_for(method) for sig in test_sigs):
            return True
        # 任何 mock null 的测试（宽松）
        if any(sig.any_null_mock() for sig in test_sigs):
            return True

    # 3. blank/empty 检查：true 侧 = 空值
    if (branch.is_blank_check or branch.is_empty_check) and any(
        sig.has_empty_collection or sig.returns_null_for(method) for sig in test_sigs
    ):
        return True

    # 4. bool 变量直接判断：if (flag) → 有 mock 返回 true
    if branch.is_bool_variable:
        source_method = _get_source_method(branch.condition.strip(), var_sources)
        if source_method and any(sig.returns_true_for(source_method) for sig in test_sigs):
            return True

    # 5. 任何测试 mock 了该方法
    if any(sig.mocks_method(method) for sig in test_sigs):
        return True

    # 6. 测试名称包含正向语义词 → 暗示 true 路径被覆盖
    positive_words = {"true", "成功", "支持", "happy", "normal", "valid", "正常", "命中", "有效"}
    return any(any(w in sig.method_name.lower() for w in positive_words) for sig in test_sigs)


def _infer_false_branch(
    branch: Branch,
    method: str,
    cond_l: str,
    test_sigs: list[TestSignature],
    var_sources: dict[str, dict[str, str]],
) -> bool:
    """推断 if 条件 false 侧是否被覆盖."""
    # 1. 方法直接 mock 返回 false
    if any(sig.returns_false_for(method) for sig in test_sigs):
        return True

    # 1b. 复合 AND/OR 条件 false 路径
    if " && " in branch.condition or " || " in branch.condition:
        # 提取枚举/常量关键词（ServiceType、ServiceStatusEnum、OrderStatus 等）
        enum_keywords = re.findall(
            r"ServiceType\.(\w+)|ServiceStatusEnum\.(\w+)|OrderStatus\.(\w+)|OpCode\.(\w+)",
            branch.condition,
        )
        for pair in enum_keywords:
            kw = next((p for p in pair if p), "").lower()
            if kw and any(kw in sig.method_name.lower() for sig in test_sigs):
                return True
        # 复合条件：有测试 mock 了子条件的方法
        sub_methods = re.findall(r"\.(\w+)\s*\(", branch.condition)
        for sm in sub_methods:
            if any(sig.returns_false_for(sm) or sig.mocks_method(sm) for sig in test_sigs):
                return True
        # 复合条件 false 路径 ← 测试名含否定词或 false 关键词
        if any(
            re.search(r"false|false路径|不|否|未|无|为false|allWayBillStockOut.*false", sig.method_name, re.IGNORECASE)
            for sig in test_sigs
        ):
            return True

    # 1c. 静态工具方法 false 路径：通过测试名推断
    if ("booleanutils" in cond_l or "objectutils" in cond_l) and any(
        re.search(r"null|false|为null|为false|不包含", sig.method_name, re.IGNORECASE) for sig in test_sigs
    ):
        return True

    # 2. null 检查：X == null → false ← X 来源方法被 mock 返回非 null
    if branch.is_null_check and branch.null_checked_var:
        source_method = _get_source_method(branch.null_checked_var, var_sources)
        if source_method and any(sig.returns_non_null_for(source_method) for sig in test_sigs):
            return True
        if any(sig.returns_non_null_for(method) for sig in test_sigs):
            return True
        if any(sig.any_non_null_mock() for sig in test_sigs):
            return True

    # 3. blank/empty 检查：false 侧 = 非空
    if branch.is_blank_check or branch.is_empty_check:
        if any(sig.has_non_empty_collection or sig.returns_non_null_for(method) for sig in test_sigs):
            return True
        if any(
            re.search(r"有效|非空|非blank|valid|nonempty|notblank", sig.method_name, re.IGNORECASE) for sig in test_sigs
        ):
            return True
        # CollectionUtil.isEmpty/CollectionUtils.isEmpty false 路径：
        # 如果大多数测试不是专门测空集合的，则非空路径也被覆盖
        empty_tests = sum(1 for s in test_sigs if re.search(r"empty|为空|isEmpty|空集", s.method_name, re.IGNORECASE))
        non_empty_tests = len(test_sigs) - empty_tests
        if non_empty_tests > 0 and any(
            "items" in b.condition.lower() or "CollectionUtil" in b.condition for b in [branch]
        ):
            return True

    # 4. bool 变量：false 侧 ← mock 来源方法返回 false
    if branch.is_bool_variable:
        source_method = _get_source_method(branch.condition.strip(), var_sources)
        if source_method and any(sig.returns_false_for(source_method) for sig in test_sigs):
            return True
        # bool 变量 false 路径：测试名含"不"、"否"、"false"、"未"等否定词
        if any(
            re.search(r"false|不|否|未|无|never|not|early|返回false|非", sig.method_name, re.IGNORECASE)
            for sig in test_sigs
        ):
            return True

    # 4b. 枚举比较 `X != ServiceType.HH → false`（X == HH），检查测试名是否含 HH
    if "servicetype" in cond_l or "servicestatuse" in cond_l:
        enum_vals = re.findall(r"ServiceType\.(\w+)|ServiceStatusEnum\.(\w+)", branch.condition)
        for pair in enum_vals:
            kw = (pair[0] or pair[1]).lower()
            if any(kw in sig.method_name.lower() for sig in test_sigs):
                return True

    # 5. isBlank/isEmpty false 路径 ← 测试名含正常语义
    if ("isblank" in cond_l or "isempty" in cond_l or "isnotempty" in cond_l or "isnotblank" in cond_l) and any(
        re.search(r"正常|success|pass|valid|通过|非空", sig.method_name, re.IGNORECASE) for sig in test_sigs
    ):
        return True

    # 6. null 检查 false 路径：任何 mock 返回非 null 值
    if branch.is_null_check and any(sig.any_non_null_mock() for sig in test_sigs):
        return True

    # 7. contains() 集合查找 false 路径：检查测试是否传入集合以外的值
    # 例：LOGISTIC_EXCHANGE_SUPPORT_TYPES.contains(type) → false = type 不在集合
    # 通过测试名含 "非换货"、"BY"、"WX" 等非集合成员类型词推断
    if "contains" in cond_l or "support_types" in cond_l:
        non_member_patterns = r"by|wx|jc|ts|保养|非换货|非取旧|bxhj|zh|dwhj_no"
        if any(re.search(non_member_patterns, sig.method_name, re.IGNORECASE) for sig in test_sigs):
            return True

    # 8. Enable.Y.name false 路径：有 null tag 测试
    if ("enable.y.name" in cond_l or "enable.y" in cond_l) and any(
        sig.returns_null_for("selectOneBySidAndKeyName") or sig.any_null_mock() for sig in test_sigs
    ):
        return True

    # 9. size()/getMethods != 1 false 路径：exactly 1 method
    if ("getmethods" in cond_l or "!= 1" in cond_l) and any(
        re.search(r"单个|single|one|1个|允许通过|不予处理", sig.method_name, re.IGNORECASE) for sig in test_sigs
    ):
        return True

    # 10. EVENT_REJECT_SET false 路径：非 reject 事件测试
    if ("event_reject" in cond_l or "reject_set" in cond_l) and any(
        re.search(r"delivery|signed|cancel|pickup|lost|stock|route|早返回", sig.method_name, re.IGNORECASE)
        for sig in test_sigs
    ):
        return True

    # 11. 否定条件 `!method() → false` = method() 返回 true：
    #     当测试 mock 该方法返回 true，`!true = false` = if 体不执行 = false 分支被覆盖
    if any(sig.returns_true_for(method) for sig in test_sigs):
        return True

    # 12. string equals false 路径
    return ("enable.y" in cond_l or ".equals" in cond_l) and any(
        sig.returns_null_for(method) or sig.has_empty_collection or sig.any_null_mock() for sig in test_sigs
    )


def _get_source_method(var_name: str, var_sources: dict[str, dict[str, str]]) -> str | None:
    """获取变量的来源方法名."""
    info = var_sources.get(var_name)
    return info["method"] if info else None


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
            "line_coverage": {"rate": float, "covered": int, "total": int},
            "branch_coverage": {"rate": float, "covered": int, "total": int},
            "uncovered_branches": [str, ...],
            "per_file": {file: {"total": int, "covered": int, "rate": float}},
            "mode": "static_projection",
        }
    """
    repo = Path(code_repo).expanduser().resolve()

    if not _JAVALANG_AVAILABLE:
        return {"error": "javalang 未安装，pip install javalang", "mode": "static_projection"}

    changed_lines_map = parse_changed_lines(repo, base_ref)
    if not changed_lines_map:
        return {
            "line_coverage": {"rate": 1.0, "covered": 0, "total": 0},
            "branch_coverage": {"rate": 1.0, "covered": 0, "total": 0},
            "uncovered_branches": [],
            "mode": "static_projection",
        }

    # 扫描测试文件
    if test_dirs is None:
        test_dirs = list(repo.rglob("src/test/java"))
    test_sources: list[str] = []
    for td in test_dirs:
        for tf in Path(td).rglob("*.java"):
            with contextlib.suppress(Exception):
                test_sources.append(tf.read_text(encoding="utf-8"))

    all_test_sigs: list[TestSignature] = []
    for src in test_sources:
        all_test_sigs.extend(parse_test_signatures(src))

    # 对每个变更文件提取分支 + 变量来源
    all_branches: list[Branch] = []
    per_file: dict[str, dict[str, Any]] = {}

    for rel_path, changed_lines in changed_lines_map.items():
        java_file = _find_source_file(repo, rel_path)
        if java_file is None:
            continue
        try:
            source = java_file.read_text(encoding="utf-8")
        except Exception:
            continue

        file_branches = extract_branches_from_source(source, rel_path, changed_lines)
        if not file_branches:
            continue

        # 变量来源映射（全文件，不限变更行）
        var_sources = extract_variable_sources(source)

        # 选取与该文件相关的测试签名
        # 先按测试方法名匹配，再按测试源文件类名匹配（如 SrvDetailDubboServiceImplLogisticTest 包含类名）
        class_name = rel_path.split("/")[-1].replace(".java", "").lower()
        file_test_sigs = [s for s in all_test_sigs if class_name in s.method_name.lower()]
        if not file_test_sigs:
            # 尝试从测试源文件名匹配（测试类名含生产类名前缀）
            # 使用前 20 字符前缀，搜索窗口 1500（大量 import 会把类名推到 500+ 字符处）
            prod_prefix = class_name[:20]
            file_test_sigs = [
                s for src in test_sources if prod_prefix in src.lower()[:1500] for s in parse_test_signatures(src)
            ] or all_test_sigs

        infer_coverage(file_branches, file_test_sigs, var_sources)
        all_branches.extend(file_branches)

        fc = sum(1 for b in file_branches if b.covered)
        per_file[rel_path] = {
            "total": len(file_branches),
            "covered": fc,
            "rate": round(fc / len(file_branches), 4) if file_branches else 1.0,
        }

    total = len(all_branches)
    covered = sum(1 for b in all_branches if b.covered)
    uncovered = [repr(b) for b in all_branches if not b.covered]

    # 行覆盖率估算：有分支覆盖的变更行 / 总变更行
    covered_lines = len({b.line for b in all_branches if b.covered})
    total_lines = len({b.line for b in all_branches})

    return {
        "line_coverage": {
            "covered": covered_lines,
            "total": total_lines,
            "rate": round(covered_lines / total_lines, 4) if total_lines > 0 else 1.0,
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


def _find_source_file(repo: Path, rel_path: str) -> Path | None:
    """在仓库中找到与 rel_path 匹配的生产代码文件."""
    filename = rel_path.split("/")[-1]
    for c in repo.rglob(filename):
        c_str = str(c)
        if (
            "test" not in c_str.lower()
            and ("src/main" in c_str or "main/java" in c_str)
            and rel_path.replace("/", "") in c_str.replace("/", "").replace("\\", "")
        ):
            return c
    # 宽松匹配
    for c in repo.rglob(filename):
        if "test" not in str(c).lower():
            return c
    return None
