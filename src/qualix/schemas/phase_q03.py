"""Phase A.6 数据契约: 技术方案质量评审."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


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
    dimension: str = ""
    evidence: str = ""


class FailureModeItem(BaseModel):
    """Failure Mode 分析条目."""

    business_path: str = Field(min_length=1)
    failure_scenario: str = Field(min_length=1)
    has_exception_handling: bool = False
    user_impact: str = ""
    status: FailureModeStatus

    @model_validator(mode="before")
    @classmethod
    def _normalize_field_names(cls, data: dict) -> dict:
        """兼容 LLM 输出的字段名（path/scenario/impact/assessment）."""
        if not isinstance(data, dict):
            return data
        if "path" in data and "business_path" not in data:
            data["business_path"] = data.pop("path")
        if "scenario" in data and "failure_scenario" not in data:
            data["failure_scenario"] = data.pop("scenario")
        if "impact" in data and "user_impact" not in data:
            data["user_impact"] = data.pop("impact")
        if "assessment" in data and "status" not in data:
            data["status"] = data.pop("assessment")
        return data


class PhaseA6Output(BaseModel):
    """Phase A.6 完整产物."""

    project_id: str = Field(min_length=1)
    issues: list[QualityIssue] = Field(default_factory=list)
    failure_modes: list[FailureModeItem] = Field(default_factory=list)
    conclusion: str = ""
