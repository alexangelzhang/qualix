"""规则检查函数.

从 rule_compliance.py 拆分，包含所有 _check_* 函数和函数映射表。
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from dqg.text_utils import REPORT_MAP

from .rule_definitions import (
    RE_CONFIDENCE,
    RE_CONFIDENCE_D,
    RE_COVERAGE_EVIDENCE,
    RE_COVERAGE_STATUS,
    RE_GAP_DEF_LINE,
    RE_GAP_LEVEL,
    RE_GAP_TABLE_LINE,
    RE_OPEN_DEF_LINE,
    RE_OPEN_OWNER,
    RE_OPEN_TABLE_LINE,
    RE_SE_LINE,
    RE_STATE_ENUM,
    RE_URL_DESIGN,
    RE_URL_FALLBACK,
    RE_UT_EUT,
)
from .source_spec import compute_source_coverage

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# 报告读取
# ---------------------------------------------------------------------------


def read_report(pd: Path, phase_id: str) -> str:
    """读取 Phase 产物报告内容."""
    report_map = REPORT_MAP
    f = pd / report_map.get(phase_id, "")
    if f.exists():
        return f.read_text(encoding="utf-8")
    # Fallback: 合并 JSON + 推理日志 + 同目录其他 md 作为"报告"内容
    parts: list[str] = []
    for name in ("phase_b_structured.json", "phase_a3_structured.json", "phase_c_structured.json", "_reasoning_log.md"):
        candidate = pd / name
        if candidate.exists():
            parts.append(candidate.read_text(encoding="utf-8", errors="ignore"))
    # 读取同目录下所有 md 文件（补充报告如 deep_review/ab_test 等）
    for md_file in sorted(pd.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        if content not in parts:
            parts.append(content)
    # 也检查 _internal 目录
    int_dir = pd / "_internal"
    if int_dir.is_dir():
        for candidate in int_dir.glob("_reasoning_log.md"):
            parts.append(candidate.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 通用检查函数
# ---------------------------------------------------------------------------


def _check_reasoning_log(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    log = pd / "_reasoning_log.md"
    if not log.exists():
        return False, "文件不存在"
    content = log.read_text(encoding="utf-8")
    if len(content) < 100:
        return False, f"内容过少（{len(content)} 字符）"
    step_count = content.count("## Step")
    if step_count < 2:
        return False, f"仅记录 {step_count} 个 Step，不完整"
    return True, f"{step_count} 个 Step 已记录"


def _check_judge_critique(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if phase_id == "Q02":
        has_decisions = "设计决策" in report or "架构" in report or "GAP.*技术方案" in report or "复用" in report
        if has_decisions:
            return True, "有设计决策记录"
        return False, "技术方案中无设计决策记录"
    if phase_id == "Q05":
        has_eut = "EUT" in report or "eut_matrix" in report
        if has_eut:
            return True, "有 EUT 矩阵"
        return False, "无 EUT 矩阵"
    if phase_id == "Q06":
        has_audit = "审计" in report or "覆盖" in report or "AB" in report or "对比" in report
        if has_audit:
            return True, "有审计分析"
        return False, "无审计分析"
    has_in_report = "自我评审" in report or ("Judge" in report and "Critique" in report)
    has_file = (pd / "_critique.json").exists() or (pd / "_judge_result.json").exists()
    if has_in_report or has_file:
        return True, "已执行"
    return False, "报告中无自我评审记录，且无 _critique.json/_judge_result.json"


def _check_source_annotation(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    annotated, total, missing = compute_source_coverage(report, phase_id)
    if total == 0:
        return True, "报告无判定性结论"
    if annotated == total:
        return True, f"{annotated}/{total} 结论行挂来源"
    sample = "; ".join(f"L{ln}" for ln in missing[:3])
    return False, f"{annotated}/{total} 结论行挂来源，{total - annotated} 行缺失（如 {sample}）"


def _check_confidence_annotation(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if phase_id in ("Q02", "Q05", "Q06"):
        return True, "确定性产出，不适用"
    if phase_id == "Q07":
        matches = RE_CONFIDENCE_D.findall(report)
        if len(matches) >= 2:
            return True, f"{len(matches)} 处置信度/严重级别标注"
        return False, f"仅 {len(matches)} 处置信度标注（要求 ≥2）"
    matches = RE_CONFIDENCE.findall(report)
    if len(matches) >= 2:
        return True, f"{len(matches)} 处置信度标注"
    return False, f"仅 {len(matches)} 处置信度标注（要求 ≥2）"


def _check_no_ut_eut(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if phase_id not in ("Q01", "Q04", "Q03"):
        return True, "不适用"
    matches = RE_UT_EUT.findall(report)
    if matches:
        return False, f"发现 {len(matches)} 处 UT/EUT 输出"
    return True, "未输出 UT/EUT"


# ---------------------------------------------------------------------------
# Phase Q01 检查
# ---------------------------------------------------------------------------


def _check_mermaid(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "```mermaid" in report:
        count = report.count("```mermaid")
        return True, f"{count} 个 Mermaid 图"
    return False, "报告中无 Mermaid 图"


def _check_image_table(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "图片资产" in report or "图片语义" in report:
        return True, "存在"
    return False, "报告中无图片资产表"


def _check_br_detail(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    vague_patterns = [
        "展示完整信息",
        "自动查询.*并回传展示",
        "按状态节点展示",
        "支持导入导出",
    ]
    vague_count = 0
    for p in vague_patterns:
        vague_count += len(re.findall(p, report))
    if vague_count > 0:
        return False, f"发现 {vague_count} 处概括性描述"
    return True, "BR 描述具体"


def _check_gap_level(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    gap_lines = [ln for ln in report.split("\n") if RE_GAP_TABLE_LINE.match(ln) or RE_GAP_DEF_LINE.match(ln)]
    if not gap_lines:
        return True, "无 GAP"
    has_level = sum(1 for ln in gap_lines if RE_GAP_LEVEL.search(ln))
    rate = has_level / max(len(gap_lines), 1)
    if rate >= 0.8:
        return True, f"{has_level}/{len(gap_lines)} 有风险等级"
    return False, f"仅 {has_level}/{len(gap_lines)} 有风险等级（要求 ≥80%）"


def _check_open_owner(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    open_lines = [ln for ln in report.split("\n") if RE_OPEN_TABLE_LINE.match(ln) or RE_OPEN_DEF_LINE.match(ln)]
    if not open_lines:
        return True, "无 OPEN"
    has_owner = sum(1 for ln in open_lines if RE_OPEN_OWNER.search(ln))
    rate = has_owner / max(len(open_lines), 1)
    if rate >= 0.8:
        return True, f"{has_owner}/{len(open_lines)} 有决策方"
    return False, f"仅 {has_owner}/{len(open_lines)} 有决策方（要求 ≥80%）"


def _check_se_basis(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    se_lines = [ln for ln in report.split("\n") if RE_SE_LINE.match(ln)]
    if not se_lines:
        return True, "无 SE"
    has_basis = sum(1 for ln in se_lines if "判定依据" in ln or "|" in ln)
    rate = has_basis / max(len(se_lines), 1)
    if rate >= 0.5:
        return True, f"{has_basis}/{len(se_lines)} 有判定依据"
    return False, f"仅 {has_basis}/{len(se_lines)} 有判定依据（要求 ≥50%）"


# ---------------------------------------------------------------------------
# Phase Q04 检查
# ---------------------------------------------------------------------------


def _check_coverage_evidence(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    coverage_lines = [ln for ln in report.split("\n") if RE_COVERAGE_STATUS.search(ln)]
    if not coverage_lines:
        return True, "无覆盖判定"
    has_evidence = sum(1 for ln in coverage_lines if RE_COVERAGE_EVIDENCE.search(ln))
    rate = has_evidence / max(len(coverage_lines), 1)
    if rate >= 0.6:
        return True, f"{has_evidence}/{len(coverage_lines)} 有原文引用"
    return False, f"仅 {has_evidence}/{len(coverage_lines)} 有原文引用（要求 ≥60%）"


def _check_gap_closure(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "闭环" in report:
        return True, "已检查"
    return False, "报告中无 GAP/OPEN 闭环检查"


def _check_reverse_audit(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "反向审计" in report or "NEW_DESIGN" in report or "NOT_IN_SCOPE" in report:
        return True, "已完成"
    return False, "报告中无反向审计"


# ---------------------------------------------------------------------------
# Phase Q03 检查
# ---------------------------------------------------------------------------


def _check_five_dimensions(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    dim_patterns = {
        "架构": ["架构", "ARCH-", "DDD", "分层", "状态机", "调用链"],
        "接口": ["接口", "API-", "入参", "出参", "协议", "endpoint"],
        "数据": ["数据", "DATA-", "DDL", "表设计", "索引", "唯一键"],
        "异常": ["异常", "EXC-", "异常处理", "Failure Mode", "故障", "超时", "降级"],
        "性能": ["性能", "PERF-", "并发", "批量", "缓存", "OOM"],
    }
    found = []
    for dim, keywords in dim_patterns.items():
        if any(kw in report for kw in keywords):
            found.append(dim)
    if len(found) >= 4:
        return True, f"{len(found)}/5 维度已检查"
    return False, f"仅 {len(found)}/5 维度（{', '.join(found)}）"


def _check_failure_mode(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "Failure Mode" in report or "failure mode" in report or "故障模式" in report:
        return True, "已完成"
    return False, "报告中无 Failure Mode 分析"


# ---------------------------------------------------------------------------
# Phase Q02 检查
# ---------------------------------------------------------------------------


def _check_ddl(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查是否包含 CREATE TABLE DDL."""
    count = report.count("CREATE TABLE")
    if count >= 1:
        return True, f"{count} 张表 DDL"
    return False, "未找到 CREATE TABLE DDL"


