"""Phase A.5 数据契约: 技术方案覆盖度审计."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CoverageStatus(StrEnum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    IMPLICIT = "IMPLICIT"


class ClosureStatus(StrEnum):
    CLOSED = "已闭环"
    PARTIAL = "部分闭环"
    UNCLOSED = "未闭环"


class ReqCoverageItem(BaseModel):
    """REQ 级覆盖条目."""

    req_id: str = Field(pattern=r"^REQ-\d+$")
    status: CoverageStatus
    notes: str = ""


class BrCoverageItem(BaseModel):
    """BR 级覆盖条目."""

    br_id: str = Field(pattern=r"^BR-\d+$")
    status: CoverageStatus
    notes: str = ""


class SeCoverageItem(BaseModel):
    """SE 级覆盖条目."""

    se_id: str = Field(pattern=r"^SE-\d+$")
    status: CoverageStatus
    failure_impact: str = ""
    notes: str = ""


class GapClosureItem(BaseModel):
    """GAP 闭环条目."""

    gap_id: str = Field(pattern=r"^GAP-\d+$")
    status: ClosureStatus


class OpenClosureItem(BaseModel):
    """OPEN 闭环条目."""

    open_id: str = Field(pattern=r"^OPEN-\d+$")
    status: ClosureStatus


class CoverageSummary(BaseModel):
    """覆盖度统计."""

    dimension: str
    total: int = Field(ge=0)
    covered: int = Field(ge=0, default=0)
    partial: int = Field(ge=0, default=0)
    missing: int = Field(ge=0, default=0)
    implicit: int = Field(ge=0, default=0)
    coverage_rate: float = Field(ge=0.0, le=1.0, default=0.0)


class PhaseA5Output(BaseModel):
    """Phase A.5 完整产物."""

    project_id: str = Field(min_length=1)
    req_coverage: list[ReqCoverageItem] = Field(default_factory=list)
    br_coverage: list[BrCoverageItem] = Field(default_factory=list)
    se_coverage: list[SeCoverageItem] = Field(default_factory=list)
    gap_closure: list[GapClosureItem] = Field(default_factory=list)
    open_closure: list[OpenClosureItem] = Field(default_factory=list)
    coverage_summary: list[CoverageSummary] = Field(default_factory=list)
    conclusion: str = ""
