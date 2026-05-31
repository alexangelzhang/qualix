"""GoProvider — lightweight Go support for Qualix language gates."""

from __future__ import annotations

import re
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

_GO_TIMEOUT = 120
_FUNC_RE = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_TEST_RE = re.compile(r"^func\s+(?P<name>Test[A-Za-z0-9_]+)\s*\(\s*t\s+\*testing\.T\s*\)", re.MULTILINE)
_ASSERT_RE = re.compile(r"(?P<kind>assert\.[A-Za-z0-9_]+|require\.[A-Za-z0-9_]+|t\.Errorf|t\.Fatalf|t\.FailNow)\s*\((?P<args>[^)]*)\)")


class GoProvider(LanguageProvider):
    @property
    def language_id(self) -> str:
        return "go"

    @property
    def display_name(self) -> str:
        return "Go"

    def detect(self, repo_root: Path) -> float:
        if (repo_root / "go.mod").exists():
            return 0.95
        if any(repo_root.rglob("*.go")):
            return 0.5
        return 0.0

    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        deps = self.resolve_test_dependencies(repo_root)
        if "testify" in deps:
            return TestFrameworkInfo(name="go-test", version="", config_file="go.mod")
        if any(repo_root.rglob("*_test.go")):
            return TestFrameworkInfo(name="go-test")
        return TestFrameworkInfo(name="go-test") if (repo_root / "go.mod").exists() else None

    def resolve_test_dependencies(self, repo_root: Path) -> list[str]:
        go_mod = repo_root / "go.mod"
        if not go_mod.exists():
            return []
        text = go_mod.read_text(encoding="utf-8", errors="replace")
        deps = []
        if "github.com/stretchr/testify" in text:
            deps.append("testify")
        if "go.uber.org/mock" in text or "github.com/golang/mock" in text:
            deps.append("gomock")
        return deps

    def compile_check(self, repo_root: Path, module: str | None = None) -> CompileResult:
        if not (repo_root / "go.mod").exists():
            return CompileResult(passed=True, skipped=True, error_summary="no go.mod")
        target = module or "./..."
        cmd = ["go", "test", target, "-run", "^$", "-count=0"]
        try:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=_GO_TIMEOUT)
        except FileNotFoundError:
            return CompileResult(passed=False, build_tool="go", command=" ".join(cmd), error_summary="go not found")
        except subprocess.TimeoutExpired:
            return CompileResult(passed=False, build_tool="go", command=" ".join(cmd), error_summary="go test compile timed out")
        return CompileResult(
            passed=result.returncode == 0,
            build_tool="go",
            command=" ".join(cmd),
            stdout=result.stdout[-2000:],
            stderr=result.stderr[-2000:],
            error_summary="" if result.returncode == 0 else _last_lines(result.stdout + result.stderr),
        )

    def lint_check(self, repo_root: Path) -> LintResult:
        if not (repo_root / "go.mod").exists():
            return LintResult(passed=True, skipped=True)
        cmd = ["go", "vet", "./..."]
        try:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=_GO_TIMEOUT)
        except FileNotFoundError:
            return LintResult(passed=False, tool="go vet", command=" ".join(cmd), issues=[{"message": "go not found"}])
        except subprocess.TimeoutExpired:
            return LintResult(passed=False, tool="go vet", command=" ".join(cmd), issues=[{"message": "go vet timed out"}])
        issues = [] if result.returncode == 0 else [{"message": line} for line in _last_lines(result.stdout + result.stderr).splitlines()]
        return LintResult(passed=result.returncode == 0, tool="go vet", command=" ".join(cmd), issues=issues)

    def parse_source(self, source_code: str) -> SourceInfo:
        return SourceInfo(functions=[{"name": m.group("name")} for m in _FUNC_RE.finditer(source_code)])

    def parse_test_methods(self, test_content: str) -> list[TestMethodInfo]:
        matches = list(_TEST_RE.finditer(test_content))
        methods: list[TestMethodInfo] = []
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(test_content)
            content = test_content[start:end]
            line_start = test_content[:start].count("\n") + 1
            line_end = line_start + content.count("\n")
            assertions = []
            for assertion in _ASSERT_RE.finditer(content):
                kind = assertion.group("kind")
                args = _split_args(assertion.group("args"))
                assertions.append(
                    AssertionInfo(
                        kind=kind,
                        line=line_start + content[: assertion.start()].count("\n"),
                        text=assertion.group(0),
                        strength=self.classify_assertion_strength(kind, args),
                        args=args,
                    )
                )
            methods.append(
                TestMethodInfo(
                    name=match.group("name"),
                    line_start=line_start,
                    line_end=line_end,
                    content=content,
                    assertions=assertions,
                )
            )
        return methods

    def classify_assertion_strength(self, assertion_kind: str, args: list[str]) -> Strength:
        kind = assertion_kind.lower()
        if kind.endswith(("equal", "equals", "noerror", "error", "contains", "len", "true", "false")):
            return Strength.STRONG
        if kind.endswith(("notnil", "nil", "notempty")):
            return Strength.WEAK
        if kind in {"t.failnow", "t.fatalf", "t.errorf"}:
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
                        suggestion="assert concrete returned values and side effects",
                        assert_summary={"strong": len(strong), "weak": len(weak), "total": len(method.assertions)},
                    )
                )
        return results

    def test_file_pattern(self) -> str:
        return "**/*_test.go"

    def locate_test_file(self, source_file: Path) -> Path | None:
        if source_file.suffix != ".go" or source_file.name.endswith("_test.go"):
            return None
        return source_file.with_name(f"{source_file.stem}_test.go")

    def get_test_gen_context(self, source_file: Path) -> TestGenContext:
        return TestGenContext(
            language="go",
            test_framework="go test",
            assertion_style="testing or testify/assert",
            mock_library="gomock or hand-written fakes",
            conventions=["use table-driven tests", "check returned values and side effects", "pass context explicitly"],
        )

    def _source_extensions(self) -> tuple[str, ...]:
        return (".go",)

    def _matches_test_pattern(self, file_path: str) -> bool:
        return Path(file_path).name.endswith("_test.go")


def _split_args(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _last_lines(text: str, limit: int = 8) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])

