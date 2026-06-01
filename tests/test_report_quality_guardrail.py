"""Tests for report_quality_checks + semantic_guardrail."""

from __future__ import annotations

from qualix.quality.fabrication_detector import (
    FabricationDetectorGuardrail,
    _extract_java_identifiers,
)
from qualix.quality.guardrail import GuardrailContext
from qualix.quality.report_quality_checks import (
    check_confidence_annotations,
    check_gap_risk_level,
    check_id_format,
    check_open_decision_owner,
    check_source_annotations,
)
from qualix.quality.semantic_guardrail import ReportSemanticGuardrail

# ---------------------------------------------------------------------------
# report_quality_checks
# ---------------------------------------------------------------------------


class TestSourceAnnotations:
    def test_detects_missing_source(self):
        text = "该接口缺失幂等校验，存在重复提交风险\n"
        issues = check_source_annotations(text, "Q01")
        assert len(issues) >= 1
        assert issues[0]["check"] == "source_annotation"

    def test_passes_with_source(self):
        text = "该接口缺失幂等校验 [来源: OrderService.java:42]\n"
        issues = check_source_annotations(text, "Q01")
        assert len(issues) == 0

    def test_skips_table_headers(self):
        text = "| --- | --- | --- |\n"
        issues = check_source_annotations(text, "Q01")
        assert len(issues) == 0

    def test_skips_headings(self):
        text = "# 风险总结\n"
        issues = check_source_annotations(text, "Q01")
        assert len(issues) == 0

    def test_q05a_accepts_se_eut_as_source(self):
        text = "SE-003 对应 EUT-007 的异常路径遗漏，需补充边界测试\n"
        issues = check_source_annotations(text, "Q05a")
        assert len(issues) == 0

    def test_q07_accepts_file_line_as_source(self):
        text = "OrderService.createOrder 存在空指针风险 OrderService.java:42\n"
        issues = check_source_annotations(text, "Q07")
        assert len(issues) == 0

    def test_q01_rejects_req_id_as_source(self):
        text = "REQ-001 缺失幂等校验，存在重复提交风险\n"
        issues = check_source_annotations(text, "Q01")
        assert len(issues) >= 1
        assert issues[0]["check"] == "source_annotation"


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
        issues = check_confidence_annotations(text, "Q05a")
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
        ctx = _make_ctx(
            "Q01",
            data={
                "requirements": [{"req_id": "BR-001", "description": "需要校验"}],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed]
        assert len(warnings) >= 1
        assert "概括性描述" in warnings[0].message

    def test_br_detail_passes_with_detail(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q01",
            data={
                "requirements": [
                    {
                        "req_id": "BR-001",
                        "description": "订单金额字段必须为 BigDecimal，精度 2 位，校验范围 0.01-999999.99",
                    }
                ],
            },
        )
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

    def test_cross_phase_ok_for_q05a(self):
        g = ReportSemanticGuardrail()
        report = "EUT-001 测试用例\nEUT-002 单测\n"
        ctx = _make_ctx("Q05a", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "越权" in r.message]
        assert len(warnings) == 0

    def test_p0_unclosed_detects(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q01",
            report="整体通过，建议上线",
            data={
                "gaps": [{"gap_id": "GAP-001", "severity": "P0", "status": "open"}],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "P0" in r.message]
        assert len(warnings) >= 1

    def test_p0_closed_passes(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q01",
            report="整体通过",
            data={
                "gaps": [{"gap_id": "GAP-001", "severity": "P0", "status": "closed"}],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "P0" in r.message]
        assert len(warnings) == 0


class TestFindingsCodeEvidence:
    def test_detects_no_evidence(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q07",
            data={
                "findings": [
                    {"description": "这个方法有问题"},
                    {"description": "逻辑不对"},
                ],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "代码证据" in r.message]
        assert len(warnings) >= 1

    def test_passes_with_evidence(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q07",
            data={
                "findings": [
                    {"description": "空指针风险", "location": "OrderService.java:42"},
                ],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "代码证据" in r.message]
        assert len(warnings) == 0

    def test_skips_non_applicable_phases(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q01",
            data={
                "findings": [{"description": "无证据"}],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "代码证据" in r.message]
        assert len(warnings) == 0


class TestCoverageDescriptionVague:
    def test_detects_vague(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q04", report="REQ-001 基本覆盖，整体覆盖较好")
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "概括性描述" in r.message]
        assert len(warnings) >= 1

    def test_passes_specific(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q04", report="REQ-001 COVERED [来源: HLD 3.2 节接口定义]")
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "概括性描述" in r.message]
        assert len(warnings) == 0


class TestGapOpenClosureEmpty:
    def test_detects_empty_closure(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q04",
            data={
                "gap_closure": [
                    {"gap_id": "GAP-001", "closure_status": ""},
                    {"gap_id": "GAP-002", "closure_status": "closed"},
                ],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "闭环状态为空" in r.message]
        assert len(warnings) >= 1

    def test_passes_all_filled(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx(
            "Q04",
            data={
                "gap_closure": [
                    {"gap_id": "GAP-001", "closure_status": "closed"},
                ],
            },
        )
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "闭环状态为空" in r.message]
        assert len(warnings) == 0


class TestCodeOnlyDerivation:
    def test_detects_no_req_refs(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q06", report="OrderServiceTest 覆盖了 createOrder 方法的主流程和异常分支")
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "仅凭代码推导" in r.message]
        assert len(warnings) >= 1

    def test_passes_with_req_refs(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q06", report="REQ-001 的 SE-003 已被 OrderServiceTest 覆盖，BR-002 的边界值测试完整")
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "仅凭代码推导" in r.message]
        assert len(warnings) == 0


class TestIsolatedAnalysis:
    def test_detects_no_call_chain(self):
        g = ReportSemanticGuardrail()
        report = "OrderService.createOrder 方法存在空指针风险。\n" * 20  # >500 chars
        ctx = _make_ctx("Q07", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "孤立分析" in r.message]
        assert len(warnings) >= 1

    def test_passes_with_call_chain(self):
        g = ReportSemanticGuardrail()
        report = (
            "OrderService.createOrder 方法存在空指针风险。\n"
            "调用链: Controller → OrderService → PaymentGateway\n"
            "上游 Controller 未做参数校验导致 null 传入\n" * 10
        )
        ctx = _make_ctx("Q07", report=report)
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "孤立分析" in r.message]
        assert len(warnings) == 0

    def test_skips_short_report(self):
        g = ReportSemanticGuardrail()
        ctx = _make_ctx("Q07", report="短报告")
        results = g.check(ctx)
        warnings = [r for r in results if not r.passed and "孤立分析" in r.message]
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# fabrication_detector
# ---------------------------------------------------------------------------


class TestExtractJavaIdentifiers:
    def test_extracts_class_names(self):
        text = "OrderService 调用 PaymentGateway 处理支付"
        ids = _extract_java_identifiers(text)
        assert "OrderService" in ids["class"]
        assert "PaymentGateway" in ids["class"]

    def test_extracts_method_calls(self):
        text = "orderService.createOrder(param) 和 paymentGateway.processPayment()"
        ids = _extract_java_identifiers(text)
        assert "createOrder" in ids["method"]
        assert "processPayment" in ids["method"]

    def test_extracts_getters(self):
        text = "调用 getOrderStatus 获取状态"
        ids = _extract_java_identifiers(text)
        assert "getOrderStatus" in ids["method"]

    def test_ignores_short_names(self):
        text = "a.b() 和 Xy 不应被提取"
        ids = _extract_java_identifiers(text)
        assert len(ids["class"]) == 0
        assert len(ids["method"]) == 0


class TestFabricationDetectorGuardrail:
    def test_skips_non_code_phases(self):
        g = FabricationDetectorGuardrail()
        ctx = _make_ctx("Q01", report="OrderService 处理订单")
        results = g.check(ctx)
        assert len(results) == 0

    def test_skips_empty_report(self):
        g = FabricationDetectorGuardrail()
        ctx = _make_ctx("Q07", report="")
        results = g.check(ctx)
        assert len(results) == 0

    def test_skips_whitelisted_classes(self):
        g = FabricationDetectorGuardrail()
        # Only whitelisted Spring/Java classes
        ctx = _make_ctx("Q07", report="RestController 和 BigDecimal 和 Optional 使用正确")
        results = g.check(ctx)
        # Should not flag whitelisted items
        fabrication_warnings = [r for r in results if r.guardrail_name == "fabrication_detector"]
        assert len(fabrication_warnings) == 0

    def test_no_false_positive_without_index(self):
        """无 code_symbols 索引时不应误报."""
        g = FabricationDetectorGuardrail()
        # 大量未知类名但无索引 → 应跳过（ratio > 0.8 且 found_in_db 为空）
        report = "FooBarService 调用 BazQuxController 和 XyzRepository 处理 AbcHandler"
        ctx = _make_ctx("Q07", report=report)
        results = g.check(ctx)
        fabrication_warnings = [r for r in results if r.guardrail_name == "fabrication_detector"]
        assert len(fabrication_warnings) == 0


# ---------------------------------------------------------------------------
# rule_checks._check_traceability
# ---------------------------------------------------------------------------


class TestTraceability:
    def _setup(self, tmp_path, req_ids: list[str]):
        import json as _json

        q02_dir = tmp_path / "Q02"
        q02_dir.mkdir(parents=True)
        q01_dir = tmp_path / "Q01"
        q01_dir.mkdir(parents=True)
        (q01_dir / "phase_a_structured.json").write_text(
            _json.dumps({"requirements": [{"req_id": rid} for rid in req_ids]}),
            encoding="utf-8",
        )
        return q02_dir

    def test_all_ids_traced(self, tmp_path):
        from qualix.quality.rules.rule_checks import _check_traceability

        q02_dir = self._setup(tmp_path, ["REQ-001", "REQ-002"])
        report = "技术方案覆盖 REQ-001 和 REQ-002 的所有场景"
        passed, detail = _check_traceability(q02_dir, report, "Q02")
        assert passed
        assert "2/2" in detail

    def test_detects_missing_id(self, tmp_path):
        from qualix.quality.rules.rule_checks import _check_traceability

        q02_dir = self._setup(tmp_path, ["REQ-001", "REQ-002", "REQ-003"])
        report = "技术方案覆盖 REQ-001 和 REQ-002"
        passed, detail = _check_traceability(q02_dir, report, "Q02")
        assert not passed
        assert "REQ-003" in detail

    def test_skips_when_q01_absent(self, tmp_path):
        from qualix.quality.rules.rule_checks import _check_traceability

        q02_dir = tmp_path / "Q02"
        q02_dir.mkdir(parents=True)
        passed, detail = _check_traceability(q02_dir, "任意报告", "Q02")
        assert passed
        assert "未找到 Q01" in detail

    def test_skips_when_no_requirements(self, tmp_path):
        import json as _json

        q02_dir = tmp_path / "Q02"
        q02_dir.mkdir(parents=True)
        q01_dir = tmp_path / "Q01"
        q01_dir.mkdir(parents=True)
        (q01_dir / "phase_a_structured.json").write_text(_json.dumps({"requirements": []}), encoding="utf-8")

        from qualix.quality.rules.rule_checks import _check_traceability

        passed, _ = _check_traceability(q02_dir, "任意报告", "Q02")
        assert passed
