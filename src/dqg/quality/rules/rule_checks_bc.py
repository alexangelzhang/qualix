"""Phase Q05/Q06 规则检查函数.

从 rule_checks.py 拆分，包含单测生成（Q05）和单测审计（Q06）的检查函数。
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from .rule_definitions import RE_REQ_ID, RE_SE_ID

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
    return False, "单测设计矩阵（_test_design_matrix.json）不存在（报告文本提及不等同于矩阵存在）"


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
    return False, f"设计矩阵缺失，REQ 覆盖率无法验证（报告有 {req_refs} 处 REQ 引用，但需要结构化矩阵）"


def _check_br_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 BR 覆盖率 = 100%（有无设计矩阵均验证）.

    有矩阵时：读 summary.backend_covered_br/total_br。
    无矩阵时：通过 SE.bound_reqs 链路间接验证（EUT→SE→BR）。
    """
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    # 优先用设计矩阵
    for candidate in [pd.parent / "_test_design_matrix.json", pd / "_test_design_matrix.json"]:
        data = load_json(candidate)
        if data and data.get("summary"):
            total = data["summary"].get("backend_total_br", 0) or data["summary"].get("total_br", 0)
            covered = data["summary"].get("backend_covered_br", 0) or data["summary"].get("covered_br", 0)
            if total > 0:
                if covered >= total:
                    return True, f"BR 覆盖率 100%（{covered}/{total}）"
                return False, f"BR 覆盖率 {covered}/{total} ({covered * 100 // total}%，要求 100%)"

    # 无矩阵：通过 Q01 SE.bound_reqs 链路间接验证

    q01_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    q01_data = load_json(pd.parent / "Q01" / q01_json) or {}
    reqs = q01_data.get("requirements", [])
    ses = q01_data.get("semantic_expectations", [])
    all_br_ids = {str(r.get("req_id", "")) for r in reqs if str(r.get("req_id", "")).startswith("BR")}
    if not all_br_ids:
        return False, "无法验证 BR 覆盖率（Q01 产物不可用）"

    # SE → BR/REQ 映射
    se_bound_reqs: dict[str, set[str]] = {s["se_id"]: set(s.get("bound_reqs", []) or []) for s in ses}

    # EUT → SE → BR
    eut_data = load_json(pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")) or {}
    euts = eut_data.get("eut_items", eut_data.get("test_cases", []))
    covered_brs: set[str] = set()
    for eut in euts:
        se_refs = list(eut.get("se_refs", []) or [])
        bound_se = str(eut.get("bound_se", "") or "")
        if bound_se and bound_se not in se_refs:
            se_refs = [bound_se, *se_refs]
        for se_id in se_refs:
            covered_brs.update(se_bound_reqs.get(se_id, set()) & all_br_ids)

    missing = sorted(all_br_ids - covered_brs)
    covered_count = len(all_br_ids) - len(missing)
    if missing:
        return False, (f"BR 覆盖 {covered_count}/{len(all_br_ids)}，要求 100%，缺失: {', '.join(missing[:6])}")
    return True, f"BR 100% 覆盖（{len(all_br_ids)} 条，通过 SE 链路验证）"


def _check_code_branch_coverage(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查代码分支覆盖 = 100%（有无设计矩阵均验证）.

    有矩阵时：读 summary.covered_branches/total_branches。
    无矩阵时：从分支清单（_internal/_q05_branch_inventory.json）+ EUT 类型推断。
    两者均无：FAIL。
    """
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    # 优先用设计矩阵
    for candidate in [pd.parent / "_test_design_matrix.json", pd / "_test_design_matrix.json"]:
        data = load_json(candidate)
        if data and data.get("summary"):
            total = data["summary"].get("total_branches", 0)
            covered = data["summary"].get("covered_branches", 0)
            if total > 0:
                if covered >= total:
                    return True, f"代码分支覆盖 100%（{covered}/{total}）"
                return False, f"代码分支覆盖 {covered}/{total} ({covered * 100 // total}%，要求 100%)"

    # 无矩阵：从分支清单 + EUT 类型推断
    inv_path = pd / "_internal" / "_q05_branch_inventory.json"
    inv = load_json(inv_path) if inv_path.exists() else None
    if inv is not None:
        from dqg.quality.guardrail.q05_branch_coverage import (
            _count_boundary_branches,
            _count_boundary_euts,
            _count_exception_branches,
            _count_exception_euts,
        )

        b5d = load_json(pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")) or {}
        exc_br = _count_exception_branches(inv)
        bnd_br = _count_boundary_branches(inv)
        exc_eut = _count_exception_euts(b5d)
        bnd_eut = _count_boundary_euts(b5d)
        errors: list[str] = []
        if exc_br > 0 and exc_eut < exc_br:
            errors.append(f"Exception 分支 {exc_eut}/{exc_br}（要求 100%）")
        if bnd_br > 0 and bnd_eut < bnd_br:
            errors.append(f"Boundary 分支 {bnd_eut}/{bnd_br}（要求 100%）")
        if errors:
            return False, f"代码分支覆盖不足 100%: {'; '.join(errors)}"
        return True, (f"代码分支 100% 覆盖（Exception={exc_eut}/{exc_br}, Boundary={bnd_eut}/{bnd_br}）")

    return False, "无设计矩阵且无分支清单，代码分支覆盖无法验证（需执行三步范式 Step A）"


def _load_q01_counts(pd: Path) -> tuple[int, int, int]:
    """从 Q01 产物读取 REQ/BR/SE 数量，返回 (req_count, br_count, se_count)."""
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    q01_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    q01_data = load_json(pd.parent / "Q01" / q01_json) or {}
    reqs = q01_data.get("requirements", [])
    ses = q01_data.get("semantic_expectations", [])
    req_count = sum(1 for r in reqs if str(r.get("req_id", "")).startswith("REQ"))
    br_count = sum(1 for r in reqs if str(r.get("req_id", "")).startswith("BR"))
    return req_count, br_count, len(ses)


def _check_eut_count(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 EUT 数量 ≥ Q01 的 REQ+BR+SE 总数（动态门槛，无上限）."""
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    req_count, br_count, se_count = _load_q01_counts(pd)
    min_euts = max(10, req_count + br_count + se_count)
    threshold_desc = f"REQ({req_count})+BR({br_count})+SE({se_count})={min_euts}"

    json_path = pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")
    data = load_json(json_path)
    if data:
        euts = data.get("eut_items", data.get("eut_matrix", data.get("test_cases", [])))
        count = len(euts)
        if count >= min_euts:
            return True, f"{count} 个 EUT ≥ 门槛 {threshold_desc}"
        return False, f"仅 {count} 个 EUT，要求 ≥{threshold_desc}"
    count = report.count("EUT-")
    if count >= min_euts:
        return True, f"~{count} 个 EUT 引用（≥{threshold_desc}）"
    return False, f"仅 ~{count} 个 EUT 引用，要求 ≥{threshold_desc}"


_EXCEPTION_KWS: frozenset[str] = frozenset(
    {
        "校验",
        "不允许",
        "禁止",
        "短路",
        "不发起",
        "不生成",
        "不回退",
        "拒绝",
        "失败",
        "异常",
        "错误",
        "阻断",
        "强制",
        "不得",
        "不能",
    }
)
_BOUNDARY_KWS: frozenset[str] = frozenset(
    {
        "精确",
        "边界",
        "为空",
        "null",
        "缺一不可",
        "1:1",
        "完单后精确",
        "恰好",
        "必须包含",
        "全部必传",
        "字段完整",
        "不得缺失",
    }
)


def _check_path_balance(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查路径覆盖率：Happy ≥ 80%，Exception = 100%，Boundary = 100%.

    验证维度（REQ + BR + SE + 代码分支清单）：
    - SE 逐条：含异常/边界语义的每条 SE 必须有对应类型的 EUT，≥80% SE 有 Happy EUT
    - BR 逐条：含异常/边界语义的每条 BR 必须通过 SE 链路覆盖到对应类型的 EUT
    - REQ 逐条：≥80% REQ 通过 SE 链路覆盖到 Happy Path EUT
    - 代码维度：分支清单中异常/边界分支必须全部有对应类型 EUT（100%）
    """
    from collections import Counter, defaultdict

    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    json_path = pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")
    data = load_json(json_path)
    if not data:
        return False, "phase_b_structured.json 不存在，路径覆盖无法验证"

    euts = data.get("eut_items", data.get("eut_matrix", data.get("test_cases", [])))
    if not euts:
        return False, "eut_items 为空"

    # ── 从 Q01 加载 SE/BR/REQ 列表 ──────────────────────────────────────────
    q01_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    q01_data = load_json(pd.parent / "Q01" / q01_json) or {}
    ses = q01_data.get("semantic_expectations", [])
    reqs_list = q01_data.get("requirements", [])

    # SE → 它覆盖的 BR/REQ（via bound_reqs）
    se_bound_reqs: dict[str, set[str]] = {s["se_id"]: set(s.get("bound_reqs", []) or []) for s in ses}

    # ── 按 bound_se 记录每条 SE 的路径类型 ──────────────────────────────────
    se_routes: dict[str, set[str]] = defaultdict(set)
    # 同时构建 BR/REQ → 路径类型（间接覆盖）
    req_routes: dict[str, set[str]] = defaultdict(set)
    for e in euts:
        route = e.get("route_type", "")
        se_ref_list = list(e.get("se_refs", []) or [])
        bound_se = str(e.get("bound_se", "") or "")
        if bound_se and bound_se not in se_ref_list:
            se_ref_list = [bound_se, *se_ref_list]
        for se_id in se_ref_list:
            se_routes[se_id].add(route)
            for req_id in se_bound_reqs.get(se_id, set()):
                req_routes[req_id].add(route)

    errors: list[str] = []

    # ── SE 维度 ──────────────────────────────────────────────────────────────
    all_se_ids = [s["se_id"] for s in ses]
    se_need_exc = [s["se_id"] for s in ses if any(kw in s.get("description", "") for kw in _EXCEPTION_KWS)]
    se_need_bnd = [s["se_id"] for s in ses if any(kw in s.get("description", "") for kw in _BOUNDARY_KWS)]

    missing_se_exc = [sid for sid in se_need_exc if "Exception" not in se_routes.get(sid, set())]
    if se_need_exc and missing_se_exc:
        errors.append(
            f"[SE] Exception {len(se_need_exc) - len(missing_se_exc)}/{len(se_need_exc)} 100%，缺失: {', '.join(missing_se_exc)}"
        )

    missing_se_bnd = [sid for sid in se_need_bnd if "Boundary" not in se_routes.get(sid, set())]
    if se_need_bnd and missing_se_bnd:
        errors.append(
            f"[SE] Boundary {len(se_need_bnd) - len(missing_se_bnd)}/{len(se_need_bnd)} 100%，缺失: {', '.join(missing_se_bnd)}"
        )

    if all_se_ids:
        se_happy = [sid for sid in all_se_ids if "Happy Path" in se_routes.get(sid, set())]
        se_happy_rate = len(se_happy) / len(all_se_ids)
        if se_happy_rate < 0.8:
            errors.append(f"[SE] Happy {len(se_happy)}/{len(all_se_ids)}={se_happy_rate:.0%}，要求 ≥80%")

    # ── BR 维度（通过 SE 链路间接验证） ─────────────────────────────────────
    br_list = [r for r in reqs_list if str(r.get("req_id", "")).startswith("BR")]
    br_descs = {r["req_id"]: r.get("description", "") for r in br_list}
    br_need_exc = [r["req_id"] for r in br_list if any(kw in br_descs.get(r["req_id"], "") for kw in _EXCEPTION_KWS)]
    br_need_bnd = [r["req_id"] for r in br_list if any(kw in br_descs.get(r["req_id"], "") for kw in _BOUNDARY_KWS)]

    missing_br_exc = [bid for bid in br_need_exc if "Exception" not in req_routes.get(bid, set())]
    if br_need_exc and missing_br_exc:
        errors.append(
            f"[BR] Exception {len(br_need_exc) - len(missing_br_exc)}/{len(br_need_exc)} 100%，缺失: {', '.join(missing_br_exc[:5])}"
        )

    missing_br_bnd = [bid for bid in br_need_bnd if "Boundary" not in req_routes.get(bid, set())]
    if br_need_bnd and missing_br_bnd:
        errors.append(
            f"[BR] Boundary {len(br_need_bnd) - len(missing_br_bnd)}/{len(br_need_bnd)} 100%，缺失: {', '.join(missing_br_bnd[:5])}"
        )

    # ── REQ 维度（Happy Path ≥ 80%） ────────────────────────────────────────
    req_ids = [r["req_id"] for r in reqs_list if str(r.get("req_id", "")).startswith("REQ")]
    if req_ids:
        req_happy = [rid for rid in req_ids if "Happy Path" in req_routes.get(rid, set())]
        req_happy_rate = len(req_happy) / len(req_ids)
        if req_happy_rate < 0.8:
            errors.append(f"[REQ] Happy {len(req_happy)}/{len(req_ids)}={req_happy_rate:.0%}，要求 ≥80%")

    # ── 代码维度（分支清单） ─────────────────────────────────────────────────
    inv_path = pd / "_internal" / "_q05_branch_inventory.json"
    inv = load_json(inv_path) if inv_path.exists() else None
    if inv is not None:
        from dqg.quality.guardrail.q05_branch_coverage import (
            _count_boundary_branches,
            _count_boundary_euts,
            _count_exception_branches,
            _count_exception_euts,
        )

        exc_br = _count_exception_branches(inv)
        bnd_br = _count_boundary_branches(inv)
        exc_eut = _count_exception_euts(data)
        bnd_eut = _count_boundary_euts(data)
        if exc_br > 0 and exc_eut < exc_br:
            errors.append(f"[代码] Exception 分支 {exc_eut}/{exc_br}，要求 100%")
        if bnd_br > 0 and bnd_eut < bnd_br:
            errors.append(f"[代码] Boundary 分支 {bnd_eut}/{bnd_br}，要求 100%")

    if errors:
        return False, "; ".join(errors)

    # fallback（Q01 不可用时）
    if not all_se_ids:
        route_counts = Counter(e.get("route_type", "") for e in euts)
        if route_counts.get("Happy Path", 0) == 0:
            return False, "无 Happy Path EUT"

    return True, (
        "路径覆盖达标 | SE[Happy≥80%/Exception=100%/Boundary=100%]"
        " BR[Exception=100%/Boundary=100%] REQ[Happy≥80%]" + (" 代码维度[100%]" if inv is not None else "")
    )


def _check_se_bound(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查每条 SE 都有至少一个 bound_se 匹配的 EUT（逐条验证，100% 覆盖）."""
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.json_utils import load_json

    json_path = pd / STRUCTURED_JSON_MAP.get("Q05", "phase_b_structured.json")
    data = load_json(json_path)

    # 从 Q01 获取全量 SE ID
    q01_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    q01_data = load_json(pd.parent / "Q01" / q01_json) or {}
    all_se_ids = {s["se_id"] for s in q01_data.get("semantic_expectations", [])}

    if data and all_se_ids:
        euts = data.get("eut_items", data.get("eut_matrix", data.get("test_cases", [])))
        covered_se = {str(e.get("bound_se", "") or "") for e in euts if e.get("bound_se")}
        missing = sorted(all_se_ids - covered_se)
        covered_count = len(all_se_ids) - len(missing)
        if not missing:
            return True, f"全部 {len(all_se_ids)} 条 SE 均有 bound_se 对应的 EUT"
        return False, (f"SE 覆盖 {covered_count}/{len(all_se_ids)}，缺失 EUT 绑定: {', '.join(missing)}")

    # fallback：仅靠文本计数
    se_refs = len(RE_SE_ID.findall(report))
    if se_refs >= 3:
        return True, f"{se_refs} 处 SE 引用（Q01 不可用，无法精确验证）"
    return False, f"仅 {se_refs} 处 SE 引用（要求每条 SE 有对应 EUT）"


_STRONG_ASSERT_PATTERN = re.compile(r"\b(assertEquals|assertThrows|assertThat|verify|assertSame|assertArrayEquals)\b")
_WEAK_ONLY_PATTERN = re.compile(r"\bassertNotNull\b")


def _check_strong_assert(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查测试代码断言强度：扫描业务仓库新增 .java 文件，检测弱断言比例.

    强断言：assertEquals / assertThrows / assertThat / verify / assertSame
    弱断言（仅有）：assertNotNull 但无任何强断言方法
    """
    from dqg.json_utils import load_json
    from dqg.quality.checks.q05_structure_checks import _collect_new_test_files_from_repos

    # 读 code_repos（来自 _inputs.json）
    inputs_data = load_json(pd / "_internal" / "_inputs.json") or {}
    code_repos: list[str] = inputs_data.get("code_repos") or []
    if not code_repos and inputs_data.get("code_repo"):
        code_repos = [inputs_data["code_repo"]]

    if code_repos:
        java_files = [f for f in _collect_new_test_files_from_repos(code_repos) if f.suffix == ".java"]
        if java_files:
            weak_files, strong_files = [], []
            for path in java_files:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                has_strong = bool(_STRONG_ASSERT_PATTERN.search(text))
                has_weak = bool(_WEAK_ONLY_PATTERN.search(text))
                if has_strong:
                    strong_files.append(path.name)
                elif has_weak:
                    weak_files.append(path.name)
            total = len(java_files)
            if weak_files and not strong_files:
                return False, (
                    f"{len(weak_files)}/{total} 个测试文件仅含 assertNotNull 弱断言，"
                    f"缺少 assertEquals/assertThrows/verify: {', '.join(weak_files[:3])}"
                )
            if strong_files:
                return True, f"{len(strong_files)}/{total} 个测试文件含强断言（assertEquals/assertThrows/verify）"
        return True, "未发现新增 .java 测试文件，断言检查已跳过"

    # fallback：报告文字检查（无 code_repos 时）
    if "assertEquals" in report or "assertThrows" in report or "verify(" in report:
        return True, "使用了强断言（报告文字）"
    if "assertNotNull" in report and "assertEquals" not in report:
        return False, "仅检测到 assertNotNull（弱断言），缺少 assertEquals/assertThrows/verify"
    return True, "断言检查需要 code_repo 配置"


# Q06 检查函数从独立模块导入
from .rule_checks_q06 import (
    _check_c_assert_strength,
    _check_c_boundary,
    _check_c_defensive,
    _check_c_maintainability,
    _check_c_mock_reality,
    _check_c_path_balance,
    _check_c_se_coverage,
    _check_c_state_machine,
)

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
