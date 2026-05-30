"""JavaProvider — DQG Java 语言支持.

整合 AST 分析、断言强度映射、编译检查、弱断言检测。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qualix.context.code_skeleton import SkeletonResult

from qualix.languages.base import (
    CompileResult,
    LanguageProvider,
    Strength,
    TestFrameworkInfo,
    TestMethodInfo,
    WeakAssertResult,
    WeakAssertSignalInfo,
)
from qualix.languages.java.assertions import classify_java_assertion
from qualix.log import get_logger

log = get_logger(__name__)

_COMPILE_TIMEOUT = 120


class JavaProvider(LanguageProvider):
    """Java 语言 Provider."""

    @property
    def language_id(self) -> str:
        return "java"

    @property
    def display_name(self) -> str:
        return "Java"

    # ── 检测 ──

    def detect(self, repo_root: Path) -> float:
        if (repo_root / "pom.xml").exists():
            return 0.9
        if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
            return 0.9
        # 有 .java 文件但无构建文件
        if any(repo_root.rglob("*.java")):
            return 0.5
        return 0.0

    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        # 检查 pom.xml 或 build.gradle 中的 junit 依赖
        pom = repo_root / "pom.xml"
        if pom.exists():
            content = pom.read_text(encoding="utf-8", errors="replace")
            if "junit-jupiter" in content or "junit5" in content.lower():
                return TestFrameworkInfo(name="junit5")
            if "junit" in content.lower():
                return TestFrameworkInfo(name="junit4")
        for gradle_file in ("build.gradle", "build.gradle.kts"):
            gf = repo_root / gradle_file
            if gf.exists():
                content = gf.read_text(encoding="utf-8", errors="replace")
                if "junit-jupiter" in content or "junit5" in content.lower():
                    return TestFrameworkInfo(name="junit5")
                if "junit" in content.lower():
                    return TestFrameworkInfo(name="junit4")
        return None

    # ── 质量门控 ──

    def compile_check(self, repo_root: Path, module: str | None = None) -> CompileResult:
        build_tool = self._detect_build_tool(repo_root)
        if not build_tool:
            return CompileResult(passed=True, skipped=True, error_summary="未检测到 Java 构建工具")

        cmd = self._build_compile_command(build_tool, module)
        log.info("编译检查: %s (cwd=%s)", cmd, repo_root)

        try:
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT,
                shell=True,
            )
            passed = result.returncode == 0
            error_summary = ""
            if not passed:
                error_summary = self._extract_compile_errors(result.stderr + result.stdout)
            return CompileResult(
                passed=passed,
                build_tool=build_tool,
                command=cmd,
                stdout=result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                stderr=result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
                error_summary=error_summary,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                passed=False,
                build_tool=build_tool,
                command=cmd,
                error_summary=f"编译超时（>{_COMPILE_TIMEOUT}s）",
            )
        except Exception as exc:
            return CompileResult(
                passed=False,
                build_tool=build_tool,
                command=cmd,
                stderr=str(exc),
                error_summary=f"编译执行异常: {exc}",
            )

    # ── AST 分析 ──

    def parse_test_methods(self, test_content: str) -> list[TestMethodInfo]:
        from qualix.languages.java.ast_analyzer import (
            extract_test_methods,
            is_available,
            parse_java,
        )

        if not is_available():
            return []

        source = test_content.encode("utf-8")
        root = parse_java(source)
        if root is None:
            return []

        raw_methods = extract_test_methods(root, source)
        result: list[TestMethodInfo] = []
        for m in raw_methods:
            from qualix.languages.base import AssertionInfo

            assertions = []
            for a in m.asserts:
                assertions.append(
                    AssertionInfo(
                        kind=a.kind,
                        line=a.line,
                        text=a.text,
                        strength=classify_java_assertion(a.kind, a.args),
                        args=a.args,
                    )
                )
            verify_calls = []
            for v in m.verify_calls:
                verify_calls.append(
                    AssertionInfo(
                        kind=v.kind,
                        line=v.line,
                        text=v.text,
                        strength=Strength.WEAK,
                        args=v.args,
                    )
                )
            result.append(
                TestMethodInfo(
                    name=m.name,
                    line_start=m.line_start,
                    line_end=m.line_end,
                    content=m.content,
                    assertions=assertions,
                    verify_calls=verify_calls,
                    helper_calls=m.helper_calls,
                )
            )
        return result

    def classify_assertion_strength(self, assertion_kind: str, args: list[str]) -> Strength:
        return classify_java_assertion(assertion_kind, args)

    # ── 弱断言分析 ──

    def analyze_weak_asserts(self, test_content: str) -> list[WeakAssertResult]:
        """完整弱断言分析 — 委托给现有 AST 分析器."""
        from qualix.languages.java.ast_analyzer import (
            analyze_assert_strength,
            extract_helper_methods,
            extract_test_methods,
            is_available,
            parse_java,
        )

        if not is_available():
            return self._analyze_weak_asserts_regex(test_content)

        source = test_content.encode("utf-8")
        root = parse_java(source)
        if root is None:
            return self._analyze_weak_asserts_regex(test_content)

        test_methods = extract_test_methods(root, source)
        helpers = extract_helper_methods(root, source)

        results: list[WeakAssertResult] = []
        for method in test_methods:
            analysis = analyze_assert_strength(method, helpers=helpers)
            if analysis["signals"]:
                results.append(
                    WeakAssertResult(
                        method_name=analysis["method_name"],
                        line_start=analysis["line_start"],
                        line_end=analysis["line_end"],
                        risk_level=analysis["risk_level"],
                        signals=[
                            WeakAssertSignalInfo(
                                code=s["code"],
                                severity=s["severity"],
                                reason=s["reason"],
                            )
                            for s in analysis["signals"]
                        ],
                        evidence=analysis.get("evidence", []),
                        suggestion=analysis.get("suggestion", ""),
                        assert_summary=analysis.get("assert_summary", {}),
                    )
                )
        return results

    def _analyze_weak_asserts_regex(self, test_content: str) -> list[WeakAssertResult]:
        """Regex fallback — 委托给现有正则分析."""
        from qualix.context.weak_assert_analysis import (
            analyze_test_method,
            extract_test_methods_regex,
        )

        methods = extract_test_methods_regex(test_content)
        results: list[WeakAssertResult] = []
        for m in methods:
            analysis = analyze_test_method(m)
            if analysis["signals"]:
                results.append(
                    WeakAssertResult(
                        method_name=analysis["method_name"],
                        line_start=analysis["line_start"],
                        line_end=analysis["line_end"],
                        risk_level=analysis["risk_level"],
                        signals=[
                            WeakAssertSignalInfo(
                                code=s["code"],
                                severity=s["severity"],
                                reason=s["reason"],
                            )
                            for s in analysis["signals"]
                        ],
                        evidence=analysis.get("evidence", []),
                        suggestion=analysis.get("suggestion", ""),
                    )
                )
        return results

    # ── 骨架提取 ──

    def extract_skeleton(
        self,
        source: str,
        expand_methods: set[str] | None = None,
    ) -> SkeletonResult | None:
        """Extract Java code skeleton using tree-sitter (regex fallback)."""
        from qualix.context.code_skeleton import extract_skeleton

        return extract_skeleton(source, expand_methods)

    # ── 测试文件定位 ──

    def test_file_pattern(self) -> str:
        return "**/*Test.java"

    def locate_test_file(self, source_file: Path) -> Path | None:
        # src/main/java/com/foo/Bar.java → src/test/java/com/foo/BarTest.java
        parts = source_file.parts
        if "main" in parts:
            idx = parts.index("main")
            test_parts = (*parts[:idx], "test", *parts[idx + 1 :])
            test_path = Path(*test_parts)
            test_path = test_path.with_stem(test_path.stem + "Test")
            return test_path
        return None

    # ── 文件过滤 ──

    def _source_extensions(self) -> tuple[str, ...]:
        return (".java",)

    def _matches_test_pattern(self, file_path: str) -> bool:
        name = Path(file_path).name
        return name.endswith("Test.java") or name.endswith("Tests.java") or name.startswith("Test")

    # ── 内部工具 ──

    @staticmethod
    def _detect_build_tool(repo_root: Path) -> str | None:
        if (repo_root / "pom.xml").exists():
            return "maven"
        if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
            return "gradle"
        return None

    @staticmethod
    def _build_compile_command(build_tool: str, module: str | None) -> str:
        if build_tool == "maven":
            base = "mvn compile -q --batch-mode"
            if module:
                return f"{base} -pl {module} -am"
            return base
        if build_tool == "gradle":
            return "./gradlew compileJava -q --no-daemon"
        return ""

    @staticmethod
    def _extract_compile_errors(output: str) -> str:
        lines = output.splitlines()
        errors: list[str] = []
        for line in lines:
            stripped = line.strip()
            if ("[ERROR]" in stripped and ".java:" in stripped) or (
                "error:" in stripped.lower() and ".java" in stripped
            ):
                errors.append(stripped)
            if len(errors) >= 5:
                break
        if not errors:
            tail = [line.strip() for line in lines[-10:] if line.strip()]
            errors = tail[-3:]
        return "\n".join(errors)
