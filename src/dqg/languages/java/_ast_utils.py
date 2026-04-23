"""Java AST 遍历工具函数.

从 ast_analyzer.py 拆分，提供 tree-sitter 节点遍历、
方法体分析、变量追踪等底层能力。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dqg.languages.java.ast_analyzer import TestMethod


def iter_nodes(node: Any, node_type: str):
    """递归遍历 AST，yield 所有指定类型的节点."""
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from iter_nodes(child, node_type)


def find_child(node: Any, child_type: str) -> Any:
    """查找第一个指定类型的子节点."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def get_child_text(node: Any, child_type: str, source: bytes) -> str:
    """获取指定类型子节点的文本."""
    child = find_child(node, child_type)
    if child:
        return source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
    return ""


def has_test_annotation(method_node: Any) -> bool:
    """检查方法是否有 @Test 等测试注解."""
    modifiers = find_child(method_node, "modifiers")
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


def analyze_method_body(
    body_node: Any,
    source: bytes,
    method: TestMethod,
    assert_methods: frozenset[str],
    strong_methods: frozenset[str],
    constant_booleans: frozenset[str],
) -> None:
    """分析方法体中的断言、verify、变量赋值、helper 调用."""
    for node in iter_nodes(body_node, "expression_statement"):
        expr = node.children[0] if node.children else None
        if not expr:
            continue
        _analyze_expression(expr, source, method, assert_methods, strong_methods, constant_booleans)

    # 变量赋值追踪
    for node in iter_nodes(body_node, "local_variable_declaration"):
        _track_variable(node, source, method)


def _analyze_expression(
    expr: Any,
    source: bytes,
    method: TestMethod,
    assert_methods: frozenset[str],
    strong_methods: frozenset[str],
    constant_booleans: frozenset[str],
) -> None:
    """分析单个表达式：断言调用、verify 调用、helper 调用."""
    from dqg.languages.java.ast_analyzer import AssertCall

    text = source[expr.start_byte : expr.end_byte].decode("utf-8", errors="replace")
    line = expr.start_point[0]

    if expr.type == "method_invocation":
        method_name = get_invocation_name(expr, source)
        args = get_invocation_args(expr, source)

        if _chain_contains_verify(expr, source):
            method.verify_calls.append(
                AssertCall(
                    kind="verify",
                    line=line,
                    text=text,
                    is_strong=False,
                    args=args,
                )
            )
            return

        if method_name in assert_methods:
            is_strong = method_name in strong_methods
            if method_name in ("assertTrue", "assertFalse") and args and args[0].strip() not in constant_booleans:
                is_strong = True
            method.asserts.append(
                AssertCall(
                    kind=method_name,
                    line=line,
                    text=text,
                    is_strong=is_strong,
                    args=args,
                )
            )
        elif method_name == "verify":
            method.verify_calls.append(
                AssertCall(
                    kind="verify",
                    line=line,
                    text=text,
                    is_strong=False,
                    args=args,
                )
            )
        elif method_name == "assertThat":
            method.asserts.append(
                AssertCall(
                    kind="assertThat",
                    line=line,
                    text=text,
                    is_strong=True,
                    args=args,
                )
            )
        elif not method_name.startswith("assert") and method_name != "verify":
            method.helper_calls.append(method_name)


def get_invocation_name(node: Any, source: bytes) -> str:
    """获取方法调用的方法名."""
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
    if node.children and node.children[0].type == "method_invocation":
        return get_invocation_name(node.children[0], source)
    return ""


def _chain_contains_verify(node: Any, source: bytes) -> bool:
    """检查链式调用中是否包含 verify."""
    if node.type == "method_invocation":
        name = ""
        for child in node.children:
            if child.type == "identifier":
                name = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
                break
        if name == "verify":
            return True
        for child in node.children:
            if child.type == "method_invocation" and _chain_contains_verify(child, source):
                return True
    return False


def get_invocation_args(node: Any, source: bytes) -> list[str]:
    """获取方法调用的参数列表."""
    args_node = find_child(node, "argument_list")
    if not args_node:
        return []
    args: list[str] = []
    for child in args_node.children:
        if child.type not in ("(", ")", ","):
            args.append(source[child.start_byte : child.end_byte].decode("utf-8", errors="replace"))
    return args


def _track_variable(node: Any, source: bytes, method: TestMethod) -> None:
    """追踪局部变量赋值."""
    declarator = find_child(node, "variable_declarator")
    if not declarator:
        return
    name_node = find_child(declarator, "identifier")
    if not name_node:
        return
    var_name = source[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace")
    for child in declarator.children:
        if child.type not in ("identifier", "="):
            assigned_from = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
            method.local_vars[var_name] = assigned_from
            break


def find_throws_variable(method: TestMethod) -> str | None:
    """查找 assertThrows 返回值的变量名."""
    for var_name, assigned_from in method.local_vars.items():
        if "assertThrows" in assigned_from:
            return var_name
    return None
