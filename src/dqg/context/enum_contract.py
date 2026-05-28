"""枚举与 ID 契约单一真源（T7），注入 Worker prompt 首部.

权威值与 `src/dqg/schemas/phase_*.py` 对齐；禁止在 skill 示例中自造枚举词。
"""

from __future__ import annotations

from typing import Final


class EnumSource:
    """文档化 + 程序引用的枚举常量（与 Pydantic StrEnum 一致）."""

    Q03_SEVERITY: Final[tuple[str, ...]] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    Q03_FAILURE_MODE_STATUS: Final[tuple[str, ...]] = ("SAFE", "RISK", "CRITICAL_GAP")
    Q03_ISSUE_ID_PATTERN: Final[str] = r"^(ARCH|API|DATA|EXC|PERF)-\d+$"

    Q01_REQ_BR_ID_PATTERN: Final[str] = r"^(REQ|BR)-\d+$"
    Q01_SE_ID_PATTERN: Final[str] = r"^SE-\d+$"

    Q06_AUDIT_STATUS: Final[tuple[str, ...]] = (
        "COVERED",
        "PARTIAL",
        "MISSING",
        "WRONG_TARGET",
        "CONFLICT",
    )

    Q05_ROUTE_TYPES: Final[tuple[str, ...]] = ("Happy Path", "Exception", "Boundary")
    Q05_RISK_TIERS: Final[tuple[str, ...]] = ("T1", "T2", "T3")
    Q05_EUT_ID_PATTERN: Final[str] = r"^EUT-\d+$"


def render_enum_contract_prefix(phase_id: str) -> str:
    """生成注入 skill 前的 Markdown 块；无定义时返回空串."""
    if phase_id == "Q03":
        return _q03_block()
    if phase_id == "Q01":
        return _q01_block()
    if phase_id == "Q06":
        return _q06_block()
    if phase_id in {"Q05", "Q05a"}:
        return _q05_block()
    return ""


def _q03_block() -> str:
    s = ", ".join(EnumSource.Q03_SEVERITY)
    fm = ", ".join(EnumSource.Q03_FAILURE_MODE_STATUS)
    return (
        "<!-- ENUM_CONTRACT:Q03 — 与 phase_q03.py 同源，禁止自造词 -->\n"
        "## 枚举契约（Q03）\n\n"
        f"- **issues[].severity** 仅允许: `{s}`\n"
        f"- **issues[].issue_id** 正则: `{EnumSource.Q03_ISSUE_ID_PATTERN}`\n"
        f"- **failure_modes[].status** 仅允许: `{fm}`\n"
        "- **failure_modes[]** 必填: `business_path`, `failure_scenario`, `has_exception_handling`, `status`\n"
    )


def _q01_block() -> str:
    return (
        "<!-- ENUM_CONTRACT:Q01 -->\n"
        "## 枚举与 ID 契约（Q01）\n\n"
        f"- **requirements[].req_id** 扁平 ID，正则: `{EnumSource.Q01_REQ_BR_ID_PATTERN}`（禁止 `BR-001-01` 嵌套）\n"
        f"- **semantic_expectations[].se_id** 正则: `{EnumSource.Q01_SE_ID_PATTERN}`\n"
    )


def _q06_block() -> str:
    st = ", ".join(f"`{x}`" for x in EnumSource.Q06_AUDIT_STATUS)
    return (
        "<!-- ENUM_CONTRACT:Q06 -->\n"
        "## 枚举契约（Q06）\n\n"
        f"- **audit_items[].status** 仅允许: {st}\n"
        "- **findings[]** 每条必填: `id`, `severity`（禁止整段缺失）\n"
        "- **audit_items[].eut_id** 必须可追溯到 Q05 `eut_items`\n"
    )


def _q05_block() -> str:
    rt = ", ".join(f"`{x}`" for x in EnumSource.Q05_ROUTE_TYPES)
    rk = ", ".join(EnumSource.Q05_RISK_TIERS)
    return (
        "<!-- ENUM_CONTRACT:Q05 -->\n"
        "## 枚举契约（Q05）\n\n"
        f"- **eut_items[].route_type** 仅允许: {rt}\n"
        f"- **eut_items[].risk_tier** 仅允许: `{rk}`\n"
        f"- **eut_items[].eut_id** 正则: `{EnumSource.Q05_EUT_ID_PATTERN}`\n"
        "- **eut_items[].bound_se** 必填，须为 Q01 已存在 SE/REQ\n"
    )
