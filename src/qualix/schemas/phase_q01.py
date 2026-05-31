"""Phase A 数据契约: 需求结构化报告."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Confidence(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class GapRiskLevel(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class SemanticExpectation(BaseModel):
    """关键语义 SE."""

    se_id: str = Field(pattern=r"^SE-\d+$")
    description: str = Field(min_length=1)
    verification: str = Field(
        default="",
        description="判定依据：可执行的测试步骤（发什么请求 + 断言什么），应达到 se_checklist 示例对 ✓ 强度，如含 HTTP 状态码/errorCode/SQL 断言/参数化枚举",
    )
    category: str = Field(
        default="",
        description="语义类别：幂等/并发、状态迁移、数据转换、匹配冲突、跨系统口径、默认行为、时间窗口、接口约定等",
    )
    bound_reqs: list[str] = Field(default_factory=list, description="绑定的 REQ/BR ID 列表，如 ['REQ-001', 'BR-006']")
    confidence: Confidence = Field(default=Confidence.MEDIUM, description="置信度：High/Medium/Low")
    source: str = Field(default="", description="判定依据来源，如 plain_text.txt:79")
    code_target: str = Field(default="", description="代码映射目标，如 MrOrderMainService.applyEarlyDeliveryAuthStore")
    # 向后兼容旧字段
    mapped_to_req_br: bool = False
    mapping_target: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: str | Confidence) -> str | Confidence:
        if isinstance(value, Confidence):
            return value
        mapping = {
            "high": Confidence.HIGH,
            "medium": Confidence.MEDIUM,
            "low": Confidence.LOW,
            "高": Confidence.HIGH,
            "中": Confidence.MEDIUM,
            "低": Confidence.LOW,
        }
        return mapping.get(str(value).strip().lower(), value)


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
    risk_level: GapRiskLevel = Field(default=GapRiskLevel.P2, description="风险等级：P0/P1/P2")
    required_clarification: str = Field(default="", description="需补充的口径")
    owner: str = ""

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk_level(cls, value: str | GapRiskLevel) -> str | GapRiskLevel:
        if isinstance(value, GapRiskLevel):
            return value
        mapping = {
            "高": GapRiskLevel.P0,
            "中": GapRiskLevel.P1,
            "低": GapRiskLevel.P2,
            "p0": GapRiskLevel.P0,
            "p1": GapRiskLevel.P1,
            "p2": GapRiskLevel.P2,
        }
        return mapping.get(str(value).strip().lower(), value)


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

    @model_validator(mode="after")
    def check_se_bound_refs_exist(self) -> PhaseAOutput:
        """SE.bound_reqs 只能引用当前 Q01 已定义的 REQ/BR."""
        known_ids = {item.req_id for item in self.requirements}
        for se in self.semantic_expectations:
            for ref_id in se.bound_reqs:
                if ref_id not in known_ids:
                    msg = f"{se.se_id}.bound_reqs 引用了不存在的 REQ/BR: {ref_id}"
                    raise ValueError(msg)
        return self
