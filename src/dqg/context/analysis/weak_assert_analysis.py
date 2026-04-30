"""弱断言静态分析：正则匹配 + tree-sitter AST 桥接.

从 weak_assert_context.py 拆分而来，负责：
1. 正则模式定义（断言类型识别）
2. 测试方法提取（正则 fallback）
3. 断言强度分析
4. tree-sitter AST 分析桥接
"""

from __future__ import annotations

import re
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# 尝试导入 AST 分析器
try:
    from .java_ast_analyzer import (
        analyze_assert_strength,
        extract_helper_methods,
        extract_test_methods,
        parse_java,
    )
    from .java_ast_analyzer import (
        is_available as _ast_available,
    )
except ImportError:
    _ast_available = lambda: False  # noqa: E731

_TEST_ANNOTATION_PATTERN = re.compile(
    r"^\s*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b",
    re.MULTILINE,
)
_METHOD_NAME_PATTERN = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:throws[^{]+)?\{",
    re.MULTILINE,
)
_ASSERT_NOT_NULL_PATTERN = re.compile(r"\bassertNotNull\s*\(")
_CONSTANT_BOOL_ASSERT_PATTERN = re.compile(
    r"\bassert(?:True|False)\s*\(\s*(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\)"
)
_VERIFY_PATTERN = re.compile(r"\bverify\s*\(")
_TIMES_PATTERN = re.compile(r"\btimes\s*\(")
_ASSERT_THROWS_PATTERN = re.compile(r"\bassertThrows\s*\(")
_EXCEPTION_ASSIGN_PATTERN = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*assertThrows\s*\(")
_ASSERT_THAT_PATTERN = re.compile(r"\bassertThat\s*\(")
_NON_CONSTANT_BOOL_ASSERT_PATTERN = re.compile(
    r"\bassert(?:True|False)\s*\(\s*(?!(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\))"
)
_STRONG_ASSERT_PATTERN = re.compile(
    r"\bassert(?:Equals|NotEquals|Same|NotSame|ArrayEquals|IterableEquals|LinesMatch|Null|DoesNotThrow|All)\s*\("
)


class WeakAssertSignal:
    ASSERT_NOT_NULL_ONLY = "ASSERT_NOT_NULL_ONLY"
    CONSTANT_BOOLEAN_ASSERT = "CONSTANT_BOOLEAN_ASSERT"
    VERIFY_ONLY_NO_BUSINESS_ASSERT = "VERIFY_ONLY_NO_BUSINESS_ASSERT"
    ASSERT_THROWS_NO_EFFECT_ASSERT = "ASSERT_THROWS_NO_EFFECT_ASSERT"


def is_ast_available() -> bool:
    return _ast_available()


def extract_test_methods_regex(content: str) -> list[dict[str, Any]]:
    """正则提取测试方法."""
    lines = content.splitlines()
    methods: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        if not _TEST_ANNOTATION_PATTERN.match(lines[index]):
            index += 1
            continue

        annotation_start = index
        search_index = index + 1
        while search_index < len(lines):
            stripped = lines[search_index].strip()
            if not stripped or stripped.startswith("@"):
                search_index += 1
                continue
            break

        signature_lines: list[str] = []
        while search_index < len(lines):
            signature_lines.append(lines[search_index])
            if "{" in lines[search_index]:
                break
            search_index += 1

        if search_index >= len(lines):
            break

        signature_text = "\n".join(signature_lines)
        match = _METHOD_NAME_PATTERN.search(signature_text)
        if not match:
            index = search_index + 1
            continue

        method_name = match.group("name")
        brace_depth = lines[search_index].count("{") - lines[search_index].count("}")
        body_end = search_index
        while body_end + 1 < len(lines) and brace_depth > 0:
            body_end += 1
            brace_depth += lines[body_end].count("{") - lines[body_end].count("}")

        methods.append(
            {
                "method_name": method_name,
                "line_start": annotation_start + 1,
                "line_end": body_end + 1,
                "content": "\n".join(lines[annotation_start : body_end + 1]),
            }
        )
        index = body_end + 1

    return methods


def analyze_test_method(method: dict[str, Any]) -> dict[str, Any]:
    """分析单个测试方法的断言强度."""
    content = method["content"]
    method_lines = _normalized_lines(content)
    not_null_lines = _matching_lines(method_lines, _ASSERT_NOT_NULL_PATTERN)
    constant_bool_lines = _matching_lines(method_lines, _CONSTANT_BOOL_ASSERT_PATTERN)
    verify_lines = _matching_lines(method_lines, _VERIFY_PATTERN)
    if _TIMES_PATTERN.search(content) and not verify_lines:
        verify_lines = _matching_lines(method_lines, _TIMES_PATTERN)
    strong_assert = _strong_assert_lines(method_lines)

    signals: list[dict[str, str]] = []
    evidence: list[str] = []
    suggestion_parts: list[str] = []

    if not_null_lines and not strong_assert and not verify_lines and not _ASSERT_THROWS_PATTERN.search(content):
        signals.append(
            {
                "code": WeakAssertSignal.ASSERT_NOT_NULL_ONLY,
                "severity": "high",
                "reason": "仅看到 assertNotNull，未验证业务字段、状态或副作用。",
            }
        )
        evidence.extend(not_null_lines[:2])
        suggestion_parts.append("补充关键业务字段、状态迁移或副作用断言")

    if constant_bool_lines and not strong_assert:
        signals.append(
            {
                "code": WeakAssertSignal.CONSTANT_BOOLEAN_ASSERT,
                "severity": "high",
                "reason": "存在常量布尔断言，未实际验证业务结果。",
            }
        )
        evidence.extend(constant_bool_lines[:2])
        suggestion_parts.append("移除常量布尔断言，改为断言真实业务表达式")

    if verify_lines and not strong_assert:
        signals.append(
            {
                "code": WeakAssertSignal.VERIFY_ONLY_NO_BUSINESS_ASSERT,
                "severity": "high",
                "reason": "仅做交互校验，未看到业务结果断言。",
            }
        )
        evidence.extend(verify_lines[:2])
        suggestion_parts.append("在 verify 之外补充业务结果或副作用断言")

    if _ASSERT_THROWS_PATTERN.search(content) and _has_assert_throws_without_effect(content, method_lines):
        signals.append(
            {
                "code": WeakAssertSignal.ASSERT_THROWS_NO_EFFECT_ASSERT,
                "severity": "medium",
                "reason": "只校验抛异常或异常对象，缺少失败后的业务效果断言。",
            }
        )
        evidence.extend(_matching_lines(method_lines, _ASSERT_THROWS_PATTERN)[:1])
        suggestion_parts.append("补充失败后的状态、数据或副作用断言")

    deduped_evidence = list(dict.fromkeys(evidence))
    suggestion = "；".join(dict.fromkeys(suggestion_parts)) if suggestion_parts else ""

    return {
        "method_name": method["method_name"],
        "line_start": method["line_start"],
        "line_end": method["line_end"],
        "risk_level": _risk_level_for_signals(signals),
        "signals": signals,
        "evidence": deduped_evidence[:4],
        "suggestion": suggestion,
    }


def _has_assert_throws_without_effect(content: str, method_lines: list[str]) -> bool:
    exception_vars = set(_EXCEPTION_ASSIGN_PATTERN.findall(content))
    business_effect_lines = []
    for line in _strong_assert_lines(method_lines):
        if exception_vars and any(re.search(rf"\\b{re.escape(name)}\\b", line) for name in exception_vars):
            continue
        business_effect_lines.append(line)
    return not business_effect_lines


def _strong_assert_lines(method_lines: list[str]) -> list[str]:
    strong: list[str] = []
    for line in method_lines:
        if _ASSERT_NOT_NULL_PATTERN.search(line):
            continue
        if _CONSTANT_BOOL_ASSERT_PATTERN.search(line):
            continue
        if _ASSERT_THAT_PATTERN.search(line):
            strong.append(line)
            continue
        if _NON_CONSTANT_BOOL_ASSERT_PATTERN.search(line):
            strong.append(line)
            continue
        if _STRONG_ASSERT_PATTERN.search(line):
            strong.append(line)
    return strong


def _matching_lines(lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    return [line for line in lines if pattern.search(line)]


def _normalized_lines(content: str) -> list[str]:
    normalized: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue
        normalized.append(line)
    return normalized


def _risk_level_for_signals(signals: list[dict[str, str]]) -> str:
    if not signals:
        return ""
    if any(signal["severity"] == "high" for signal in signals):
        return "high"
    return "medium"


def analyze_with_ast(content: str) -> list[dict[str, Any]]:
    """使用 tree-sitter Java AST 分析测试方法的断言强度（含跨方法分析）."""
    source = content.encode("utf-8")
    root = parse_java(source)
    if root is None:
        log.warning("tree-sitter parse failed, falling back to regex")
        methods = extract_test_methods_regex(content)
        return [analyze_test_method(m) for m in methods]

    test_methods = extract_test_methods(root, source)
    helpers = extract_helper_methods(root, source)

    results: list[dict[str, Any]] = []
    for method in test_methods:
        analysis = analyze_assert_strength(method, helpers=helpers)
        if analysis["signals"]:
            results.append(analysis)
    return results
