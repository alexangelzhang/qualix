"""Phase A.6 数据契约: 技术方案质量评审."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureModeStatus(StrEnum):
    SAFE = "SAFE"
    RISK = "RISK"
    CRITICAL_GAP = "CRITICAL_GAP"


class QualityIssue(BaseModel):
    """质量问题条目."""

    issue_id: str = Field(pattern=r"^(ARCH|API|DATA|EXC|PERF)-\d+$")
    description: str = Field(min_length=1)
    severity: Severity
    suggestion: str = ""


class FailureModeItem(BaseModel):
    """Failure Mode 分析条目."""

    business_path: str = Field(min_length=1)
    failure_scenario: str = Field(min_length=1)
    has_exception_handling: bool
    user_impact: str = ""
    status: FailureModeStatus


class PhaseA6Output(BaseModel):
    """Phase A.6 完整产物."""

    project_id: str = Field(min_length=1)
    issues: list[QualityIssue] = Field(default_factory=list)
    failure_modes: list[FailureModeItem] = Field(default_factory=list)
    conclusion: str = ""
