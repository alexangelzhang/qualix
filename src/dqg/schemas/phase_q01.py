"""Phase A 数据契约: 需求结构化报告."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SemanticExpectation(BaseModel):
    """关键语义 SE."""

    se_id: str = Field(pattern=r"^SE-\d+$")
    description: str = Field(min_length=1)
    category: str = ""
    mapped_to_req_br: bool = False
    mapping_target: str = ""


class Requirement(BaseModel):
    """需求点 REQ 或分支需求 BR."""

    req_id: str = Field(pattern=r"^(REQ|BR)-\d+$")
    parent_id: str = ""
    description: str = Field(min_length=1)
    trigger: str = ""
    behavior_change: str = ""
    acceptance_criteria: str = ""
    priority: str = ""


class Gap(BaseModel):
    """明显缺口 GAP."""

    gap_id: str = Field(pattern=r"^GAP-\d+$")
    related_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    required_clarification: str = ""
    owner: str = ""


class OpenItem(BaseModel):
    """待确认项 OPEN."""

    open_id: str = Field(pattern=r"^OPEN-\d+$")
    related_ids: list[str] = Field(default_factory=list)
    question: str = Field(min_length=1)
    options: str = ""
    decision_owner: str = ""


class PhaseAOutput(BaseModel):
    """Phase A 完整产物."""

    project_id: str = Field(min_length=1)
    requirements: list[Requirement] = Field(min_length=1)
    semantic_expectations: list[SemanticExpectation] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    open_items: list[OpenItem] = Field(default_factory=list)
    conclusion: str = ""

    @model_validator(mode="after")
    def check_req_has_at_least_one_req(self) -> PhaseAOutput:
        """至少有一个 REQ 级需求（非 BR）."""
        has_req = any(r.req_id.startswith("REQ-") for r in self.requirements)
        if not has_req:
            msg = "requirements 中至少需要一个 REQ 级需求点"
            raise ValueError(msg)
        return self
