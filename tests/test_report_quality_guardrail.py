"""Tests for report_quality_checks + semantic_guardrail."""

from __future__ import annotations

import pytest

from dqg.quality.report_quality_checks import (
    check_confidence_annotations,
    check_gap_risk_level,
    check_id_format,
    check_open_decision_owner,
    check_source_annotations,
)
from dqg.quality.semantic_guardrail import ReportSemanticGuardrail
from dqg.quality.guardrail import GuardrailContext


# ---------------------------------------------------------------------------
# report_quality_checks
# ---------------------------------------------------------------------------


class TestSourceAnnotations:
    def test_detects_missing_source(self):
        text = "该接口缺失幂等校验，存在重复提交风险\n"
        issues = check_source_annotations(text)
        assert len(issues) >= 1
        assert issues[0]["check"] == "source_annotation"

    def test_passes_with_source(self):
        text = "该接口缺失幂等校验 [来源: OrderService.java:42]\n"
        issues = check_source_annotations(text)
        assert len(issues) == 0

    def test_skips_table_headers(self):
        text = "| --- | --- | --- |\n"
        issues = check_source_annotations(text)
        assert len(issues) == 0

    def test_skips_headings(self):
        text = "# 风险总结\n"
        issues = check_source_annotations(text)
        assert len(issues) == 0


class TestIdFormat:
    def test_valid_ids(self):
        data = {
            "requirements": [{"req_id": "REQ-001"}, {"req_id": "BR-002"}],
            "semantic_expectations": [{"se_id": "SE-001"}],
            "gaps": [{"gap_id": "GAP-001"}],
            "open_items": [{"open_id": "OPEN-001"}],
        }
        issues = check_id_format(data)
        assert len(issues) == 0

    def test_invalid_id_format(self):
        data = {
            "requirements": [{"req_id": "req_001"}],
            "semantic_expectations": [],
            "gaps": [],
            "open_items": [],
        }
        issues = check_id_format(data)
        assert len(issues) >= 1

    def test_empty_data(self):
        issues = check_id_format({})
        assert len(issues) == 0


class TestGapRiskLevel:
    def test_detects_missing_risk(self):
        data = {"gaps": [{"gap_id": "GAP-001", "description": "缺少校验"}]}
        issues = check_gap_risk_level(data)
        assert len(issues) == 1
        assert "P0/P1/P2" in issues[0]["message"]

    def test_passes_with_severity(self):
        data = {"gaps": [{"gap_id": "GAP-001", "severity": "P0", "description": "缺少校验"}]}
        issues = check_gap_risk_level(data)
        assert len(issues) == 0

    def test_passes_with_risk_in_description(self):
        data = {"gaps": [{"gap_id": "GAP-001", "description": "P1 缺少校验"}]}
        issues = check_gap_risk_level(data)
        assert len(issues) == 0


class TestOpenDecisionOwner:
    def test_detects_missing_owner(self):
        data = {"open_items": [{"open_id": "OPEN-001", "description": "待确定方案"}]}
        issues = check_open_decision_owner(data)
        assert len(issues) == 1

    def test_passes_with_decision_owner_field(self):
        data = {"open_items": [{"open_id": "OPEN-001", "decision_owner": "PM 张三"}]}
        issues = check_open_decision_owner(data)
        assert len(issues) == 0

    def test_passes_with_owner_in_description(self):
        data = {"open_items": [{"open_id": "OPEN-001", "description": "需产品决策方确认"}]}
        issues = check_open_decision_owner(data)
        assert len(issues) == 0


class TestConfidenceAnnotations:
    def test_detects_missing_confidence(self):
        text = "REQ-001 COVERED\nREQ-002 NOT_COVERED\n"
        issues = check_confidence_annotations(text, "Q04")
        assert len(issues) == 1

    def test_skips_non_applicable_phases(self):
        text = "REQ-001 COVERED\n"
        issues = check_confidence_annotations(text, "Q05")
        assert len(issues) == 0

    def test_passes_with_confidence(self):
        text = "REQ-001 COVERED High confidence\nREQ-002 NOT_COVERED Low\n"
        issues = check_confidence_annotations(text, "Q04")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# semantic_guardrail
# ---------------------------------------------------------------------------

def _make_ctx(phase_id: str, report: str = "", data: dict | None = None) -> GuardrailContext:
    from pathlib import Path
    return GuardrailContext(
        output_dir=Path("/tmp/test"),
        project_id="test",
        phase_id=phase_id,
        phase_dir=Path("/tmp/test/Q01"),
        report_content=report,
        structured_data=data or {},
    )


class TestReportSemanticGuardrail:
    def test_br_detail_detects_vague(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q01", data={
            "requirements": [{"req_id": "BR-001", "description": "需要校验"}],
        })
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed]
        assert len(warnings) >= 1
        assert "概括性描述" in warnings[0].message

    def test_br_detail_passes_with_detail(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q01", data={
            "requirements": [{
                "req_id": "BR-001",
                "description": "订单金额字段必须为 BigDecimal，精度 2 位，校验范围 0.01-999999.99",
            }],
        })
        results = g.check(ctx)
        br_warnings = [r for r in results if not r.passed and "概括性" in r.message]
        assert len(br_warnings) == 0

    def test_coverage_evidence_detects_no_evidence(self):
        g = ReportSemanticGuardrail()
        report = "REQ-001 COVERED 已覆盖\nREQ-002 COVERED 已覆盖\nREQ-003 COVERED 已覆盖\n"
        ctx = _make_ctx("Q04", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "虚高" in r.message]
        assert len(warnings) >= 1

    def test_coverage_evidence_passes_with_source(self):
        g = ReportSemanticGuardrail()
        report = "REQ-001 COVERED [来源: OrderService.java:42]\n"
        ctx = _make_ctx("Q04", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "虚高" in r.message]
        assert len(warnings) == 0

    def test_cross_phase_violation(self):
        g = ReportSemanticGuardrail()
        report = "EUT-001 测试用例\nEUT-002 单测\nEUT-003 unit test\n"
        ctx = _make_ctx("Q01", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "越权" in r.message]
        assert len(warnings) >= 1

    def test_cross_phase_ok_for_q05(self):
        g = ReportSemanticGuardrail()
        report = "EUT-001 测试用例\nEUT-002 单测\n"
        ctx = _make_ctx("Q05", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "越权" in r.message]
        assert len(warnings) == 0

    def test_p0_unclosed_detects(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q01", report="整体通过，建议上线", data={
            "gaps": [{"gap_id": "GAP-001", "severity": "P0", "status": "open"}],
        })
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "P0" in r.message]
        assert len(warnings) >= 1

    def test_p0_closed_passes(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q01", report="整体通过", data={
            "gaps": [{"gap_id": "GAP-001", "severity": "P0", "status": "closed"}],
        })
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "P0" in r.message]
        assert len(warnings) == 0
