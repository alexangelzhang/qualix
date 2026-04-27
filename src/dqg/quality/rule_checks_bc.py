"""Phase Q05/Q06 规则检查函数.

从 rule_checks.py 拆分，包含单测生成（Q05）和单测审计（Q06）的检查函数。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from dqg.quality.rule_definitions import RE_BR_ID, RE_REQ_ID, RE_SE_ID

# ---------------------------------------------------------------------------
# Phase Q05 检查
# ---------------------------------------------------------------------------


def _check_design_matrix(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查单测设计矩阵是否存在."""
    from dqg.json_utils import load_json

    matrix_path = pd.parent / "_test_design_matrix.json"
    if not matrix_path.exists():
        matrix_path = pd / "_test_design_matrix.json"
    if matrix_path.exists():
        data = load_json(matrix_path)
        if data and data.get("summary"):
            total = data["summary"].get("total_test_cases", 0)
            return True, f"设计矩阵存在（{total} 个用例）"
        return True, "设计矩阵存在"
    if "test_design_matrix" in report or "req_coverage" in report or "设计矩阵" in report:
        return True, "有设计矩阵内容"
    return False, "单测设计矩阵（_test_design_matrix.json）不存在"


def _check_req_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 REQ 覆盖率."""
    from dqg.json_utils import load_json

    for candidate in [pd.parent / "_test_design_matrix.json", pd / "_test_design_matrix.json"]:
        data = load_json(candidate)
        if data and data.get("summary"):
            total = data["summary"].get("total_req", 0)
            covered = data["summary"].get("covered_req", 0)
            if total > 0:
                rate = covered / total
                if rate >= 1.0:
                    return True, f"REQ 覆盖率 {covered}/{total} (100%)"
                return False, f"REQ 覆盖率 {covered}/{total} ({rate * 100:.0f}%，要求 100%)"
    req_refs = len(RE_REQ_ID.findall(report))
    if req_refs >= 5:
        return True, f"{req_refs} 处 REQ 引用"
    return False, f"仅 {req_refs} 处 REQ 引用（无法验证 REQ 覆盖率）"


def _check_br_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 BR 覆盖率."""
    from dqg.json_utils import load_json

    for candidate in [pd.parent / "_test_design_matrix.json", pd / "_test_design_matrix.json"]:
        data = load_json(candidate)
        if data and data.get("summary"):
            total = data["summary"].get("backend_total_br", 0)
            covered = data["summary"].get("backend_covered_br", 0)
            if total == 0:
                total = data["summary"].get("total_br", 0)
                covered = data["summary"].get("covered_br", 0)
            if total > 0:
                rate = covered / total
                if rate >= 0.8:
                    return True, f"BR 覆盖率 {covered}/{total} ({rate * 100:.0f}%)"
                return False, f"BR 覆盖率 {covered}/{total} ({rate * 100:.0f}%，要求 ≥80%)"
    br_refs = len(RE_BR_ID.findall(report))
    if br_refs >= 10:
        return True, f"{br_refs} 处 BR 引用"
    return False, f"仅 {br_refs} 处 BR 引用（无法验证 BR 覆盖率）"


def _check_code_branch_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查代码分支覆盖."""
    from dqg.json_utils import load_json

    for candidate in [pd.parent / "_test_design_matrix.json", pd / "_test_design_matrix.json"]:
        data = load_json(candidate)
        if data and data.get("summary"):
            total = data["summary"].get("total_branches", 0)
            covered = data["summary"].get("covered_branches", 0)
            if total > 0:
                rate = covered / total
                if rate >= 0.7:
                    return True, f"分支覆盖率 {covered}/{total} ({rate * 100:.0f}%)"
                return False, f"分支覆盖率 {covered}/{total} ({rate * 100:.0f}%，要求 ≥70%)"
    keywords = ["分支", "branch", "if.*null", "try.*catch", "switch", "default", "降级", "防御"]
    found = sum(1 for kw in keywords if kw.lower() in report.lower())
    if found >= 3:
        return True, f"有分支覆盖分析（{found} 个关键词）"
    return True, "分支覆盖需编译验证"


def _check_eut_count(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 EUT 数量."""
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    json_path = pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")
    data = load_json(json_path)
    if data:
        euts = data.get("eut_matrix", data.get("eut_items", data.get("test_cases", [])))
        count = len(euts)
        if count >= 10:
            return True, f"{count} 个 EUT"
        return False, f"仅 {count} 个 EUT（要求 ≥10）"
    count = report.count("EUT-")
    if count >= 10:
        return True, f"~{count} 个 EUT 引用"
    return False, f"仅 ~{count} 个 EUT 引用（要求 ≥10）"


