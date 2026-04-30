"""Java AST 分析器 — facade re-export.

实际实现已迁移到 dqg.languages.java.ast_analyzer。
本文件保留向后兼容，所有现有 import 无需改动。
"""

from dqg.languages.java.ast_analyzer import (
    AssertCall,
    TestMethod,
    _ensure_parser,
    _parser,
    analyze_assert_strength,
    extract_helper_methods,
    extract_test_methods,
    is_available,
    parse_java,
)

__all__ = [
    "AssertCall",
    "TestMethod",
    "_ensure_parser",
    "_parser",
    "analyze_assert_strength",
    "extract_helper_methods",
    "extract_test_methods",
    "is_available",
    "parse_java",
]
