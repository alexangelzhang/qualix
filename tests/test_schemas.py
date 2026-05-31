"""Tests for qualix.schemas — 数据契约校验."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from qualix.schemas import PhaseAOutput, validate_phase_output
from qualix.schemas.phase_a5 import CoverageStatus, PhaseA5Output, ReqCoverageItem
from qualix.schemas.phase_a6 import FailureModeItem, FailureModeStatus, PhaseA6Output, QualityIssue, Severity
from qualix.schemas.phase_b import EutItem, PhaseBOutput, RiskTier, RouteType, TCItem
from qualix.schemas.phase_c import AuditStatus, CoverageGate, EutAuditItem, FindingItem, PhaseCOutput
from qualix.schemas.phase_q01 import Gap, OpenItem, Requirement, SemanticExpectation


class TestPhaseASchema:
    def test_valid_output(self):
        output = PhaseAOutput(
            project_id="PROJ1",
            requirements=[
                Requirement(req_id="REQ-001", description="用户登录"),
                Requirement(req_id="BR-001", parent_id="REQ-001", description="手机号登录"),
            ],
            semantic_expectations=[
                SemanticExpectation(se_id="SE-001", description="登录后跳转首页"),
            ],
            gaps=[Gap(gap_id="GAP-001", description="短信验证码有效期未定义")],
            open_items=[OpenItem(open_id="OPEN-001", question="是否支持第三方登录")],
            conclusion="有条件通过",
        )
        assert len(output.requirements) == 2
        assert output.gaps[0].gap_id == "GAP-001"

    def test_requires_at_least_one_req(self):
        with pytest.raises(ValidationError, match="REQ 级需求点"):
            PhaseAOutput(
                project_id="PROJ1",
                requirements=[
                    Requirement(req_id="BR-001", description="只有 BR 没有 REQ"),
                ],
            )

    def test_empty_requirements_rejected(self):
        with pytest.raises(ValidationError):
            PhaseAOutput(
                project_id="PROJ1",
                requirements=[],
            )

    def test_invalid_req_id_pattern(self):
        with pytest.raises(ValidationError):
            Requirement(req_id="INVALID-001", description="bad id")

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            Requirement(req_id="REQ-001", description="")

    def test_semantic_expectation_verification_field(self):
        """verification 字段 default=''（向后兼容），且能正常读写新值。"""
        # 老数据不传 verification：default="" 兼容
        se_old = SemanticExpectation(se_id="SE-001", description="老 SE 无 verification")
        assert se_old.verification == ""

        # 新数据传 verification：正常读写
        se_new = SemanticExpectation(
            se_id="SE-002",
            description="并发幂等控制",
            verification="CountDownLatch 10 并发 POST；断言 1 次 2xx + 9 次 409+errorCode=DUPLICATE_SUBMIT",
        )
        assert "CountDownLatch" in se_new.verification
        assert "errorCode=DUPLICATE_SUBMIT" in se_new.verification

        # 从 JSON dict 构造（模拟从 phase_a_structured.json 读入）
        raw = {
            "se_id": "SE-003",
            "description": "已有 SE",
            "category": "幂等/并发",
            "bound_reqs": ["REQ-001"],
        }
        se_from_dict = SemanticExpectation.model_validate(raw)
        assert se_from_dict.verification == ""  # 历史产物不 break


class TestPhaseA5Schema:
    def test_valid_coverage(self):
        output = PhaseA5Output(
            project_id="PROJ1",
            req_coverage=[
                ReqCoverageItem(req_id="REQ-001", status=CoverageStatus.COVERED),
            ],
        )
        assert output.req_coverage[0].status == CoverageStatus.COVERED


class TestPhaseA6Schema:
    def test_valid_issues(self):
        output = PhaseA6Output(
            project_id="PROJ1",
            issues=[
                QualityIssue(issue_id="ARCH-001", description="分层违规", severity=Severity.HIGH),
            ],
            failure_modes=[
                FailureModeItem(
                    business_path="下单",
                    failure_scenario="RPC 超时",
                    has_exception_handling=True,
                    status=FailureModeStatus.SAFE,
                ),
            ],
        )
        assert output.issues[0].severity == Severity.HIGH

    def test_invalid_issue_id(self):
        with pytest.raises(ValidationError):
            QualityIssue(issue_id="WRONG-001", description="bad", severity=Severity.LOW)

    def test_normalize_failure_mode_field_names(self):
        """LLM 输出 path/scenario/impact/assessment 时自动映射."""
        data = {
            "path": "提交审批",
            "scenario": "BPM 创建超时",
            "impact": "表单状态卡在待提交",
            "assessment": "CRITICAL_GAP",
        }
        fm = FailureModeItem.model_validate(data)
        assert fm.business_path == "提交审批"
        assert fm.failure_scenario == "BPM 创建超时"
        assert fm.user_impact == "表单状态卡在待提交"
        assert fm.status == FailureModeStatus.CRITICAL_GAP
        assert fm.has_exception_handling is False


class TestPhaseBSchema:
    def test_valid_eut(self):
        output = PhaseBOutput(
            project_id="PROJ1",
            eut_items=[
                EutItem(
                    eut_id="EUT-001",
                    bound_se="SE-001",
                    route_type=RouteType.HAPPY,
                    given="正常 DTO",
                    when="提交订单",
                    then="状态变为 PROCESSING",
                    then_assertion_type="assertEquals",
                    risk_tier=RiskTier.T1,
                ),
            ],
        )
        assert output.eut_items[0].risk_tier == RiskTier.T1
        assert output.eut_items[0].bound_se == "SE-001"

    def test_valid_concurrent_eut(self):
        item = EutItem(
            eut_id="EUT-002",
            bound_item="SE-002",
            route_type=RouteType.CONCURRENT,
            given="相同 requestId 的两个并发调用",
            when="ExpensePolicy.approve(request)",
            then="asyncio.gather sends 2 calls; assert success_count == 1 and duplicate_count == 1",
            then_assertion_type="pytest_assert",
            risk_tier=RiskTier.T1,
        )
        assert item.route_type == RouteType.CONCURRENT
        assert item.then_assertion_type == "pytest_assert"

    def test_valid_typescript_expect_eut(self):
        item = EutItem(
            eut_id="EUT-003",
            bound_item="BR-003",
            route_type=RouteType.HAPPY,
            given="duplicate active rule exists",
            when="ruleService.create(payload)",
            then="expect(response.status).toBe(409); expect(response.body.errorCode).toBe('RULE_DUPLICATE')",
            then_assertion_type="expect",
        )
        assert item.then_assertion_type == "expect"

    def test_valid_go_assert_eut(self):
        item = EutItem(
            eut_id="EUT-004",
            bound_item="REQ-004",
            route_type=RouteType.HAPPY,
            given="approved request",
            when="policy.Approve(request)",
            then='require.Equal(t, "APPROVED", result.Status); require.Len(t, result.AuditLog, 1)',
            then_assertion_type="go_assert",
        )
        assert item.then_assertion_type == "go_assert"

    def test_eut_requires_bound_se(self):
        with pytest.raises(ValidationError):
            EutItem(
                eut_id="EUT-001",
                bound_se="",
                route_type=RouteType.HAPPY,
                given="正常 DTO",
                when="提交订单",
                then="状态变为 PROCESSING",
            )

    def test_valid_test_case_item(self):
        output = PhaseBOutput(
            project_id="PROJ1",
            test_cases=[
                TCItem(
                    id="TC-001",
                    repo="car-mrs",
                    status="COVERED",
                    covered_by="SomeTest#testMethod",
                    scenario="正常场景",
                    se_refs=["SE-001", "SE-002"],
                ),
            ],
        )
        assert len(output.test_cases) == 1
        assert output.test_cases[0].se_refs == ["SE-001", "SE-002"]

    def test_test_case_requires_repo(self):
        with pytest.raises(ValidationError):
            TCItem(id="TC-001", repo="")

    def test_empty_eut_and_test_cases_accepted(self):
        output = PhaseBOutput(project_id="PROJ1")
        assert output.eut_items == []
        assert output.test_cases == []


class TestPhaseCSchema:
    def test_valid_audit(self):
        output = PhaseCOutput(
            project_id="PROJ1",
            audit_items=[
                EutAuditItem(eut_id="EUT-001", status=AuditStatus.COVERED),
            ],
            coverage_gate=CoverageGate(line_coverage=85.0, branch_coverage=80.0),
            conclusion="PASS",
        )
        assert output.coverage_gate.line_coverage == 85.0

    def test_valid_finding_mode(self):
        output = PhaseCOutput(
            project_id="PROJ1",
            findings=[
                FindingItem(id="FINDING-01", severity="CRITICAL", title="download 方法零测试"),
            ],
            verdict="FAIL",
        )
        assert len(output.findings) == 1
        assert output.findings[0].severity == "CRITICAL"

    def test_normalize_finding_in_audit_items(self):
        """finding 模式的数据放在 audit_items 字段时自动转移到 findings."""
        data = {
            "project_id": "PROJ1",
            "audit_items": [
                {"id": "FINDING-01", "severity": "HIGH", "description": "test"},
            ],
        }
        output = PhaseCOutput.model_validate(data)
        assert output.audit_items == []
        assert len(output.findings) == 1
        assert output.findings[0].id == "FINDING-01"


class TestValidatePhaseOutput:
    def test_missing_dir_returns_errors(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert isinstance(result, list)
        assert len(result) == 1
        assert "产物目录不存在" in result[0]

    def test_missing_json_returns_errors(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "Q01"
        phase_dir.mkdir(parents=True)
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert isinstance(result, list)
        assert len(result) == 1
        assert "结构化产物文件不存在" in result[0]

    def test_valid_json_passes(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "Q01"
        phase_dir.mkdir(parents=True)

        data = {
            "project_id": "PROJ1",
            "requirements": [
                {"req_id": "REQ-001", "description": "用户登录"},
            ],
            "conclusion": "通过",
        }
        (phase_dir / "phase_a_structured.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result == []

    def test_invalid_json_returns_errors(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "Q01"
        phase_dir.mkdir(parents=True)

        data = {
            "project_id": "PROJ1",
            "requirements": [],  # min_length=1 violation
        }
        (phase_dir / "phase_a_structured.json").write_text(json.dumps(data), encoding="utf-8")
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is not None
        assert len(result) > 0

    def test_malformed_json(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "Q01"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase_a_structured.json").write_text("{bad json", encoding="utf-8")
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is not None
        assert any("JSON" in e for e in result)

    def test_unknown_phase(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = validate_phase_output(output_dir, "PROJ1", "Z")
        # 未注册 Phase 返回 None（不支持校验），而非报错
        assert result is None