def _check_path_balance(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 Happy/Exception 路径均衡."""
    from dqg.json_utils import load_json

    json_path = pd.parent / "phase_b_structured.json"
    data = load_json(json_path)
    if data:
        summary = data.get("summary", {})
        happy = summary.get("happy_path", 0)
        exception = summary.get("exception_path", 0)
        if happy > 0 and exception > 0:
            return True, f"Happy={happy}, Exception={exception}"
        return False, f"Happy={happy}, Exception={exception}（需要两种路径都有）"
    happy = report.lower().count("happy") + report.count("正常")
    exception = report.lower().count("exception") + report.count("异常") + report.count("抛异常")
    if happy > 0 and exception > 0:
        return True, f"Happy~{happy}, Exception~{exception}"
    return False, "未检测到 Happy/Exception 路径均衡"


def _check_se_bound(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 SE 绑定覆盖."""
    from dqg.json_utils import load_json

    json_path = pd.parent / "phase_b_structured.json"
    data = load_json(json_path)
    if data:
        summary = data.get("summary", {})
        se_covered = summary.get("se_covered", [])
        if len(se_covered) >= 3:
            return True, f"{len(se_covered)} 个 SE 绑定: {', '.join(se_covered[:5])}"
        return False, f"仅 {len(se_covered)} 个 SE 绑定（要求 ≥3）"
    se_refs = len(RE_SE_ID.findall(report))
    if se_refs >= 3:
        return True, f"{se_refs} 处 SE 引用"
    return False, f"仅 {se_refs} 处 SE 引用（要求 ≥3）"


def _check_strong_assert(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查是否使用强断言."""
    from dqg.json_utils import load_json

    json_path = pd.parent / "phase_b_structured.json"
    data = load_json(json_path)
    if data:
        test_files = data.get("test_files", [])
        if test_files:
            return True, f"{len(test_files)} 个测试文件（断言检查需编译验证）"
    if "assertEquals" in report or "assertThrows" in report:
        return True, "使用了强断言"
    if "assertNotNull" in report and "assertEquals" not in report:
        return False, "仅使用 assertNotNull（弱断言）"
    return True, "断言检查需编译验证"


# ---------------------------------------------------------------------------
# Phase Q06 检查（7 维度审计标准）
# ---------------------------------------------------------------------------


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
        types = []
        if has_happy:
            types.append("Happy")
        if has_exception:
            types.append("Exception")
        if has_boundary:
            types.append("Boundary")
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
    found = sum(1 for kw in keywords if kw in report)
    if found >= 1:
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


# ---------------------------------------------------------------------------
# Phase B/C 检查函数映射表
# ---------------------------------------------------------------------------

BC_CHECK_FUNCS: Final = MappingProxyType(
    {
        "_check_design_matrix": _check_design_matrix,
        "_check_req_coverage": _check_req_coverage,
        "_check_br_coverage": _check_br_coverage,
        "_check_code_branch_coverage": _check_code_branch_coverage,
        "_check_eut_count": _check_eut_count,
        "_check_path_balance": _check_path_balance,
        "_check_se_bound": _check_se_bound,
        "_check_strong_assert": _check_strong_assert,
        "_check_c_se_coverage": _check_c_se_coverage,
        "_check_c_path_balance": _check_c_path_balance,
        "_check_c_assert_strength": _check_c_assert_strength,
        "_check_c_mock_reality": _check_c_mock_reality,
        "_check_c_state_machine": _check_c_state_machine,
        "_check_c_maintainability": _check_c_maintainability,
        "_check_c_boundary": _check_c_boundary,
        "_check_c_defensive": _check_c_defensive,
    }
)