def _check_interface_design(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查接口设计完整性（URL + 入参/响应表格）."""
    url_count = len(RE_URL_DESIGN.findall(report))
    if url_count == 0:
        url_count = len(RE_URL_FALLBACK.findall(report))
    table_count = report.count("| 字段") + report.count("| Field")
    if url_count >= 3 and table_count >= 3:
        return True, f"{url_count} 个接口 URL, {table_count} 个参数表格"
    if url_count >= 3:
        return True, f"{url_count} 个接口 URL（参数表格 {table_count} 个偏少）"
    return False, f"仅 {url_count} 个接口 URL, {table_count} 个参数表格（要求 ≥3）"


def _check_state_machine(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查状态机设计（如涉及）."""
    has_mermaid = "stateDiagram" in report
    has_enum = bool(RE_STATE_ENUM.search(report))
    if has_mermaid and has_enum:
        return True, "Mermaid 状态图 + 码值表"
    if has_mermaid:
        return True, "Mermaid 状态图（建议补充码值表）"
    if has_enum:
        return True, "状态码值表（建议补充 Mermaid 图）"
    return True, "未涉及状态机（跳过）"


def _check_reuse_analysis(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查现有代码复用分析."""
    keywords = ["复用", "reuse", "扩展", "extend", "新增", "new"]
    found = sum(1 for kw in keywords if kw.lower() in report.lower())
    if "复用分析" in report or "复用/扩展/新增" in report or found >= 3:
        return True, "有复用分析"
    return False, "未找到现有代码复用分析"


def _check_impl_slice(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查实施切片建议."""
    if "切片" in report or "slice" in report.lower() or "实施" in report:
        return True, "有实施切片建议"
    return False, "未找到实施切片建议"


def _check_traceability(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    """检查 Q01 的 REQ/BR 在下游报告里是否被追溯.

    ground truth：Q01 的 phase_a_structured.json 中的 requirements.req_id 集合。
    通过条件：集合中每个 ID 在 report 中至少出现一次。
    找不到 Q01 产物则跳过（不阻断）。
    """
    from dqg.json_utils import load_json

    q01_json = pd.parent / "Q01" / "phase_a_structured.json"
    if not q01_json.exists():
        return True, "未找到 Q01 产物，跳过可追溯性检查"

    data = load_json(q01_json) or {}
    ids: set[str] = set()
    for item in data.get("requirements") or []:
        if isinstance(item, dict):
            rid = item.get("req_id") or item.get("id")
            if isinstance(rid, str) and rid:
                ids.add(rid)

    if not ids:
        return True, "Q01 无 REQ/BR，跳过可追溯性检查"

    missing = sorted(rid for rid in ids if rid not in report)
    if not missing:
        return True, f"{len(ids)}/{len(ids)} 条 REQ/BR 已追溯"
    sample = ", ".join(missing[:5])
    return False, f"{len(ids) - len(missing)}/{len(ids)} 条 REQ/BR 已追溯，缺失：{sample}"


# ---------------------------------------------------------------------------
# 检查函数映射表（合并本模块 + Phase B/C 子模块）
# ---------------------------------------------------------------------------

from .rule_checks_bc import BC_CHECK_FUNCS

CHECK_FUNCS: Final = MappingProxyType(
    {
        "_check_reasoning_log": _check_reasoning_log,
        "_check_judge_critique": _check_judge_critique,
        "_check_source_annotation": _check_source_annotation,
        "_check_confidence_annotation": _check_confidence_annotation,
        "_check_no_ut_eut": _check_no_ut_eut,
        "_check_mermaid": _check_mermaid,
        "_check_image_table": _check_image_table,
        "_check_br_detail": _check_br_detail,
        "_check_gap_level": _check_gap_level,
        "_check_open_owner": _check_open_owner,
        "_check_se_basis": _check_se_basis,
        "_check_coverage_evidence": _check_coverage_evidence,
        "_check_gap_closure": _check_gap_closure,
        "_check_reverse_audit": _check_reverse_audit,
        "_check_five_dimensions": _check_five_dimensions,
        "_check_failure_mode": _check_failure_mode,
        "_check_ddl": _check_ddl,
        "_check_interface_design": _check_interface_design,
        "_check_state_machine": _check_state_machine,
        "_check_reuse_analysis": _check_reuse_analysis,
        "_check_impl_slice": _check_impl_slice,
        "_check_traceability": _check_traceability,
        **BC_CHECK_FUNCS,
    }
)
