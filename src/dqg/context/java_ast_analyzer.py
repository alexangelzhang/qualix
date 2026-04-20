"""Java AST 分析器：基于 tree-sitter 的弱断言检测.

提供 tree-sitter Java AST 解析能力，替代正则匹配。
支持方法调用链分析、变量追踪、跨方法分析。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# tree-sitter 懒加载
_ts_available: bool | None = None
_parser: Any = None


def _ensure_parser() -> bool:
    """懒加载 tree-sitter Java parser."""
    global _ts_available, _parser
    if _ts_available is not None:
        return _ts_available
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
        lang = Language(tsjava.language())
        _parser = Parser(lang)
        _ts_available = True
    except ImportError:
        _ts_available = False
        log.debug("tree-sitter-java not available, falling back to regex")
    return _ts_available


def is_available() -> bool:
    """tree-sitter Java 是否可用."""
    return _ensure_parser()


# ---------------------------------------------------------------------------
# AST 数据结构
# ---------------------------------------------------------------------------

@dataclass
class AssertCall:
    """一次断言调用."""
    kind: str          # assertEquals, assertNotNull, assertThrows, verify, assertThat, assertTrue, ...
    line: int          # 行号(0-based)
    text: str          # 原始代码文本
    is_strong: bool    # 是否强断言
    args: list[str] = field(default_factory=list)  # 参数文本列表


@dataclass
class TestMethod:
    """一个测试方法的 AST 分析结果."""
    name: str
    line_start: int    # 1-based
    line_end: int      # 1-based
    content: str
    asserts: list[AssertCall] = field(default_factory=list)
    verify_calls: list[AssertCall] = field(default_factory=list)
    local_vars: dict[str, str] = field(default_factory=dict)  # var_name → assigned_from
    helper_calls: list[str] = field(default_factory=list)  # 调用的非断言方法


# 强断言方法名
_STRONG_ASSERT_METHODS = frozenset({
    "assertEquals", "assertNotEquals", "assertSame", "assertNotSame",
    "assertArrayEquals", "assertIterableEquals", "assertLinesMatch",
    "assertNull", "assertDoesNotThrow", "assertAll",
    "assertThat",  # Hamcrest/AssertJ
})

# 弱断言方法名
_WEAK_ASSERT_METHODS = frozenset({
    "assertNotNull",
    "assertTrue", "assertFalse",
})

# 所有断言方法名
_ALL_ASSERT_METHODS = _STRONG_ASSERT_METHODS | _WEAK_ASSERT_METHODS | frozenset({"assertThrows"})

# 常量布尔值
_CONSTANT_BOOLEANS = frozenset({"true", "false", "Boolean.TRUE", "Boolean.FALSE"})


def parse_java(source: bytes | str) -> Any:
    """解析 Java 源码，返回 tree-sitter 根节点."""
    if not _ensure_parser():
        return None
    if isinstance(source, str):
        source = source.encode("utf-8")
    tree = _parser.parse(source)
    return tree.root_node


def extract_test_methods(root_node: Any, source: bytes) -> list[TestMethod]:
    """从 AST 中提取所有 @Test 注解的方法."""
    methods: list[TestMethod] = []
    for node in _iter_nodes(root_node, "method_declaration"):
        if not _has_test_annotation(node):
            continue
        name = _get_child_text(node, "identifier", source)
        if not name:
            continue
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        method = TestMethod(
            name=name,
            line_start=start_line,
            line_end=end_line,
            content=content,
        )

        # 分析方法体
        body = _find_child(node, "block")
        if body:
            _analyze_method_body(body, source, method)

        methods.append(method)
    return methods


def extract_helper_methods(root_node: Any, source: bytes) -> dict[str, TestMethod]:
    """提取所有非 @Test 的方法（Helper），用于跨方法分析.

    Returns:
        {method_name: TestMethod} 映射
    """
    helpers: dict[str, TestMethod] = {}
    for node in _iter_nodes(root_node, "method_declaration"):
        if _has_test_annotation(node):
            continue
        name = _get_child_text(node, "identifier", source)
        if not name:
            continue
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        method = TestMethod(
            name=name,
            line_start=start_line,
            line_end=end_line,
            content=content,
        )
        body = _find_child(node, "block")
        if body:
            _analyze_method_body(body, source, method)
        helpers[name] = method
    return helpers


def analyze_assert_strength(
    method: TestMethod,
    helpers: dict[str, TestMethod] | None = None,
) -> dict[str, Any]:
    """分析测试方法的断言强度，返回弱断言信号.

    Args:
        helpers: 同文件内的 Helper 方法映射，用于跨方法分析
    """
    # 跨方法分析：将 helper 中的断言合并到当前方法
    effective_asserts = list(method.asserts)
    effective_verify = list(method.verify_calls)
    resolved_helpers: list[str] = []

    if helpers:
        for helper_name in method.helper_calls:
            helper = helpers.get(helper_name)
            if helper and (helper.asserts or helper.verify_calls):
                effective_asserts.extend(helper.asserts)
                effective_verify.extend(helper.verify_calls)
                resolved_helpers.append(helper_name)

    signals: list[dict[str, str]] = []
    evidence: list[str] = []
    suggestions: list[str] = []

    strong_asserts = [a for a in effective_asserts if a.is_strong]
    weak_asserts = [a for a in effective_asserts if not a.is_strong]
    has_strong = bool(strong_asserts)
    has_verify = bool(effective_verify)

    # Signal 1: 仅 assertNotNull，无强断言
    not_null_only = [a for a in weak_asserts if a.kind == "assertNotNull"]
    if not_null_only and not has_strong and not has_verify:
        signals.append({
            "code": "ASSERT_NOT_NULL_ONLY",
            "severity": "high",
            "reason": "仅 assertNotNull，未验证业务字段、状态或副作用。",
        })
        evidence.extend(a.text.strip() for a in not_null_only[:2])
        suggestions.append("补充关键业务字段、状态迁移或副作用断言")

    # Signal 2: 常量布尔断言
    constant_bools = [
        a for a in weak_asserts
        if a.kind in ("assertTrue", "assertFalse")
        and a.args and a.args[0].strip() in _CONSTANT_BOOLEANS
    ]
    if constant_bools and not has_strong:
        signals.append({
            "code": "CONSTANT_BOOLEAN_ASSERT",
            "severity": "high",
            "reason": "存在常量布尔断言 (如 assertTrue(true))，未实际验证业务结果。",
        })
        evidence.extend(a.text.strip() for a in constant_bools[:2])
        suggestions.append("移除常量布尔断言，改为断言真实业务表达式")

    # Signal 3: 仅 verify，无业务断言
    if has_verify and not has_strong and not weak_asserts:
        signals.append({
            "code": "VERIFY_ONLY_NO_BUSINESS_ASSERT",
            "severity": "high",
            "reason": "仅做交互校验 (verify)，未看到业务结果断言。",
        })
        evidence.extend(v.text.strip() for v in effective_verify[:2])
        suggestions.append("在 verify 之外补充业务结果或副作用断言")

    # Signal 4: assertThrows 无后续业务效果断言
    throws_asserts = [a for a in effective_asserts if a.kind == "assertThrows"]
    if throws_asserts:
        # 检查 assertThrows 返回值是否被用于后续强断言
        throws_var = _find_throws_variable(method)
        has_effect_assert = any(
            a for a in strong_asserts
            if not throws_var or throws_var not in a.text
        )
        if not has_effect_assert:
            signals.append({
                "code": "ASSERT_THROWS_NO_EFFECT_ASSERT",
                "severity": "medium",
                "reason": "只校验抛异常，缺少失败后的业务效果断言（如状态未变更、数据未写入）。",
            })
            evidence.extend(a.text.strip() for a in throws_asserts[:1])
            suggestions.append("补充失败后的状态、数据或副作用断言")

    # Signal 5: 断言数量过少
    total_asserts = len(effective_asserts) + len(effective_verify)
    method_lines = len(method.content.splitlines())
    if total_asserts <= 1 and method_lines > 15 and not signals:
        signals.append({
            "code": "INSUFFICIENT_ASSERTIONS",
            "severity": "medium",
            "reason": f"方法体 {method_lines} 行但仅 {total_asserts} 个断言，可能遗漏关键验证。",
        })
        suggestions.append("检查是否遗漏了对关键业务结果的断言")

    risk = "high" if any(s["severity"] == "high" for s in signals) else ("medium" if signals else "")

    return {
        "method_name": method.name,
        "line_start": method.line_start,
        "line_end": method.line_end,
        "risk_level": risk,
        "signals": signals,
        "evidence": list(dict.fromkeys(evidence))[:4],
        "suggestion": "；".join(dict.fromkeys(suggestions)) if suggestions else "",
        "assert_summary": {
            "strong": len(strong_asserts),
            "weak": len(weak_asserts),
            "verify": len(effective_verify),
            "throws": len(throws_asserts),
            "total": total_asserts,
        },
        "helper_calls": method.helper_calls[:5],
        "resolved_helpers": resolved_helpers,
    }


# ---------------------------------------------------------------------------
# AST 遍历工具
# ---------------------------------------------------------------------------

def _iter_nodes(node: Any, node_type: str):
    """递归遍历 AST，yield 所有指定类型的节点."""
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from _iter_nodes(child, node_type)


def _find_child(node: Any, child_type: str) -> Any:
    """查找第一个指定类型的子节点."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _get_child_text(node: Any, child_type: str, source: bytes) -> str:
    """获取指定类型子节点的文本."""
    child = _find_child(node, child_type)
    if child:
        return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""


