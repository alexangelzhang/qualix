"""TypeScript AST 分析器：基于 tree-sitter 的 expect() 链式调用解析.

解析 Jest/Vitest 的 expect(x).toXxx(y) 模式，
提取测试方法、断言、mock 使用。
"""

from __future__ import annotations

from typing import Any

from qualix.languages.base import AssertionInfo, MockInfo, TestMethodInfo
from qualix.languages.typescript.assertions import (
    MOCK_PATTERNS,
    classify_ts_assertion,
)
from qualix.log import get_logger

log = get_logger(__name__)

_ts_available: bool | None = None
_parser: Any = None


def _ensure_parser() -> bool:
    """懒加载 tree-sitter TypeScript parser."""
    global _ts_available, _parser
    if _ts_available is not None:
        return _ts_available
    try:
        import tree_sitter_typescript as ts_ts
        from tree_sitter import Language, Parser

        lang = Language(ts_ts.language_typescript())
        _parser = Parser(lang)
        _ts_available = True
    except ImportError:
        _ts_available = False
        log.debug("tree-sitter-typescript not available")
    return _ts_available


def is_available() -> bool:
    """tree-sitter TypeScript 是否可用."""
    return _ensure_parser()


def parse_typescript(source: bytes | str) -> Any:
    """解析 TypeScript 源码，返回 tree-sitter 根节点."""
    if not _ensure_parser():
        return None
    if isinstance(source, str):
        source = source.encode("utf-8")
    tree = _parser.parse(source)
    return tree.root_node


# ---------------------------------------------------------------------------
# 测试方法提取
# ---------------------------------------------------------------------------


def extract_test_methods(root_node: Any, source: bytes) -> list[TestMethodInfo]:
    """提取 it()/test() 块中的测试方法."""
    methods: list[TestMethodInfo] = []
    for node in _iter_nodes(root_node, "call_expression"):
        fn_name = _get_test_call_name(node, source)
        if fn_name not in ("it", "test", "it.only", "test.only", "it.skip", "test.skip"):
            continue

        args_node = _find_child(node, "arguments")
        if not args_node:
            continue

        # 第一个参数是测试名
        test_name = _get_first_string_arg(args_node, source)
        if not test_name:
            continue

        # 第二个参数是回调函数
        callback = _find_callback(args_node)
        if not callback:
            continue

        content = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        method = TestMethodInfo(
            name=test_name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            content=content,
        )

        # 分析回调体中的断言
        body = _find_child(callback, "statement_block")
        if body:
            _analyze_body(body, source, method)

        methods.append(method)
    return methods


# ---------------------------------------------------------------------------
# Mock 检测
# ---------------------------------------------------------------------------


def extract_mock_patterns(root_node: Any, source: bytes) -> list[MockInfo]:
    """检测 jest.mock/vi.mock/jest.spyOn 等 mock 使用."""
    mocks: list[MockInfo] = []
    for node in _iter_nodes(root_node, "call_expression"):
        member = _find_child(node, "member_expression")
        if not member:
            continue
        text = source[member.start_byte : member.end_byte].decode("utf-8", errors="replace")
        if text not in MOCK_PATTERNS:
            continue

        args_node = _find_child(node, "arguments")
        target = _get_first_string_arg(args_node, source) if args_node else ""
        full_text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        mocks.append(
            MockInfo(
                kind=text,
                line=node.start_point[0],
                text=full_text,
                target=target,
            )
        )
    return mocks


# ---------------------------------------------------------------------------
# 内部：断言提取
# ---------------------------------------------------------------------------


def _analyze_body(body_node: Any, source: bytes, method: TestMethodInfo) -> None:
    """分析函数体中的 expect() 链式调用."""
    for node in _iter_nodes(body_node, "call_expression"):
        result = _parse_expect_chain(node, source)
        if result:
            method.assertions.append(result)


def _parse_expect_chain(node: Any, source: bytes) -> AssertionInfo | None:
    """解析 expect(x).toXxx(y) 链式调用.

    AST 结构:
      call_expression          ← toXxx(y)
        member_expression      ← expect(x).toXxx
          call_expression      ← expect(x)
            identifier         ← expect
            arguments          ← (x)
          property_identifier  ← toXxx
        arguments              ← (y)
    """
    member = _find_child(node, "member_expression")
    if not member:
        return None

    # 找 property_identifier (matcher 名)
    matcher_name = ""
    for child in member.children:
        if child.type == "property_identifier":
            matcher_name = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")

    if not matcher_name:
        return None

    # 找内层 call_expression (expect(...))
    inner_call = _find_child(member, "call_expression")
    if not inner_call:
        return None

    # 确认是 expect()
    fn_id = _find_child(inner_call, "identifier")
    if not fn_id:
        return None
    fn_name = source[fn_id.start_byte : fn_id.end_byte].decode("utf-8", errors="replace")
    if fn_name != "expect":
        return None

    # expect 参数
    expect_args_node = _find_child(inner_call, "arguments")
    expect_arg = _get_args_text(expect_args_node, source)[0] if expect_args_node else ""

    # matcher 参数
    matcher_args_node = _find_child(node, "arguments")
    matcher_args = _get_args_text(matcher_args_node, source) if matcher_args_node else []

    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    strength = classify_ts_assertion(matcher_name, expect_arg, matcher_args)

    return AssertionInfo(
        kind=matcher_name,
        line=node.start_point[0],
        text=text,
        strength=strength,
        args=matcher_args,
    )


# ---------------------------------------------------------------------------
# AST 遍历工具
# ---------------------------------------------------------------------------


def _iter_nodes(node: Any, node_type: str):
    """递归遍历 AST."""
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from _iter_nodes(child, node_type)


def _find_child(node: Any, child_type: str) -> Any:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _get_test_call_name(node: Any, source: bytes) -> str:
    """获取 it/test/it.only 等调用名."""
    first = node.children[0] if node.children else None
    if not first:
        return ""
    if first.type == "identifier":
        return source[first.start_byte : first.end_byte].decode("utf-8", errors="replace")
    if first.type == "member_expression":
        return source[first.start_byte : first.end_byte].decode("utf-8", errors="replace")
    return ""


def _get_first_string_arg(args_node: Any, source: bytes) -> str:
    """获取参数列表中第一个字符串参数的值."""
    for child in args_node.children:
        if child.type == "string":
            # 去掉引号
            raw = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
            return raw.strip("'\"`")
        if child.type == "template_string":
            raw = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
            return raw.strip("`")
    return ""


def _find_callback(args_node: Any) -> Any:
    """在参数列表中找到回调函数（arrow_function 或 function_expression）."""
    for child in args_node.children:
        if child.type in ("arrow_function", "function_expression", "function"):
            return child
    return None


def _get_args_text(args_node: Any, source: bytes) -> list[str]:
    """获取参数列表中各参数的文本."""
    if not args_node:
        return []
    args: list[str] = []
    for child in args_node.children:
        if child.type not in ("(", ")", ","):
            args.append(source[child.start_byte : child.end_byte].decode("utf-8", errors="replace"))
    return args
