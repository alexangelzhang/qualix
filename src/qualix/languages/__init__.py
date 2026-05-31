"""Qualix 多语言支持 — LanguageProvider 抽象层.

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

try:
    from qualix.languages.go.provider import GoProvider
    from qualix.languages.python.provider import PythonProvider
    from qualix.languages.typescript.provider import TypeScriptProvider
except ImportError:  # pragma: no cover - optional import surface
    GoProvider = None  # type: ignore[assignment]
    PythonProvider = None  # type: ignore[assignment]
    TypeScriptProvider = None  # type: ignore[assignment]

__all__ = [
    "AssertionInfo",
    "CompileResult",
    "CoverageResult",
    "GoProvider",
    "LanguageProvider",
    "LanguageRegistry",
    "LintResult",
    "MockInfo",
    "PythonProvider",
    "SourceInfo",
    "Strength",
    "TestFrameworkInfo",
    "TestGenContext",
    "TestMethodInfo",
    "TypeScriptProvider",
    "WeakAssertResult",
    "WeakAssertSignalInfo",
    "get_registry",
]