def _has_test_annotation(method_node: Any) -> bool:
    """检查方法是否有 @Test 等测试注解."""
    modifiers = _find_child(method_node, "modifiers")
    if not modifiers:
        return False
    test_annotations = {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate"}
    for child in modifiers.children:
        if child.type == "marker_annotation":
            name = child.children[-1] if child.children else None
            if name and name.type == "identifier":
                text = name.text.decode("utf-8", errors="replace") if name.text else ""
                if text in test_annotations:
                    return True
    return False


def _analyze_method_body(body_node: Any, source: bytes, method: TestMethod) -> None:
    """分析方法体中的断言、verify、变量赋值、helper 调用."""
    for node in _iter_nodes(body_node, "expression_statement"):
        expr = node.children[0] if node.children else None
        if not expr:
            continue
        _analyze_expression(expr, source, method)

    # 变量赋值追踪
    for node in _iter_nodes(body_node, "local_variable_declaration"):
        _track_variable(node, source, method)


def _analyze_expression(expr: Any, source: bytes, method: TestMethod) -> None:
    """分析单个表达式：断言调用、verify 调用、helper 调用."""
    text = source[expr.start_byte:expr.end_byte].decode("utf-8", errors="replace")
    line = expr.start_point[0]

    # 方法调用
    if expr.type == "method_invocation":
        method_name = _get_invocation_name(expr, source)
        args = _get_invocation_args(expr, source)

        # 检查链式调用中是否包含 verify: verify(mock).method(args)
        if _chain_contains_verify(expr, source):
            method.verify_calls.append(AssertCall(
                kind="verify", line=line, text=text,
                is_strong=False, args=args,
            ))
            return

        if method_name in _ALL_ASSERT_METHODS:
            is_strong = method_name in _STRONG_ASSERT_METHODS
            # assertTrue/assertFalse 非常量参数视为强断言
            if method_name in ("assertTrue", "assertFalse") and args:
                if args[0].strip() not in _CONSTANT_BOOLEANS:
                    is_strong = True
            method.asserts.append(AssertCall(
                kind=method_name, line=line, text=text,
                is_strong=is_strong, args=args,
            ))
        elif method_name == "verify":
            method.verify_calls.append(AssertCall(
                kind="verify", line=line, text=text,
                is_strong=False, args=args,
            ))
        elif method_name == "assertThat":
            method.asserts.append(AssertCall(
                kind="assertThat", line=line, text=text,
                is_strong=True, args=args,
            ))
        elif not method_name.startswith("assert") and method_name != "verify":
            method.helper_calls.append(method_name)


def _get_invocation_name(node: Any, source: bytes) -> str:
    """获取方法调用的方法名."""
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    # 链式调用: obj.method() — 取最外层方法名
    if node.children and node.children[0].type == "method_invocation":
        return _get_invocation_name(node.children[0], source)
    return ""


def _chain_contains_verify(node: Any, source: bytes) -> bool:
    """检查链式调用中是否包含 verify: verify(mock).method(args)."""
    if node.type == "method_invocation":
        name = ""
        for child in node.children:
            if child.type == "identifier":
                name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
        if name == "verify":
            return True
        # 递归检查内层调用
        for child in node.children:
            if child.type == "method_invocation" and _chain_contains_verify(child, source):
                return True
    return False


def _get_invocation_args(node: Any, source: bytes) -> list[str]:
    """获取方法调用的参数列表."""
    args_node = _find_child(node, "argument_list")
    if not args_node:
        return []
    args: list[str] = []
    for child in args_node.children:
        if child.type not in ("(", ")", ","):
            args.append(source[child.start_byte:child.end_byte].decode("utf-8", errors="replace"))
    return args


def _track_variable(node: Any, source: bytes, method: TestMethod) -> None:
    """追踪局部变量赋值."""
    declarator = _find_child(node, "variable_declarator")
    if not declarator:
        return
    name_node = _find_child(declarator, "identifier")
    if not name_node:
        return
    var_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
    # 赋值来源
    for child in declarator.children:
        if child.type not in ("identifier", "="):
            assigned_from = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            method.local_vars[var_name] = assigned_from
            break


def _find_throws_variable(method: TestMethod) -> str | None:
    """查找 assertThrows 返回值的变量名."""
    for var_name, assigned_from in method.local_vars.items():
        if "assertThrows" in assigned_from:
            return var_name
    return None
