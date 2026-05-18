"""Phase B 数据契约: 单测生成 (EUT Matrix)."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from dqg.schemas.location import SourceLocation

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
        # 空气断言：常量比较，无业务语义
        r"assertEquals\s*\(\s*\d+\s*,\s*\d+\s*\)",  # assertEquals(1, 1)
        r"assertTrue\s*\(\s*true\s*\)",  # assertTrue(true)
        r"assertFalse\s*\(\s*false\s*\)",  # assertFalse(false)
        # 过弱断言：只验证非空/非null，没有业务值（后面没有其他断言）
        r"^assertNotNull\s*\([^;；]+\)\s*[;；]?\s*$",  # 只有 assertNotNull，无后续断言（行末）
        r"^assertNull\s*\([^;；]+\)\s*[;；]?\s*$",  # 只有 assertNull，无后续断言（行末）
        r"^assertTrue\s*\(result\s*!=\s*null\)\s*[;；]?\s*$",  # assertTrue(result != null) 单独一行
    ]
]

# EUT then 字段具体性白名单（至少匹配一个才算具体）
# 要求包含可验证的业务断言：具体值/业务枚举/异常类型/调用次数
# 已收窄：纯比较运算符（trivially true）升级为"比较 + 具体值"
_CONCRETE_THEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"assertEquals\s*\([^,)]+,\s*[^)]+\)",  # assertEquals(expected, actual)
        r"assertThrows\s*\([A-Za-z]{4,}Exception",  # assertThrows(具体异常类) — 排除 Exception.class
        r"verify\s*\(",  # Mockito.verify（含 times/never 的形态）
        r"(状态|status|state)\s*.{0,10}\b[A-Z_]{3,}\b",  # 状态枚举（需有"状态/status"上下文）
        r"(等于|==|!=|>=|<=|>|<)\s*\w+",  # 比较后必须有操作数（去掉裸运算符）
        r"(返回|return).{0,20}\d{1,}",  # 返回 + 具体数字（如 code 200）
        r"(抛出|throw|throws|抛异常).{0,20}Exception",  # 抛出 + 异常类
        r"(为|是|==)\s*(null|空|false|true|0)\b",  # 确定性布尔/null/零
        r"\b[A-Z][A-Z_]{2,}\b",  # 业务枚举（≥3字符全大写）
        r"(次|times|never|once)\b",  # 调用次数语义
        r"(包含|contains|containsExactly|不包含|isEmpty\s*\(\))",  # 集合内容
        r"(大小|size\s*\(\)|长度|length\s*\(\))\s*[=><]=?\s*\d",  # 集合大小与数字
        r"errorCode\s*[=!]=",  # 错误码
        r"getMessage\(\).{0,20}含",  # 异常消息包含
        r"assertThat\s*\(.+\)\s*\.is",  # AssertJ 链式
        r"assertIterableEquals|assertArrayEquals",  # 集合/数组比较
        r"\.(get[A-Z]\w+|is[A-Z]\w+)\s*\(\)\s*[=!]=\s*\S",  # getter 对比
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
    bound_item: str = Field(
        min_length=1,
        description="绑定的需求条目 ID，支持 REQ-001/BR-007/SE-003 三种格式。必填。",
    )
    # 向后兼容字段——自动与 bound_item 双向同步，新代码请用 bound_item
    bound_se: str = Field(
        default="",
        description="[已废弃] 请使用 bound_item。向后兼容保留。",
    )
    route_type: RouteType
    given: str = Field(min_length=1)
    when: str = Field(min_length=1)
    then: str = Field(min_length=1)
    risk_tier: RiskTier = RiskTier.T2
    repo: str = Field(default="", description="归属仓库名，多仓库场景必填")
    se_refs: list[str] = Field(default_factory=list, description="关联的 SE ID 列表")

    @model_validator(mode="before")
    @classmethod
    def sync_bound_item_and_bound_se(cls, values: dict) -> dict:
        """双向迁移：旧格式 bound_se → bound_item；新格式 bound_item → 填充 bound_se 供旧代码读取."""
        bi = values.get("bound_item", "")
        bs = values.get("bound_se", "")
        if not bi and bs:
            values["bound_item"] = bs
        if bi and not bs:
            values["bound_se"] = bi
        return values

    @field_validator("bound_item")
    @classmethod
    def validate_bound_item_format(cls, v: str) -> str:
        """bound_item 必须是 REQ-NNN / BR-NNN / SE-NNN 格式."""
        if not re.match(r"^(REQ|BR|SE)-\d+$", v.strip()):
            raise ValueError(
                f"bound_item '{v}' 格式无效。须为 REQ-001 / BR-007 / SE-003 格式，对应 Q01 产出的 REQ/BR/SE 条目 ID。"
            )
        return v

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
        # P0-2: assertThrows 必须是具体业务异常类，不能是基类 Exception/RuntimeException
        _BASE_EXC = re.compile(r"assertThrows\s*\(\s*(Exception|RuntimeException|Throwable)\.class", re.IGNORECASE)
        if _BASE_EXC.search(stripped):
            raise ValueError(
                f"assertThrows 必须指定具体业务异常类，不能用 Exception/RuntimeException/Throwable: '{stripped}'。"
                "请改为具体类（如 MafSrvAftersaleException.class、BusinessException.class）。"
            )
        return v

    @model_validator(mode="after")
    def exception_eut_must_have_postcondition(self) -> EutItem:
        """Fix-2: Exception EUT 在 assertThrows 之外还必须有后置状态/副作用断言.

        SKILL.md 3.3：异常后必须补充业务效果断言（状态未变更、数据未写入、事务已回滚）。
        若 then 只有 assertThrows 而无 verify/assertEquals/状态检查，视为不完整异常测试。
        """
        if self.route_type != RouteType.EXCEPTION:
            return self
        then = (self.then or "").strip()
        _HAS_THROWS = re.compile(r"assertThrows\s*\(", re.IGNORECASE)
        _HAS_POSTCOND = re.compile(
            r"\b(verify\s*\(|assertEquals\s*\(|assertThat\s*\(|assertSame\s*\(|assertNull\s*\(|assertFalse\s*\(|状态未变|数据未写|未调用|never\s*\(|times\s*\(\s*0)",
            re.IGNORECASE,
        )
        if _HAS_THROWS.search(then) and not _HAS_POSTCOND.search(then):
            raise ValueError(
                f"Exception EUT then 字段缺少后置状态断言: '{then[:80]}'。\n"
                "SKILL.md 3.3 要求：assertThrows 后必须补充业务效果断言，例如：\n"
                "  verify(mock, never()).save(any()) — 数据未写入\n"
                "  assertEquals(INIT, state.getStatus()) — 状态未变更\n"
                "  verify(srvServiceExtendManager, never()).delete(...) — 副作用未执行"
            )
        return self


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
