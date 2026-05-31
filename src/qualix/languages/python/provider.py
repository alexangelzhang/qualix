"""PythonProvider — lightweight Python support for Qualix language gates."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from qualix.languages.base import (
    AssertionInfo,
    CompileResult,
    LanguageProvider,
    LintResult,
    SourceInfo,
    Strength,
    TestFrameworkInfo,
    TestGenContext,
    TestMethodInfo,
    WeakAssertResult,
    WeakAssertSignalInfo,
)

_PY_TIMEOUT = 120


class PythonProvider(LanguageProvider):
    @property
    def language_id(self) -> str:
        return "python"

    @property
    def display_name(self) -> str:
        return "Python"

    def detect(self, repo_root: Path) -> float:
        if (repo_root / "pyproject.toml").exists():
            return 0.95
        if (repo_root / "requirements.txt").exists() or (repo_root / "setup.py").exists():
            return 0.8
        if any(repo_root.rglob("*.py")):
            return 0.5
        return 0.0

    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        text = ""
        for name in ("pyproject.toml", "requirements.txt"):
            path = repo_root / name
            if path.exists():
                text += path.read_text(encoding="utf-8", errors="replace").lower()
        if "pytest" in text or (repo_root / "tests").exists():
            return TestFrameworkInfo(name="pytest", config_file="pyproject.toml" if (repo_root / "pyproject.toml").exists() else "")
        if "unittest" in text:
            return TestFrameworkInfo(name="unittest")
        return None

    def resolve_test_dependencies(self, repo_root: Path) -> list[str]:
        deps = []
        text = ""
        for name in ("pyproject.toml", "requirements.txt"):
            path = repo_root / name
            if path.exists():
                text += path.read_text(encoding="utf-8", errors="replace").lower()
        for dep in ("pytest", "pytest-cov", "ruff", "mypy"):
            if dep in text:
                deps.append(dep)
        return deps

    def compile_check(self, repo_root: Path, module: str | None = None) -> CompileResult:
        target = module or "."
        cmd = ["python3", "-m", "compileall", "-q", target]
        try:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=_PY_TIMEOUT)
        except FileNotFoundError:
            return CompileResult(passed=False, build_tool="compileall", command=" ".join(cmd), error_summary="python3 not found")
        except subprocess.TimeoutExpired:
            return CompileResult(passed=False, build_tool="compileall", command=" ".join(cmd), error_summary="compileall timed out")
        return CompileResult(
            passed=result.returncode == 0,
            build_tool="compileall",
            command=" ".join(cmd),
            stdout=result.stdout[-2000:],
            stderr=result.stderr[-2000:],
            error_summary="" if result.returncode == 0 else _last_lines(result.stdout + result.stderr),
        )

    def lint_check(self, repo_root: Path) -> LintResult:
        if not _has_command("ruff"):
            return LintResult(passed=True, tool="ruff", skipped=True)
        cmd = ["ruff", "check", "."]
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=_PY_TIMEOUT)
        issues = [] if result.returncode == 0 else [{"message": line} for line in _last_lines(result.stdout + result.stderr).splitlines()]
        return LintResult(passed=result.returncode == 0, tool="ruff", command=" ".join(cmd), issues=issues)

    def parse_source(self, source_code: str) -> SourceInfo:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return SourceInfo()
        functions = []
        classes = []
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                functions.append({"name": node.name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                classes.append({"name": node.name, "line": node.lineno})
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return SourceInfo(functions=functions, classes=classes, imports=imports)

    def parse_test_methods(self, test_content: str) -> list[TestMethodInfo]:
        try:
            tree = ast.parse(test_content)
        except SyntaxError:
            return []
        methods = []
        lines = test_content.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            line_start = node.lineno
            line_end = getattr(node, "end_lineno", node.lineno)
            content = "\n".join(lines[line_start - 1 : line_end])
            assertions = []
            for child in ast.walk(node):
                info = _assertion_from_node(child, line_start)
                if info:
                    assertions.append(info)
            methods.append(
                TestMethodInfo(
                    name=node.name,
                    line_start=line_start,
                    line_end=line_end,
                    content=content,
                    assertions=assertions,
                )
            )
        return methods

    def classify_assertion_strength(self, assertion_kind: str, args: list[str]) -> Strength:
        if assertion_kind in {"assert_compare", "assert_equal", "assert_raises", "pytest.raises"}:
            return Strength.STRONG
        if assertion_kind in {"assert_truthy", "assert_is_not_none", "assert_called"}:
            return Strength.WEAK
        return Strength.WEAK

    def analyze_weak_asserts(self, test_content: str) -> list[WeakAssertResult]:
        results = []
        for method in self.parse_test_methods(test_content):
            strong = [a for a in method.assertions if a.strength == Strength.STRONG]
            weak = [a for a in method.assertions if a.strength == Strength.WEAK]
            signals = []
            evidence = []
            if not method.assertions:
                signals.append(WeakAssertSignalInfo(code="NO_ASSERTION", severity="high", reason="test has no assertion"))
            elif weak and not strong:
                signals.append(
                    WeakAssertSignalInfo(code="WEAK_ASSERT_ONLY", severity="medium", reason="test only has weak assertions")
                )
                evidence = [a.text for a in weak[:3]]
            if signals:
                results.append(
                    WeakAssertResult(
                        method_name=method.name,
                        line_start=method.line_start,
                        line_end=method.line_end,
                        risk_level="high" if any(s.severity == "high" for s in signals) else "medium",
                        signals=signals,
                        evidence=evidence,
                        suggestion="assert concrete values, state changes, or side effects",
                        assert_summary={"strong": len(strong), "weak": len(weak), "total": len(method.assertions)},
                    )
                )
        return results

    def test_file_pattern(self) -> str:
        return "**/test_*.py"

    def locate_test_file(self, source_file: Path) -> Path | None:
        if source_file.suffix != ".py" or source_file.name.startswith("test_"):
            return None
        return source_file.with_name(f"test_{source_file.name}")

    def get_test_gen_context(self, source_file: Path) -> TestGenContext:
        return TestGenContext(
            language="python",
            test_framework="pytest",
            assertion_style="plain assert / pytest.raises",
            mock_library="unittest.mock",
            conventions=["use Arrange-Act-Assert", "assert concrete values and side effects", "prefer Decimal for money"],
        )

    def _source_extensions(self) -> tuple[str, ...]:
        return (".py",)

    def _matches_test_pattern(self, file_path: str) -> bool:
        name = Path(file_path).name
        return name.startswith("test_") or name.endswith("_test.py")


def _assertion_from_node(node: ast.AST, method_start: int) -> AssertionInfo | None:
    if isinstance(node, ast.Assert):
        kind = "assert_compare" if isinstance(node.test, ast.Compare) else "assert_truthy"
        text = ast.unparse(node) if hasattr(ast, "unparse") else kind
        return AssertionInfo(kind=kind, line=node.lineno, text=text, strength=PythonProvider().classify_assertion_strength(kind, []))
    if isinstance(node, ast.With):
        text = ast.unparse(node) if hasattr(ast, "unparse") else "with"
        if "pytest.raises" in text:
            return AssertionInfo(kind="pytest.raises", line=node.lineno, text=text, strength=Strength.STRONG)
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        text = ast.unparse(node) if hasattr(ast, "unparse") else "call"
        if ".assert_called" in text:
            return AssertionInfo(kind="assert_called", line=node.lineno, text=text, strength=Strength.WEAK)
    _ = method_start
    return None


def _has_command(name: str) -> bool:
    try:
        result = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _last_lines(text: str, limit: int = 8) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])

