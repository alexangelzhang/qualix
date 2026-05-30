"""DQG 多语言支持 — LanguageProvider 抽象层.

用法::

    from qualix.languages import get_registry

    registry = get_registry()
    provider = registry.detect(repo_root)  # 自动检测
    provider = registry.get("typescript")  # 按 ID 获取
"""

from qualix.languages.base import (
    AssertionInfo,
    CompileResult,
    CoverageResult,
    LanguageProvider,
    LintResult,
    MockInfo,
    SourceInfo,
    Strength,
    TestFrameworkInfo,
    TestGenContext,
    TestMethodInfo,
    WeakAssertResult,
    WeakAssertSignalInfo,
)
from qualix.languages.registry import LanguageRegistry, get_registry

__all__ = [
    # Data types
    "AssertionInfo",
    "CompileResult",
    "CoverageResult",
    # ABC
    "LanguageProvider",
    # Registry
    "LanguageRegistry",
    "LintResult",
    "MockInfo",
    "SourceInfo",
    "Strength",
    "TestFrameworkInfo",
    "TestGenContext",
    "TestMethodInfo",
    "WeakAssertResult",
    "WeakAssertSignalInfo",
    "get_registry",
]
