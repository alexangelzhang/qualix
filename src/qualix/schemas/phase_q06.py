"""Phase C 数据契约: 单测覆盖审计."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from qualix.schemas.evidence import EvidenceCitation
from qualix.schemas.location import SourceLocation


class AuditStatus(StrEnum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WRONG_TARGET = "WRONG_TARGET"
    CONFLICT = "CONFLICT"


class EutAuditItem(BaseModel):
    """EUT 审计条目（兼容 EUT 逐条和 SE-based 汇总两种模式）."""

    id: str = ""
    se_id: str = ""
    eut_id: str = Field(pattern=r"^EUT-\d+([\s,~]+(\d+|EUT-\d+))*$")
    description: str = ""
    status: AuditStatus
    test_class: str = ""
    test_method: str = ""
    assertion_strength: str = ""
    source: str = ""
    notes: str = ""
    tc_id: str = ""
    repo: str = ""
    evidence: str = ""
    evidence_citations: list[EvidenceCitation] = Field(
        default_factory=list,
        description=(
            "Read-only file-line evidence candidates for this EUT. "
            "These citations do not decide COVERED/PARTIAL/MISSING; Q06 audit logic still owns the verdict."
        ),
    )
    recommendation: str = ""
    issues: list[str] = Field(default_factory=list)
    test_location: SourceLocation | None = None
    production_location: SourceLocation | None = None


class FindingItem(BaseModel):
    """审计发现条目（finding 模式，兼容 LLM 输出）."""

    id: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    category: str = ""
    title: str = ""
    description: str = ""
    impact: str = ""
    affected_reqs: list[str] = Field(default_factory=list)
    evidence: dict | str = Field(default="")
    recommendation: str = ""
    production_location: SourceLocation | None = None


class CoverageGate(BaseModel):
    """覆盖率门禁."""

    line_coverage: float | None = Field(default=None, ge=0.0, le=100.0)
    branch_coverage: float | None = Field(default=None, ge=0.0, le=100.0)


class PhaseCOutput(BaseModel):
    """Phase C 完整产物.

    支持两种模式:
    - audit 模式: audit_items 包含 EutAuditItem（eut_id/status/test_class）
    - finding 模式: findings 包含 FindingItem（id/severity/description）
    """

    project_id: str = Field(min_length=1)
    audit_items: list[EutAuditItem] = Field(default_factory=list)
    findings: list[FindingItem] = Field(default_factory=list)
    coverage_gate: CoverageGate = Field(default_factory=CoverageGate)
    conclusion: str = ""
    summary: dict = Field(default_factory=dict)
    verdict: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_audit_items(cls, data: dict) -> dict:
        """将 finding 模式的 audit_items 转移到 findings 字段."""
        if not isinstance(data, dict):
            return data
        items = data.get("audit_items", [])
        if items and isinstance(items[0], dict) and "id" in items[0] and "eut_id" not in items[0]:
            data["findings"] = items
            data["audit_items"] = []
        return data
