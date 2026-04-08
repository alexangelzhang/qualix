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
    bound_se: str = ""
    route_type: RouteType
    given: str = Field(min_length=1)
    when: str = Field(min_length=1)
    then: str = Field(min_length=1)
    risk_tier: RiskTier = RiskTier.T2


class PhaseBOutput(BaseModel):
    """Phase B 完整产物."""

    project_id: str = Field(min_length=1)
    eut_items: list[EutItem] = Field(min_length=1)
