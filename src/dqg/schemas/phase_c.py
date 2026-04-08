"""Phase C 数据契约: 单测覆盖审计."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AuditStatus(StrEnum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WRONG_TARGET = "WRONG_TARGET"


class EutAuditItem(BaseModel):
    """EUT 审计条目."""

    eut_id: str = Field(pattern=r"^EUT-\d+$")
    status: AuditStatus
    test_class: str = ""
    notes: str = ""


class CoverageGate(BaseModel):
    """覆盖率门禁."""

    line_coverage: float | None = Field(default=None, ge=0.0, le=100.0)
    branch_coverage: float | None = Field(default=None, ge=0.0, le=100.0)


class PhaseCOutput(BaseModel):
    """Phase C 完整产物."""

    project_id: str = Field(min_length=1)
    audit_items: list[EutAuditItem] = Field(default_factory=list)
    coverage_gate: CoverageGate = Field(default_factory=CoverageGate)
    conclusion: str = ""
