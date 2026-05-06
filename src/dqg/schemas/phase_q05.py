"""Phase B 数据契约: 单测生成 (EUT Matrix)."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from dqg.schemas.location import SourceLocation  # noqa: TC001

# EUT then 字段模糊描述黑名单（匹配到即拒绝）
_VAGUE_THEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^验证成功$",
        r"^验证结果$",
        r"^检查结果$",
        r"^确认正确$",
        r"^确认成功$",
        r"^验证通过$",
        r"^测试通过$",
        r"^结果正确$",
        r"^符合预期$",
        r"^正常返回$",
        r"^返回成功$",
        r"^执行成功$",
        r"^功能正常$",
        r"^断言通过$",
    ]
]

# EUT then 字段具体性白名单（至少匹配一个才算具体）
_CONCRETE_THEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"assert\w+",  # assertEquals, assertThrows, ...
        r"verify\s*\(",  # Mockito.verify
        r"(等于|==|!=|>=|<=|>|<)",  # 比较操作
        r"(返回|return).*\d",  # 返回具体值
        r"(状态|status).*[A-Z_]{2,}",  # 状态枚举
        r"(抛出|throw).*Exception",  # 具体异常
        r"(为|是)\s*(null|空|0|false|true)",  # 具体值
        r"\d+(\.\d+)?",  # 包含数字
        r"(次|times|never|once)",  # 调用次数
        r"(包含|contains|不包含)",  # 集合断言
        r"(大小|size|长度|length)\s*[=><]",  # 集合大小
    ]
]


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

    @field_validator("then")
    @classmethod
    def then_must_be_concrete(cls, v: str) -> str:
        """拒绝模糊的 then 描述，要求包含具体断言或值."""
        stripped = v.strip()
        for pat in _VAGUE_THEN_PATTERNS:
            if pat.search(stripped):
                raise ValueError(
                    f"EUT then 字段过于模糊: '{stripped}'。"
                    "请写明具体断言（如 assertEquals(APPROVED, status)）或预期值。"
                )
        if not any(pat.search(stripped) for pat in _CONCRETE_THEN_PATTERNS):
            raise ValueError(
                f"EUT then 字段缺少具体性: '{stripped}'。需包含断言方法、具体值、状态码、异常类型等可验证内容。"
            )
        return v


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
    test_location: SourceLocation | None = None
    production_location: SourceLocation | None = None


class PhaseBOutput(BaseModel):
    """Phase B 完整产物."""

    project_id: str = Field(min_length=1)
    eut_items: list[EutItem] = Field(default_factory=list)
    test_cases: list[TCItem] = Field(default_factory=list, description="兼容 LLM 实际输出的 TC 列表")
