"""Tests for dqg.schemas — 数据契约校验."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dqg.schemas import PhaseAOutput, validate_phase_output
from dqg.schemas.phase_q01 import Gap, OpenItem, Requirement, SemanticExpectation
from dqg.schemas.phase_a5 import CoverageStatus, PhaseA5Output, ReqCoverageItem
from dqg.schemas.phase_a6 import FailureModeItem, FailureModeStatus, PhaseA6Output, QualityIssue, Severity
from dqg.schemas.phase_b import EutItem, PhaseBOutput, RiskTier, RouteType
from dqg.schemas.phase_c import AuditStatus, CoverageGate, EutAuditItem, PhaseCOutput


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


class TestPhaseBSchema:
    def test_valid_eut(self):
        output = PhaseBOutput(
            project_id="PROJ1",
            eut_items=[
                EutItem(
                    eut_id="EUT-001",
                    route_type=RouteType.HAPPY,
                    given="正常 DTO",
                    when="提交订单",
                    then="状态变为 PROCESSING",
                    risk_tier=RiskTier.T1,
                ),
            ],
        )
        assert output.eut_items[0].risk_tier == RiskTier.T1

    def test_empty_eut_rejected(self):
        with pytest.raises(ValidationError):
            PhaseBOutput(project_id="PROJ1", eut_items=[])


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


class TestValidatePhaseOutput:
    def test_missing_dir_returns_none(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is None

    def test_missing_json_returns_none(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "phaseA"
        phase_dir.mkdir(parents=True)
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is None

    def test_valid_json_passes(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "phaseA"
        phase_dir.mkdir(parents=True)

        data = {
            "project_id": "PROJ1",
            "requirements": [
                {"req_id": "REQ-001", "description": "用户登录"},
            ],
            "conclusion": "通过",
        }
        (phase_dir / "phase_a_structured.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result == []

    def test_invalid_json_returns_errors(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "phaseA"
        phase_dir.mkdir(parents=True)

        data = {
            "project_id": "PROJ1",
            "requirements": [],  # min_length=1 violation
        }
        (phase_dir / "phase_a_structured.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is not None
        assert len(result) > 0

    def test_malformed_json(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        phase_dir = output_dir / "PROJ1" / "phaseA"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase_a_structured.json").write_text("{bad json", encoding="utf-8")
        result = validate_phase_output(output_dir, "PROJ1", "Q01")
        assert result is not None
        assert any("JSON" in e for e in result)

    def test_unknown_phase(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = validate_phase_output(output_dir, "PROJ1", "Z")
        assert result is not None
        assert any("未知" in e for e in result)
