"""Q05/Q06 TypeScript profile 单测.

覆盖：test_execution_gate / handlers_detection / coverage_gate / q05_structure_checks
的 TS 相关改动，保证 TS 项目不被错误 BLOCKED，且弱断言/覆盖率门禁正常工作。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dqg.quality.checks.coverage_gate import (
    check_coverage_gate,
    find_coverage_report,
    parse_istanbul_json,
)
from dqg.quality.checks.q05_structure_checks import (
    _check_wrong_directory,
    _collect_supplemental_files,
)
from dqg.quality.checks.test_execution_gate import (
    _discover_new_test_classes,
    run_test_check,
)
from dqg.runtime.execution_context import ExecutionContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, phase_id: str = "Q05") -> ExecutionContext:
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        output_dir=tmp_path,
        project_id="ts-test",
        phase_id=phase_id,
        internal_dir=internal_dir,
        phase_root=tmp_path,
        phase_def={"dir_suffix": "phaseB"},
        shared={},
    )


def _make_ts_repo(tmp_path: Path, with_tsconfig: bool = True, with_package: bool = True) -> Path:
    repo = tmp_path / "ts-app"
    repo.mkdir()
    if with_tsconfig:
        (repo / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    if with_package:
        (repo / "package.json").write_text(
            json.dumps({"devDependencies": {"jest": "^29", "typescript": "^5", "ts-jest": "^29"}})
        )
    (repo / "src").mkdir()
    (repo / "src" / "order.service.ts").write_text("export class OrderService {}")
    return repo


# ---------------------------------------------------------------------------
# Step 2: test_execution_gate — 文件发现
# ---------------------------------------------------------------------------


class TestDiscoverTsTestFiles:
    def test_ts_test_files_discovered(self, tmp_path: Path):
        """git diff 输出中的 *.test.ts / *.spec.ts 应被发现。"""
        diff_output = "\n".join(
            [
                "src/order.service.test.ts",
                "src/user.spec.ts",
                "src/order.service.tsx",  # 不是测试文件（无 .test./.spec.）
            ]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=diff_output)
            files = _discover_new_test_classes(tmp_path)

        names = [f["class_name"] for f in files]
        assert "order.service.test" in names
        assert "user.spec" in names
        langs = [f["language"] for f in files]
        assert all(lang == "typescript" for lang in langs)

    def test_java_test_files_still_work(self, tmp_path: Path):
        """Java Test.java 文件不受影响。"""
        diff_output = "src/test/java/com/example/OrderServiceTest.java"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=diff_output)
            files = _discover_new_test_classes(tmp_path)

        assert len(files) == 1
        assert files[0]["language"] == "java"
        assert files[0]["class_name"] == "OrderServiceTest"

    def test_non_test_ts_files_excluded(self, tmp_path: Path):
        """src/order.service.ts（无 .test.）不应被识别为测试文件。"""
        diff_output = "src/order.service.ts\nsrc/utils.tsx"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=diff_output)
            files = _discover_new_test_classes(tmp_path)

        assert files == []


class TestRunTestCheckTs:
    def test_no_package_json_skip(self, tmp_path: Path):
        """无 package.json / tsconfig.json → skip，不 BLOCK。"""
        empty_repo = tmp_path / "empty"
        empty_repo.mkdir()
        result = run_test_check(empty_repo, ["order.test.ts"], language="typescript")
        assert result["passed"] is True
        assert result["phase"] == "skip"

    def test_ts_tests_pass(self, tmp_path: Path):
        """npx jest 返回 0 → passed。"""
        repo = _make_ts_repo(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Tests: 3 passed", stderr="")
            result = run_test_check(repo, ["order.service.test"], language="typescript")

        assert result["passed"] is True
        assert result["phase"] == "test"

    def test_ts_tests_fail(self, tmp_path: Path):
        """npx jest 返回非零 → BLOCKED。"""
        repo = _make_ts_repo(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="FAIL src/order.service.test.ts\n● Error: expect received false",
                stderr="",
            )
            result = run_test_check(repo, ["order.service.test"], language="typescript")

        assert result["passed"] is False
        assert result["phase"] == "test"
        assert "order.service.test" in result["error_summary"] or result["error_summary"]


# ---------------------------------------------------------------------------
# Step 3: handlers_detection — 测试文件后缀
# ---------------------------------------------------------------------------


class TestCollectTestCodeText:
    def test_ts_files_collected(self, tmp_path: Path):
        """supplemental_tests/ 下的 .ts 文件应被收集。"""
        supp = tmp_path / "supplemental_tests"
        supp.mkdir()
        (supp / "order.test.ts").write_text("expect(1).toBe(1);")
        (supp / "readme.md").write_text("ignored")

        # 直接测试 _collect_supplemental_files 而非 handler（后者需要完整 ctx）
        files = _collect_supplemental_files(tmp_path)
        names = [f.name for f in files]
        assert "order.test.ts" in names
        assert "readme.md" not in names

    def test_java_files_still_collected(self, tmp_path: Path):
        """原有 .java 文件不受影响。"""
        supp = tmp_path / "supplemental_tests"
        supp.mkdir()
        (supp / "OrderTest.java").write_text("@Test public void test(){}")
        files = _collect_supplemental_files(tmp_path)
        assert any(f.name == "OrderTest.java" for f in files)


# ---------------------------------------------------------------------------
# Step 4: coverage_gate — Istanbul JSON
# ---------------------------------------------------------------------------


class TestParseIstanbulJson:
    def _write_summary(self, tmp_path: Path, lines_pct: float, branches_pct: float) -> Path:
        summary = {
            "total": {
                "lines": {"total": 100, "covered": int(lines_pct), "skipped": 0, "pct": lines_pct},
                "branches": {"total": 40, "covered": int(branches_pct * 0.4), "skipped": 0, "pct": branches_pct},
                "statements": {"total": 120, "covered": int(lines_pct * 1.2), "skipped": 0, "pct": lines_pct},
                "functions": {"total": 20, "covered": int(lines_pct * 0.2), "skipped": 0, "pct": lines_pct},
            }
        }
        path = tmp_path / "coverage-summary.json"
        path.write_text(json.dumps(summary))
        return path

    def test_parse_line_rate(self, tmp_path: Path):
        """line rate 应正确解析为 0.0-1.0 浮点。"""
        path = self._write_summary(tmp_path, lines_pct=80.0, branches_pct=75.0)
        result = parse_istanbul_json(path)
        assert result is not None
        assert abs(result["line"]["rate"] - 0.80) < 0.01

    def test_parse_branch_rate(self, tmp_path: Path):
        path = self._write_summary(tmp_path, lines_pct=90.0, branches_pct=70.0)
        result = parse_istanbul_json(path)
        assert result is not None
        assert abs(result["branch"]["rate"] - 0.70) < 0.01

    def test_missing_file_returns_none(self, tmp_path: Path):
        result = parse_istanbul_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_coverage_gate_pass(self, tmp_path: Path):
        """line 100%, branch 100% → 通过 100% 门禁（公司硬性指标）。"""
        path = self._write_summary(tmp_path, lines_pct=100.0, branches_pct=100.0)
        coverage = parse_istanbul_json(path)
        errors = check_coverage_gate(coverage)  # type: ignore[arg-type]
        assert errors == []

    def test_coverage_gate_pass_custom_threshold(self, tmp_path: Path):
        """line 85%, branch 82% → 通过自定义 80% 门禁（向下兼容）。"""
        path = self._write_summary(tmp_path, lines_pct=85.0, branches_pct=82.0)
        errors = check_coverage_gate(  # type: ignore[arg-type]
            parse_istanbul_json(path), line_threshold=0.80, branch_threshold=0.80
        )
        assert errors == []

    def test_coverage_gate_blocked(self, tmp_path: Path):
        """line 85% < 100% → BLOCKED（公司硬性指标）。"""
        path = self._write_summary(tmp_path, lines_pct=85.0, branches_pct=82.0)
        coverage = parse_istanbul_json(path)
        errors = check_coverage_gate(coverage)  # type: ignore[arg-type]
        assert any("BLOCKED" in e for e in errors)


class TestFindCoverageReport:
    def test_finds_istanbul_json(self, tmp_path: Path):
        """coverage/coverage-summary.json 应被发现。"""
        repo = tmp_path / "ts-app"
        (repo / "coverage").mkdir(parents=True)
        summary = repo / "coverage" / "coverage-summary.json"
        summary.write_text('{"total": {}}')
        found = find_coverage_report(repo)
        assert found == summary

    def test_finds_jacoco_xml(self, tmp_path: Path):
        """target/site/jacoco/jacoco.xml 应被发现（Java 项目不受影响）。"""
        repo = tmp_path / "java-app"
        (repo / "target" / "site" / "jacoco").mkdir(parents=True)
        jacoco = repo / "target" / "site" / "jacoco" / "jacoco.xml"
        jacoco.write_text("<report></report>")
        found = find_coverage_report(repo)
        assert found == jacoco

    def test_jacoco_preferred_over_istanbul(self, tmp_path: Path):
        """如果两种报告都存在，JaCoCo XML 优先（Java 项目使用了 Istanbul 目录不常见）。"""
        repo = tmp_path / "mixed"
        (repo / "target" / "site" / "jacoco").mkdir(parents=True)
        jacoco = repo / "target" / "site" / "jacoco" / "jacoco.xml"
        jacoco.write_text("<report></report>")
        (repo / "coverage").mkdir()
        (repo / "coverage" / "coverage-summary.json").write_text('{"total": {}}')
        found = find_coverage_report(repo)
        assert found == jacoco


# ---------------------------------------------------------------------------
# Step 5: q05_structure_checks — wrong_directory for TS
# ---------------------------------------------------------------------------


class TestCheckWrongDirectoryTs:
    def test_ts_test_file_in_tests_dir_ok(self):
        """__tests__/ 下的 .ts 文件不应触发 wrong_directory。"""
        data = {"test_cases": [{"test_location": {"file": "src/__tests__/order.service.test.ts"}}]}
        errors = _check_wrong_directory(data)
        assert errors == []

    def test_ts_spec_file_ok(self):
        """*.spec.ts 文件不应触发 wrong_directory。"""
        data = {"test_cases": [{"test_location": {"file": "src/order.service.spec.ts"}}]}
        errors = _check_wrong_directory(data)
        assert errors == []

    def test_ts_source_file_as_test_location_blocked(self):
        """非测试 .ts 文件（如 src/order.service.ts）作为 test_location → BLOCKED。"""
        data = {"test_cases": [{"test_location": {"file": "src/order.service.ts"}}]}
        errors = _check_wrong_directory(data)
        assert any("BLOCKED" in e for e in errors)

    def test_java_wrong_dir_still_blocked(self):
        """Java *Test.java 在 src/main/ → BLOCKED（回归）。"""
        data = {"test_cases": [{"test_location": {"file": "src/main/java/com/example/OrderTest.java"}}]}
        errors = _check_wrong_directory(data)
        assert any("BLOCKED" in e for e in errors)
