"""TypeScriptProvider — Qualix TypeScript 语言支持.

整合 AST 分析、断言强度映射、编译检查、弱断言检测。
支持 Jest 和 Vitest 测试框架。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qualix.context.code_skeleton import SkeletonResult
    from qualix.languages.base import CoverageResult

from qualix.json_utils import load_json
from qualix.languages.base import (
    CompileResult,
    LanguageProvider,
    MockInfo,
    Strength,
    TestFrameworkInfo,
    TestGenContext,
    TestMethodInfo,
    WeakAssertResult,
    WeakAssertSignalInfo,
)
from qualix.languages.typescript.assertions import (
    CONSTANT_EXPECT,
    EXPECT_DEFINED_ONLY,
    INSUFFICIENT_ASSERTIONS,
    MOCK_VERIFY_ONLY,
    THROW_NO_EFFECT,
    classify_ts_assertion,
)
from qualix.log import get_logger

log = get_logger(__name__)

_COMPILE_TIMEOUT = 120


class TypeScriptProvider(LanguageProvider):
    """TypeScript 语言 Provider."""

    @property
    def language_id(self) -> str:
        return "typescript"

    @property
    def display_name(self) -> str:
        return "TypeScript"

    # ── 检测 ──

    def detect(self, repo_root: Path) -> float:
        if (repo_root / "tsconfig.json").exists():
            return 0.9
        pkg = repo_root / "package.json"
        if pkg.exists():
            data = load_json(pkg)
            if data:
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "typescript" in deps:
                    return 0.7
        if any(repo_root.rglob("*.ts")):
            return 0.4
        return 0.0

    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        pkg = repo_root / "package.json"
        if not pkg.exists():
            return None
        data = load_json(pkg)
        if not data:
            return None
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        if "vitest" in deps:
            config = "vitest.config.ts" if (repo_root / "vitest.config.ts").exists() else ""
            return TestFrameworkInfo(name="vitest", version=deps.get("vitest", ""), config_file=config)
        if "jest" in deps:
            config = ""
            for name in ("jest.config.ts", "jest.config.js", "jest.config.mjs"):
                if (repo_root / name).exists():
                    config = name
                    break
            return TestFrameworkInfo(name="jest", version=deps.get("jest", ""), config_file=config)
        return None

    def resolve_test_dependencies(self, repo_root: Path) -> list[str]:
        pkg = repo_root / "package.json"
        if not pkg.exists():
            return []
        data = load_json(pkg)
        if not data:
            return []
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        test_pkgs = ["jest", "vitest", "ts-jest", "@jest/globals", "mocha", "chai"]
        return [p for p in test_pkgs if p in deps]

    # ── 质量门控 ──

    def compile_check(self, repo_root: Path, module: str | None = None) -> CompileResult:
        if not (repo_root / "tsconfig.json").exists():
            return CompileResult(passed=True, skipped=True, error_summary="无 tsconfig.json")

        cmd = "npx tsc --noEmit"
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
                error_summary = self._extract_tsc_errors(result.stdout + result.stderr)
            return CompileResult(
                passed=passed,
                build_tool="tsc",
                command=cmd,
                stdout=result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                stderr=result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
                error_summary=error_summary,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                passed=False, build_tool="tsc", command=cmd, error_summary=f"编译超时（>{_COMPILE_TIMEOUT}s）"
            )
        except Exception as exc:
            return CompileResult(
                passed=False, build_tool="tsc", command=cmd, stderr=str(exc), error_summary=f"编译执行异常: {exc}"
            )

    def run_tests(self, repo_root: Path, test_pattern: str = "") -> dict:
        """执行 Jest/Vitest 测试，返回 {success, stdout, stderr, returncode}."""
        fw = self.detect_test_framework(repo_root)
        runner = fw.name if fw else "jest"
        cmd_parts = ["npx", runner, "--passWithNoTests"]
        if runner == "jest":
            cmd_parts += ["--forceExit"]
        if test_pattern:
            cmd_parts += ["--testPathPattern", test_pattern]
        cmd = " ".join(cmd_parts)
        log.info("测试执行: %s (cwd=%s)", cmd, repo_root)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=300,
                shell=True,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "测试执行超时（>300s）", "returncode": -1}
        except Exception as exc:
            return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}

    def run_coverage(self, repo_root: Path) -> CoverageResult | None:
        """运行 Jest --coverage，解析 Istanbul coverage-summary.json。"""

        fw = self.detect_test_framework(repo_root)
        runner = fw.name if fw else "jest"
        cmd = f"npx {runner} --coverage --passWithNoTests --forceExit --coverageReporters json-summary"
        log.info("覆盖率收集: %s (cwd=%s)", cmd, repo_root)
        try:
            subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=300, shell=True)
        except Exception:
            return None

        candidates = [
            repo_root / "coverage" / "coverage-summary.json",
            repo_root / "coverage-summary.json",
            repo_root / ".nyc_output" / "coverage-summary.json",
        ]
        report_path = next((p for p in candidates if p.exists()), None)
        if not report_path:
            return None
        return _parse_istanbul_json(report_path)

    # ── AST 分析 ──

    def parse_test_methods(self, test_content: str) -> list[TestMethodInfo]:
        from qualix.languages.typescript.ast_analyzer import (
            extract_test_methods,
            is_available,
            parse_typescript,
        )

        if not is_available():
            return []
        source = test_content.encode("utf-8")
        root = parse_typescript(source)
        if root is None:
            return []
        return extract_test_methods(root, source)

    def classify_assertion_strength(self, assertion_kind: str, args: list[str]) -> Strength:
        return classify_ts_assertion(assertion_kind, "", args)

    def detect_mock_patterns(self, test_content: str) -> list[MockInfo]:
        from qualix.languages.typescript.ast_analyzer import (
            extract_mock_patterns,
            is_available,
            parse_typescript,
        )

        if not is_available():
            return []
        source = test_content.encode("utf-8")
        root = parse_typescript(source)
        if root is None:
            return []
        return extract_mock_patterns(root, source)

    # ── 弱断言分析 ──

    def analyze_weak_asserts(self, test_content: str) -> list[WeakAssertResult]:
        methods = self.parse_test_methods(test_content)
        results: list[WeakAssertResult] = []
        for m in methods:
            result = self._analyze_method_signals(m)
            if result:
                results.append(result)
        return results

    def _analyze_method_signals(self, method: TestMethodInfo) -> WeakAssertResult | None:
        """分析单个测试方法的弱断言信号."""
        signals: list[WeakAssertSignalInfo] = []
        evidence: list[str] = []
        suggestions: list[str] = []

        strong = [a for a in method.assertions if a.strength == Strength.STRONG]
        weak = [a for a in method.assertions if a.strength == Strength.WEAK]
        trivial = [a for a in method.assertions if a.strength == Strength.TRIVIAL]
        has_strong = bool(strong)

        # Signal 1: 仅 toBeDefined/toBeTruthy 等
        defined_only = [a for a in weak if a.kind in ("toBeDefined", "toBeTruthy", "toBeFalsy")]
        if defined_only and not has_strong:
            signals.append(
                WeakAssertSignalInfo(
                    code=EXPECT_DEFINED_ONLY,
                    severity="high",
                    reason="仅 toBeDefined/toBeTruthy，未验证具体值。",
                )
            )
            evidence.extend(a.text.strip() for a in defined_only[:2])
            suggestions.append("补充 toBe/toEqual 验证具体业务值")

        # Signal 2: 常量断言
        const_asserts = [a for a in trivial if a.kind == "toBe"]
        if const_asserts and not has_strong:
            signals.append(
                WeakAssertSignalInfo(
                    code=CONSTANT_EXPECT,
                    severity="high",
                    reason="存在常量断言 (如 expect(true).toBe(true))。",
                )
            )
            evidence.extend(a.text.strip() for a in const_asserts[:2])
            suggestions.append("移除常量断言，改为断言真实业务表达式")

        # Signal 3: 仅 toHaveBeenCalled 无业务断言
        mock_only = [a for a in trivial if a.kind in ("toHaveBeenCalled", "toHaveReturned")]
        if mock_only and not has_strong and not weak:
            signals.append(
                WeakAssertSignalInfo(
                    code=MOCK_VERIFY_ONLY,
                    severity="high",
                    reason="仅验证函数被调用，未验证业务结果。",
                )
            )
            evidence.extend(a.text.strip() for a in mock_only[:2])
            suggestions.append("在 mock 验证之外补充业务结果断言")

        # Signal 4: toThrow 无后续状态断言
        throw_asserts = [a for a in method.assertions if a.kind in ("toThrow", "toThrowError")]
        if throw_asserts and not any(a for a in strong if a.kind not in ("toThrow", "toThrowError")):
            signals.append(
                WeakAssertSignalInfo(
                    code=THROW_NO_EFFECT,
                    severity="medium",
                    reason="仅 toThrow，缺少失败后的状态断言。",
                )
            )
            evidence.extend(a.text.strip() for a in throw_asserts[:1])
            suggestions.append("补充失败后的状态、数据或副作用断言")

        # Signal 5: 断言数量过少
        total = len(method.assertions)
        method_lines = len(method.content.splitlines())
        if total <= 1 and method_lines > 10 and not signals:
            signals.append(
                WeakAssertSignalInfo(
                    code=INSUFFICIENT_ASSERTIONS,
                    severity="medium",
                    reason=f"方法体 {method_lines} 行但仅 {total} 个断言。",
                )
            )
            suggestions.append("检查是否遗漏了对关键业务结果的断言")

        if not signals:
            return None

        risk = "high" if any(s.severity == "high" for s in signals) else "medium"
        return WeakAssertResult(
            method_name=method.name,
            line_start=method.line_start,
            line_end=method.line_end,
            risk_level=risk,
            signals=signals,
            evidence=list(dict.fromkeys(evidence))[:4],
            suggestion="；".join(dict.fromkeys(suggestions)),
            assert_summary={
                "strong": len(strong),
                "weak": len(weak),
                "trivial": len(trivial),
                "total": total,
            },
        )

    # ── 骨架提取 ──

    def extract_skeleton(
        self,
        source: str,
        expand_methods: set[str] | None = None,
    ) -> SkeletonResult | None:
        """Extract TypeScript code skeleton using tree-sitter."""
        from qualix.languages.typescript.skeleton import extract_skeleton_ts

        return extract_skeleton_ts(source, expand_methods)

    # ── 测试文件定位 ──

    def test_file_pattern(self) -> str:
        return "**/*.{test,spec}.{ts,tsx}"

    def locate_test_file(self, source_file: Path) -> Path | None:
        # src/runner.ts → src/runner.test.ts
        return source_file.with_suffix(".test.ts")

    # ── 生成上下文 ──

    def get_test_gen_context(self, source_file: Path) -> TestGenContext:
        repo_root = source_file.parent
        fw = self.detect_test_framework(repo_root)
        return TestGenContext(
            language="typescript",
            test_framework=fw.name if fw else "jest",
            assertion_style="expect-chain",
            mock_library="jest" if fw and fw.name == "jest" else "vitest",
            conventions=["使用 describe/it 组织测试", "expect().toXxx() 链式断言"],
        )

    # ── 文件过滤 ──

    def _source_extensions(self) -> tuple[str, ...]:
        return (".ts", ".tsx")

    def _matches_test_pattern(self, file_path: str) -> bool:
        name = Path(file_path).name
        for ext in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"):
            if name.endswith(ext):
                return True
        return "__tests__" in file_path

    # ── 内部工具 ──

    @staticmethod
    def _extract_tsc_errors(output: str) -> str:
        lines = output.splitlines()
        errors: list[str] = []
        for line in lines:
            stripped = line.strip()
            if "error TS" in stripped:
                errors.append(stripped)
            if len(errors) >= 5:
                break
        if not errors:
            tail = [line.strip() for line in lines[-10:] if line.strip()]
            errors = tail[-3:]
        return "\n".join(errors)


def _parse_istanbul_json(report_path: Path) -> CoverageResult | None:
    """解析 Istanbul/c8 的 coverage-summary.json，返回 CoverageResult。

    Istanbul 格式示例：
    {
      "total": {
        "lines":      {"total": 100, "covered": 80, "skipped": 0, "pct": 80},
        "branches":   {"total":  40, "covered": 30, "skipped": 0, "pct": 75},
        "statements": {"total": 120, "covered": 96, "skipped": 0, "pct": 80},
        ...
      }
    }
    """
    from qualix.languages.base import CoverageResult

    data = load_json(report_path)
    if not data or not isinstance(data, dict):
        return None
    total = data.get("total", {})
    if not total:
        return None

    def _rate(key: str) -> float:
        section = total.get(key, {})
        pct = section.get("pct")
        if pct is not None:
            return round(float(pct) / 100.0, 4)
        covered = section.get("covered", 0)
        tot = section.get("total", 0)
        return round(covered / tot, 4) if tot else 0.0

    return CoverageResult(
        line_coverage=_rate("lines"),
        branch_coverage=_rate("branches"),
        statement_coverage=_rate("statements"),
        raw_report=total,
    )
