"""Phase A.3 数据契约: 技术方案生成."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReqMapping(BaseModel):
    """需求→技术设计映射."""

    req_id: str = Field(min_length=1)
    design_ref: str = Field(min_length=1)
    coverage: str = Field(pattern=r"^(full|partial|gap)$")


class InterfaceDesign(BaseModel):
    """接口设计."""

    name: str = Field(min_length=1)
    type: str = Field(pattern=r"^(command|query)$")
    description: str = ""
    idempotent: bool = False
    transaction_boundary: str = ""
    risks: list[str] = Field(default_factory=list)


class DataModelDesign(BaseModel):
    """数据模型设计."""

    table: str = Field(min_length=1)
    description: str = ""
    key_fields: list[str] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)


class GapHandling(BaseModel):
    """GAP 处理."""

    id: str = Field(pattern=r"^GAP-\d+$")
    handling: str = Field(pattern=r"^(designed|pending|blocked)$")
    risk: str = Field(pattern=r"^P[0-2]$")
    solution: str = ""


class PhaseA3Output(BaseModel):
    """Phase A.3 完整产物."""

    phase: str = Field(default="Q02")
    project_id: str = Field(min_length=1)
    architecture_style: str = Field(min_length=1)
    req_mapping: list[ReqMapping] = Field(default_factory=list)
    interfaces: list[InterfaceDesign] = Field(default_factory=list)
    data_models: list[DataModelDesign] = Field(default_factory=list)
    gaps: list[GapHandling] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
