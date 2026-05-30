"""Phase Q06 规则检查函数（单测覆盖审计 7 维度）."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from .rule_definitions import RE_SE_ID


def _check_c_se_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """SE 覆盖率：审计报告是否评估了 SE 覆盖情况."""
    se_refs = len(RE_SE_ID.findall(report))
    has_coverage_table = "SE 覆盖" in report or "se_coverage" in report or "SE.*覆盖率" in report
    if se_refs >= 5 or has_coverage_table:
        return True, f"{se_refs} 处 SE 引用，有覆盖评估"
    return False, f"仅 {se_refs} 处 SE 引用（要求审计报告评估 SE 覆盖率）"


def _check_c_path_balance(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """路径覆盖：是否评估了 Happy/Exception/Boundary 三种路径."""
    has_happy = "Happy" in report or "正常" in report or "happy" in report.lower()
    has_exception = "Exception" in report or "异常" in report or "exception" in report.lower()
    has_boundary = "Boundary" in report or "边界" in report or "boundary" in report.lower()
    covered = sum([has_happy, has_exception, has_boundary])
    if covered >= 2:
        types = [
            t for t, flag in [("Happy", has_happy), ("Exception", has_exception), ("Boundary", has_boundary)] if flag
        ]
        return True, f"覆盖 {'/'.join(types)}"
    return False, f"仅覆盖 {covered}/3 种路径类型"


def _check_c_assert_strength(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """断言强度：是否评估了断言质量."""
    keywords = [
        "断言强度",
        "assertEquals",
        "assertThrows",
        "assertNotNull",
        "弱断言",
        "强断言",
        "ArgumentCaptor",
        "verify",
    ]
    found = sum(1 for kw in keywords if kw in report)
    if found >= 3:
        return True, f"断言分析充分（{found} 个关键词）"
    return False, f"断言分析不足（仅 {found} 个关键词）"


def _check_c_mock_reality(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """Mock 真实性：是否评估了 Mock 数据质量."""
    keywords = ["Mock 真实", "mock.*真实", "BigDecimal", "email", "RpcContext", "Mock 数据", "贴近业务"]
    found = sum(1 for kw in keywords if kw.lower() in report.lower() or kw in report)
    if found >= 2:
        return True, "Mock 真实性已评估"
    if "Mock" in report or "mock" in report:
        return True, "有 Mock 相关分析"
    return False, "未评估 Mock 数据真实性"


def _check_c_state_machine(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """状态机覆盖：是否评估了状态迁移测试."""
    keywords = ["状态机", "状态迁移", "状态流转", "StatusTransition", "stateDiagram"]
    if any(kw in report for kw in keywords):
        return True, "状态机覆盖已评估"
    return True, "未涉及状态机（跳过）"


def _check_c_maintainability(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """可维护性：是否评估了测试结构."""
    keywords = ["可维护", "Nested", "DisplayName", "测试结构", "命名", "工具方法"]
    found = sum(1 for kw in keywords if kw in report)
    if found >= 2:
        return True, f"可维护性已评估（{found} 个维度）"
    if found >= 1:
        return True, "有可维护性分析"
    return False, "未评估测试可维护性"


def _check_c_boundary(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """边界场景：是否评估了边界测试覆盖."""
    keywords = ["边界", "Boundary", "空值", "不存在", "越界", "null", "empty", "除零", "溢出", "并发"]
    found = sum(1 for kw in keywords if kw in report)
    if found >= 3:
        return True, f"边界场景分析充分（{found} 个关键词）"
    if found >= 1:
        return True, f"有边界分析（{found} 个关键词）"
    return False, "未评估边界场景覆盖"


def _check_c_defensive(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """防御性测试：是否评估了系统不崩溃的防御性测试."""
    keywords = ["防御", "NPE", "null入参", "空参数", "分页越界", "系统不崩溃", "defensive", "不抛异常", "兜底", "降级"]
    found = sum(1 for kw in keywords if kw.lower() in report.lower())
    if found >= 2:
        return True, f"防御性测试已评估（{found} 个关键词）"
    if found >= 1:
        return True, f"有防御性分析（{found} 个关键词）"
    if "assertNotNull" in report or "NullPointer" in report:
        return True, "有 NPE 防御相关分析"
    return False, "未评估防御性测试（系统不崩溃）"
