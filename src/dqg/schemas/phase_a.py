"""Phase A 数据契约: 需求结构化报告."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SemanticExpectation(BaseModel):
    """关键语义 SE."""

    se_id: str = Field(pattern=r"^SE-\d+$")
    description: str = Field(min_length=1)
    category: str = Field(
        default="",
        description="语义类别：幂等/并发、状态迁移、数据转换、匹配冲突、跨系统口径、默认行为、时间窗口、接口约定等",
    )
    bound_reqs: list[str] = Field(default_factory=list, description="绑定的 REQ/BR ID 列表，如 ['REQ-001', 'BR-006']")
    confidence: str = Field(default="", description="置信度：高/中/低")
    source: str = Field(default="", description="判定依据来源，如 plain_text.txt:79")
    code_target: str = Field(default="", description="代码映射目标，如 MrOrderMainService.applyEarlyDeliveryAuthStore")
    # 向后兼容旧字段
    mapped_to_req_br: bool = False
    mapping_target: str = ""


class Requirement(BaseModel):
    """需求点 REQ 或分支需求 BR."""

    req_id: str = Field(pattern=r"^(REQ|BR)-\d+$")
    parent_id: str = ""
    description: str = Field(min_length=1)
    trigger: str = Field(default="", description="触发条件")
    behavior_change: str = Field(default="", description="行为变化")
    acceptance_criteria: str = Field(default="", description="验收标准")
    priority: str = Field(default="", description="优先级：P0/P1/P2")
    source: str = Field(default="", description="来源引用，如 plain_text.txt:79")


class Gap(BaseModel):
    """明显缺口 GAP."""

    gap_id: str = Field(pattern=r"^GAP-\d+$")
    related_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    risk_level: str = Field(default="", description="风险等级：高/中/低")
    required_clarification: str = Field(default="", description="需补充的口径")
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
