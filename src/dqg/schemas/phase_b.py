"""Phase B 数据契约: 单测生成 (EUT Matrix)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RouteType(StrEnum):
    HAPPY = "Happy Path"
    EXCEPTION = "Exception"
    BOUNDARY = "Boundary"


class RiskTier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class EutItem(BaseModel):
    """EUT 条目."""

    eut_id: str = Field(pattern=r"^EUT-\d+$")
    bound_se: str = Field(min_length=1, description="绑定的 SE ID，如 SE-001。必填。")
    route_type: RouteType
    given: str = Field(min_length=1)
    when: str = Field(min_length=1)
    then: str = Field(min_length=1)
    risk_tier: RiskTier = RiskTier.T2
    repo: str = Field(default="", description="归属仓库名，多仓库场景必填")
    se_refs: list[str] = Field(default_factory=list, description="关联的 SE ID 列表")


class TCItem(BaseModel):
    """Q05 实际产出的 TC 条目（兼容 LLM 输出格式）."""

    id: str = Field(min_length=1)
    repo: str = Field(min_length=1, description="归属仓库名")
    status: str = Field(default="", description="覆盖状态: COVERED/MISSING/PARTIAL")
    covered_by: str = Field(default="", description="覆盖该 TC 的测试方法")
    scenario: str = Field(default="", description="测试场景描述")
    se_refs: list[str] = Field(default_factory=list, description="关联的 SE ID 列表")
    layer: str = ""
    class_under_test: str = ""
    method: str = ""
    requirement: str = ""
    priority: str = ""
    existing_coverage: str = ""
    inputs: str = ""
    expected: str = ""
    br: str = ""


class PhaseBOutput(BaseModel):
    """Phase B 完整产物."""

    project_id: str = Field(min_length=1)
    eut_items: list[EutItem] = Field(default_factory=list)
    test_cases: list[TCItem] = Field(default_factory=list, description="兼容 LLM 实际输出的 TC 列表")
