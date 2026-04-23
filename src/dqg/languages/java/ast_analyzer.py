"""Java AST 分析器：基于 tree-sitter 的弱断言检测.

从 context/java_ast_analyzer.py 迁入。
提供 tree-sitter Java AST 解析能力，替代正则匹配。
支持方法调用链分析、变量追踪、跨方法分析。

底层 AST 遍历工具在 _ast_utils.py 中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dqg.languages.java._ast_utils import (
    analyze_method_body,
    find_child,
    find_throws_variable,
    get_child_text,
    has_test_annotation,
    iter_nodes,
)
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

    kind: str  # assertEquals, assertNotNull, assertThrows, verify, ...
    line: int  # 行号(0-based)
    text: str  # 原始代码文本
    is_strong: bool  # 是否强断言
    args: list[str] = field(default_factory=list)


@dataclass
class TestMethod:
    """一个测试方法的 AST 分析结果."""

    name: str
    line_start: int  # 1-based
    line_end: int  # 1-based
    content: str
    asserts: list[AssertCall] = field(default_factory=list)
    verify_calls: list[AssertCall] = field(default_factory=list)
    local_vars: dict[str, str] = field(default_factory=dict)
    helper_calls: list[str] = field(default_factory=list)


# 断言方法集合
_STRONG_ASSERT_METHODS = frozenset(
    {
        "assertEquals",
        "assertNotEquals",
        "assertSame",
        "assertNotSame",
        "assertArrayEquals",
        "assertIterableEquals",
        "assertLinesMatch",
        "assertNull",
        "assertDoesNotThrow",
        "assertAll",
        "assertThat",
    }
)

_WEAK_ASSERT_METHODS = frozenset(
    {
        "assertNotNull",
        "assertTrue",
        "assertFalse",
    }
)

_ALL_ASSERT_METHODS = _STRONG_ASSERT_METHODS | _WEAK_ASSERT_METHODS | frozenset({"assertThrows"})

_CONSTANT_BOOLEANS = frozenset({"true", "false", "Boolean.TRUE", "Boolean.FALSE"})


def parse_java(source: bytes | str) -> Any:
    """解析 Java 源码，返回 tree-sitter 根节点."""
    if not _ensure_parser():
        return None
    if isinstance(source, str):
        source = source.encode("utf-8")
    tree = _parser.parse(source)
    return tree.root_node


def _extract_method(node: Any, source: bytes) -> TestMethod | None:
    """从 AST 节点提取一个方法."""
    name = get_child_text(node, "identifier", source)
    if not name:
        return None
    content = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    method = TestMethod(
        name=name,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        content=content,
    )
    body = find_child(node, "block")
    if body:
        analyze_method_body(body, source, method, _ALL_ASSERT_METHODS, _STRONG_ASSERT_METHODS, _CONSTANT_BOOLEANS)
    return method


def extract_test_methods(root_node: Any, source: bytes) -> list[TestMethod]:
    """从 AST 中提取所有 @Test 注解的方法."""
    methods: list[TestMethod] = []
    for node in iter_nodes(root_node, "method_declaration"):
        if not has_test_annotation(node):
            continue
        method = _extract_method(node, source)
        if method:
            methods.append(method)
    return methods


def extract_helper_methods(root_node: Any, source: bytes) -> dict[str, TestMethod]:
    """提取所有非 @Test 的方法（Helper），用于跨方法分析."""
    helpers: dict[str, TestMethod] = {}
    for node in iter_nodes(root_node, "method_declaration"):
        if has_test_annotation(node):
            continue
        method = _extract_method(node, source)
        if method:
            helpers[method.name] = method
    return helpers


def analyze_assert_strength(
    method: TestMethod,
    helpers: dict[str, TestMethod] | None = None,
) -> dict[str, Any]:
    """分析测试方法的断言强度，返回弱断言信号."""
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

    # Signal 1: 仅 assertNotNull
    not_null_only = [a for a in weak_asserts if a.kind == "assertNotNull"]
    if not_null_only and not has_strong and not has_verify:
        signals.append(
            {
                "code": "ASSERT_NOT_NULL_ONLY",
                "severity": "high",
                "reason": "仅 assertNotNull，未验证业务字段、状态或副作用。",
            }
        )
        evidence.extend(a.text.strip() for a in not_null_only[:2])
        suggestions.append("补充关键业务字段、状态迁移或副作用断言")

    # Signal 2: 常量布尔断言
    constant_bools = [
        a
        for a in weak_asserts
        if a.kind in ("assertTrue", "assertFalse") and a.args and a.args[0].strip() in _CONSTANT_BOOLEANS
    ]
    if constant_bools and not has_strong:
        signals.append(
            {
                "code": "CONSTANT_BOOLEAN_ASSERT",
                "severity": "high",
                "reason": "存在常量布尔断言 (如 assertTrue(true))，未实际验证业务结果。",
            }
        )
        evidence.extend(a.text.strip() for a in constant_bools[:2])
        suggestions.append("移除常量布尔断言，改为断言真实业务表达式")

    # Signal 3: 仅 verify
    if has_verify and not has_strong and not weak_asserts:
        signals.append(
            {
                "code": "VERIFY_ONLY_NO_BUSINESS_ASSERT",
                "severity": "high",
                "reason": "仅做交互校验 (verify)，未看到业务结果断言。",
            }
        )
        evidence.extend(v.text.strip() for v in effective_verify[:2])
        suggestions.append("在 verify 之外补充业务结果或副作用断言")

    # Signal 4: assertThrows 无后续效果断言
    throws_asserts = [a for a in effective_asserts if a.kind == "assertThrows"]
    if throws_asserts:
        throws_var = find_throws_variable(method)
        has_effect = any(a for a in strong_asserts if not throws_var or throws_var not in a.text)
        if not has_effect:
            signals.append(
                {
                    "code": "ASSERT_THROWS_NO_EFFECT_ASSERT",
                    "severity": "medium",
                    "reason": "只校验抛异常，缺少失败后的业务效果断言。",
                }
            )
            evidence.extend(a.text.strip() for a in throws_asserts[:1])
            suggestions.append("补充失败后的状态、数据或副作用断言")

    # Signal 5: 断言数量过少
    total_asserts = len(effective_asserts) + len(effective_verify)
    method_lines = len(method.content.splitlines())
    if total_asserts <= 1 and method_lines > 15 and not signals:
        signals.append(
            {
                "code": "INSUFFICIENT_ASSERTIONS",
                "severity": "medium",
                "reason": f"方法体 {method_lines} 行但仅 {total_asserts} 个断言，可能遗漏关键验证。",
            }
        )
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
