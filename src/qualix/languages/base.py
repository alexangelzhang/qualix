"""LanguageProvider 抽象基类 + 共享数据类型.

每种语言实现一个 Provider，覆盖 DQG 质量门控的全部语言特定能力。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from qualix.context.code_skeleton import SkeletonResult

# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


class Strength(Enum):
    """断言强度."""

    STRONG = "strong"
    WEAK = "weak"
    TRIVIAL = "trivial"


@dataclass
class AssertionInfo:
    """一次断言调用."""

    kind: str  # toBe, assertEquals, assertNotNull, ...
    line: int  # 行号 (0-based)
    text: str  # 原始代码文本
    strength: Strength
    args: list[str] = field(default_factory=list)


@dataclass
class MockInfo:
    """一次 mock 使用."""

    kind: str  # jest.mock, jest.spyOn, Mockito.mock, ...
    line: int
    text: str
    target: str = ""  # 被 mock 的模块/类


@dataclass
class TestMethodInfo:
    """一个测试方法的分析结果."""

    name: str
    line_start: int  # 1-based
    line_end: int  # 1-based
    content: str
    assertions: list[AssertionInfo] = field(default_factory=list)
    verify_calls: list[AssertionInfo] = field(default_factory=list)
    helper_calls: list[str] = field(default_factory=list)


@dataclass
class WeakAssertSignalInfo:
    """弱断言信号."""

    code: str  # ASSERT_NOT_NULL_ONLY, EXPECT_DEFINED_ONLY, ...
    severity: str  # high, medium
    reason: str


@dataclass
class WeakAssertResult:
    """单个测试方法的弱断言分析结果."""

    method_name: str
    line_start: int
    line_end: int
    risk_level: str  # high, medium, ""
    signals: list[WeakAssertSignalInfo] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""
    assert_summary: dict[str, int] = field(default_factory=dict)


@dataclass
class TestFrameworkInfo:
    """测试框架信息."""

    name: str  # jest, vitest, junit5, pytest, go-test, ...
    version: str = ""
    config_file: str = ""  # jest.config.ts, vitest.config.ts, ...


@dataclass
class CompileResult:
    """编译/类型检查结果."""

    passed: bool
    build_tool: str = ""
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    error_summary: str = ""
    skipped: bool = False  # 动态语言可跳过


@dataclass
class LintResult:
    """Lint 检查结果."""

    passed: bool
    tool: str = ""  # eslint, ruff, clippy, ...
    command: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False


@dataclass
class SourceInfo:
    """源文件解析结果."""

    functions: list[dict[str, Any]] = field(default_factory=list)
    classes: list[dict[str, Any]] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class TestGenContext:
    """为 LLM 提供的语言特定生成上下文."""

    language: str
    test_framework: str
    assertion_style: str  # expect-chain, assert-method, ...
    mock_library: str = ""
    example_test: str = ""  # 示例测试代码片段
    conventions: list[str] = field(default_factory=list)


@dataclass
class CoverageResult:
    """覆盖率结果."""

    line_coverage: float = 0.0
    branch_coverage: float = 0.0
    statement_coverage: float = 0.0
    raw_report: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class LanguageProvider(ABC):
    """语言 Provider — 覆盖 DQG 质量门控的全部语言特定能力."""

    @property
    @abstractmethod
    def language_id(self) -> str:
        """语言标识符: 'java', 'typescript', 'go', 'python', 'rust'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称: 'Java', 'TypeScript', 'Go', 'Python', 'Rust'."""

    # ── 检测 ──

    @abstractmethod
    def detect(self, repo_root: Path) -> float:
        """返回置信度 0~1（支持 monorepo 多语言共存）."""

    @abstractmethod
    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        """识别测试框架。Go/Rust 内置测试返回固定值."""

    def resolve_test_dependencies(self, repo_root: Path) -> list[str]:
        """解析测试相关依赖（testify, mockall, pytest 等）.

        默认返回空列表，子类按需覆盖。
        """
        return []

    # ── 质量门控 ──

    @abstractmethod
    def compile_check(self, repo_root: Path, module: str | None = None) -> CompileResult:
        """编译/类型检查。动态语言可返回 CompileResult(skipped=True)."""

    def lint_check(self, repo_root: Path) -> LintResult:
        """Lint 检查。默认跳过，子类按需覆盖."""
        return LintResult(passed=True, skipped=True)

    # ── AST 分析 ──

    def parse_source(self, source_code: str) -> SourceInfo:
        """解析源文件：函数签名、类/struct、export、依赖.

        默认返回空 SourceInfo，子类按需覆盖。
        """
        return SourceInfo()

    def extract_skeleton(
        self,
        source: str,
        expand_methods: set[str] | None = None,
    ) -> SkeletonResult | None:
        """提取代码骨架：保留签名+字段，省略方法体.

        expand_methods 中的方法展开完整实现（Oracle 标注）。
        不支持的语言返回 None。默认返回 None，子类按需覆盖。
        """
        return None

    @abstractmethod
    def parse_test_methods(self, test_content: str) -> list[TestMethodInfo]:
        """从测试文件内容中提取测试方法及其断言."""

    @abstractmethod
    def classify_assertion_strength(self, assertion_kind: str, args: list[str]) -> Strength:
        """断言强度分类: strong / weak / trivial."""

    def detect_mock_patterns(self, test_content: str) -> list[MockInfo]:
        """检测 mock 使用模式。默认返回空列表."""
        return []

    # ── 弱断言分析（高层接口）──

    @abstractmethod
    def analyze_weak_asserts(self, test_content: str) -> list[WeakAssertResult]:
        """完整弱断言分析 — Pipeline 主要调用入口.

        内部调用 parse_test_methods + classify_assertion_strength，
        产出与现有 analyze_with_ast / analyze_test_method 兼容的结果。
        """

    # ── 测试文件定位 ──

    @abstractmethod
    def test_file_pattern(self) -> str:
        """glob 模式: '*_test.go', '*.test.ts', 'test_*.py'."""

    def locate_test_file(self, source_file: Path) -> Path | None:
        """给定源文件，返回对应测试文件的期望路径.

        默认返回 None（无法推断），子类按需覆盖。
        """
        return None

    # ── 生成上下文 ──

    def get_test_gen_context(self, source_file: Path) -> TestGenContext:
        """为 LLM 提供语言特定的生成上下文.

        默认返回基础信息，子类按需覆盖。
        """
        return TestGenContext(
            language=self.language_id,
            test_framework="",
            assertion_style="",
        )

    def get_skill_overrides(self) -> dict[str, Any]:
        """对 skill prompt 的语言特定覆盖。默认无覆盖."""
        return {}

    # ── 覆盖率 ──

    def run_coverage(self, repo_root: Path) -> CoverageResult | None:
        """执行覆盖率收集。不支持则返回 None."""
        return None

    # ── 文件过滤 ──

    def is_source_file(self, file_path: str) -> bool:
        """判断是否为该语言的源文件."""
        return file_path.endswith(self._source_extensions())

    def is_test_file(self, file_path: str) -> bool:
        """判断是否为该语言的测试文件."""
        return self.is_source_file(file_path) and self._matches_test_pattern(file_path)

    def _source_extensions(self) -> tuple[str, ...]:
        """源文件扩展名。子类应覆盖."""
        return ()

    def _matches_test_pattern(self, file_path: str) -> bool:
        """测试文件名模式匹配。子类应覆盖."""
        return False
