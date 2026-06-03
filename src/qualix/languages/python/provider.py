"""PythonProvider — lightweight Python support for Qualix language gates."""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
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
        # Phase 1: syntax check via compileall
        target = module or "."
        cmd = ["python3", "-m", "compileall", "-q", target]
        try:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=_PY_TIMEOUT)
        except FileNotFoundError:
            return CompileResult(passed=False, build_tool="compileall", command=" ".join(cmd), error_summary="python3 not found")
        except subprocess.TimeoutExpired:
            return CompileResult(passed=False, build_tool="compileall", command=" ".join(cmd), error_summary="compileall timed out")
        if result.returncode != 0:
            return CompileResult(
                passed=False,
                build_tool="compileall",
                command=" ".join(cmd),
                stdout=result.stdout[-2000:],
                stderr=result.stderr[-2000:],
                error_summary=_last_lines(result.stdout + result.stderr),
            )

        # Phase 2: import check — catches missing deps and NameError that compileall misses
        test_files = _find_test_files(repo_root, module)
        if test_files:
            import_result = _import_check(repo_root, test_files)
            if not import_result.passed:
                return import_result

        return CompileResult(passed=True, build_tool="compileall+import", command=" ".join(cmd))

    def import_check(self, repo_root: Path, test_files: list[Path] | None = None) -> CompileResult:
        """Standalone import check: actually imports generated test files in a subprocess.

        Catches ModuleNotFoundError, ImportError, NameError and similar runtime
        import failures that ``python -m compileall`` cannot detect.
        """
        files = test_files or _find_test_files(repo_root, None)
        if not files:
            return CompileResult(passed=True, build_tool="import_check", skipped=True, error_summary="no test files found")
        return _import_check(repo_root, files)

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
        # Walk up to find the project root (directory containing pyproject.toml / setup.py)
        repo_root = _find_project_root(source_file)
        fw = self.detect_test_framework(repo_root)
        has_pytest_mock = _has_pytest_mock(repo_root)
        mock_library = "pytest-mock (mocker fixture)" if has_pytest_mock else "unittest.mock"
        return TestGenContext(
            language="python",
            test_framework=fw.name if fw else "pytest",
            assertion_style="plain assert / pytest.raises(ExceptionClass, match=...)",
            mock_library=mock_library,
            conventions=[
                "use class TestTargetClass with method test_method_condition_expected",
                "place EUT traceability comment as first line of test body",
                "prefer constructor injection (MagicMock passed to __init__) over patch",
                "use patch('module.under.test.DepName') when dependency is imported not injected",
                "use @pytest.mark.parametrize for boundary value coverage",
                "assert concrete values and side effects — never bare assert result",
                "use mock.assert_called_once() not mock.assert_called()",
                "prefer Decimal for money comparisons",
            ],
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


def _find_project_root(source_file: Path) -> Path:
    """Walk up from source_file until a pyproject.toml / setup.py / requirements.txt is found."""
    for parent in [source_file.parent, *source_file.parents]:
        if any((parent / f).exists() for f in ("pyproject.toml", "setup.py", "requirements.txt")):
            return parent
    return source_file.parent


def _has_pytest_mock(repo_root: Path) -> bool:
    """Return True if pytest-mock is listed as a dependency in the project."""
    for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
        path = repo_root / name
        if path.exists() and "pytest-mock" in path.read_text(encoding="utf-8", errors="replace").lower():
            return True
    return False


def _has_command(name: str) -> bool:
    try:
        result = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _last_lines(text: str, limit: int = 8) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])


def _find_test_files(repo_root: Path, module: str | None) -> list[Path]:
    """Find test_*.py files under repo_root (or module subdirectory)."""
    search_root = repo_root / module if module else repo_root
    if not search_root.exists():
        return []
    return list(search_root.rglob("test_*.py")) + list(search_root.rglob("*_test.py"))


def _import_check(repo_root: Path, test_files: list[Path]) -> CompileResult:
    """Import each test file in an isolated subprocess to catch runtime import errors.

    Uses a minimal script that inserts repo_root into sys.path and attempts
    ``importlib.import_module`` for each file. Failures are surfaced as a
    structured error summary so Q05b can show actionable diagnostics.
    """
    # Write a small driver script to a temp file to avoid shell-quoting issues
    driver = (
        "import sys, importlib.util, pathlib\n"
        "root = sys.argv[1]\n"
        "sys.path.insert(0, root)\n"
        "errors = []\n"
        "for p in sys.argv[2:]:\n"
        "    spec = importlib.util.spec_from_file_location('_chk', p)\n"
        "    mod = importlib.util.module_from_spec(spec)\n"
        "    try:\n"
        "        spec.loader.exec_module(mod)\n"
        "    except Exception as e:\n"
        "        rel = pathlib.Path(p).relative_to(root) if pathlib.Path(p).is_relative_to(root) else pathlib.Path(p).name\n"
        "        errors.append(f'{rel}: {type(e).__name__}: {e}')\n"
        "if errors:\n"
        "    print('\\n'.join(errors), file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(driver)
        driver_path = f.name

    cmd = [sys.executable, driver_path, str(repo_root)] + [str(tf) for tf in test_files[:20]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_PY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return CompileResult(passed=False, build_tool="import_check", command="import_check", error_summary="import check timed out")
    finally:
        try:
            Path(driver_path).unlink(missing_ok=True)
        except Exception:
            pass

    if result.returncode != 0:
        return CompileResult(
            passed=False,
            build_tool="import_check",
            command="import_check",
            stderr=result.stderr[-2000:],
            error_summary=_last_lines(result.stderr),
        )
    return CompileResult(passed=True, build_tool="import_check")

