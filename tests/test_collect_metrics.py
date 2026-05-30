"""Tests for qualix.collect_metrics."""

from pathlib import Path

from qualix.reporting.collect_metrics import (
    collect_all_metrics,
    count_pattern,
    extract_phase_a6_metrics,
    extract_phase_a_metrics,
    extract_phase_c_metrics,
)


class TestCountPattern:
    def test_basic_count(self):
        text = "| REQ-001 | desc |\n| REQ-002 | desc |"
        assert count_pattern(text, r"\|\s*REQ-\d+") == 2

    def test_no_match(self):
        assert count_pattern("hello world", r"REQ-\d+") == 0


class TestExtractPhaseAMetrics:
    def test_not_found(self, tmp_path: Path):
        result = extract_phase_a_metrics(tmp_path / "nonexistent.md")
        assert result["status"] == "NOT_FOUND"

    def test_extracts_counts(self, tmp_path: Path):
        report = tmp_path / "phase_a_report.md"
        report.write_text(
            "| REQ-001 | 需求1 |\n"
            "| BR-001 | 分支1 |\n"
            "| BR-002 | 分支2 |\n"
            "| SE-001 | 语义1 |\n"
            "| GAP-001 | 缺口1 |\n"
            "| OPEN-001 | 待确认1 |\n"
            "评审结论：**有条件通过**\n",
            encoding="utf-8",
        )
        result = extract_phase_a_metrics(report)
        assert result["status"] == "COLLECTED"
        assert result["req_count"] == 1
        assert result["br_count"] == 2
        assert result["se_count"] == 1
        assert result["gap_count"] == 1
        assert result["open_count"] == 1
        assert result["conclusion"] == "有条件通过"


class TestExtractPhaseA6Metrics:
    def test_extracts_issue_density(self, tmp_path: Path):
        report = tmp_path / "tech_design_quality_review.md"
        report.write_text(
            "| ARCH-001 | 分层问题 |\n"
            "| ARCH-002 | 依赖问题 |\n"
            "| API-001 | 接口问题 |\n"
            "| DATA-001 | 数据问题 |\n"
            "| EXC-001 | 异常问题 |\n"
            "| PERF-001 | 性能问题 |\n"
            "| SAFE | 安全路径 |\n"
            "| RISK | 风险路径 |\n"
            "| CRITICAL_GAP | 关键缺口 |\n",
            encoding="utf-8",
        )
        result = extract_phase_a6_metrics(report)
        assert result["status"] == "COLLECTED"
        assert result["issue_density"]["architecture"] == 2
        assert result["issue_density"]["api_design"] == 1
        assert result["issue_density"]["total"] == 6
        assert result["failure_mode"]["safe"] == 1
        assert result["failure_mode"]["critical_gap"] == 1


class TestExtractPhaseCMetrics:
    def test_extracts_coverage(self, tmp_path: Path):
        report = tmp_path / "ut_audit_report.md"
        report.write_text(
            "| EUT-001 | COVERED |\n"
            "| EUT-002 | COVERED |\n"
            "| EUT-003 | PARTIAL |\n"
            "| EUT-004 | MISSING |\n"
            "| EUT-005 | WRONG_TARGET |\n"
            "line = 85.3%\n"
            "branch = 78.1%\n"
            "结论：`CONDITIONAL_PASS`\n",
            encoding="utf-8",
        )
        result = extract_phase_c_metrics(report)
        assert result["status"] == "COLLECTED"
        assert result["coverage_quality"]["covered"] == 2
        assert result["coverage_quality"]["missing"] == 1
        assert result["coverage_quality"]["wrong_target"] == 1
        assert result["coverage_gate"]["line_coverage"] == 85.3
        assert result["coverage_gate"]["branch_coverage"] == 78.1
        assert result["conclusion"] == "CONDITIONAL_PASS"


class TestCollectAllMetrics:
    def test_all_not_found(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        metrics = collect_all_metrics(output_dir, "NOPROJECT")
        assert metrics["project_id"] == "NOPROJECT"
        for phase_metrics in metrics["phases"].values():
            assert phase_metrics["status"] == "NOT_FOUND"
