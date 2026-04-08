"""Phase D 数据契约: 代码评审."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ReviewSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class ReviewFinding(BaseModel):
    """评审发现条目."""

    finding_id: str = Field(min_length=1)
    file_path: str = ""
    description: str = Field(min_length=1)
    severity: ReviewSeverity
    related_req: str = ""
    suggestion: str = ""


class PhaseDOutput(BaseModel):
    """Phase D 完整产物."""

    project_id: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)
    conclusion: str = ""
