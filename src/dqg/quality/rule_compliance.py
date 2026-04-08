"""规则执行率追踪.

扫描 Phase 产物，检测每条规则是否被实际遵守，
输出执行率报告，持久化到 SQLite。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.text_utils import REPORT_MAP
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.store import insert_metric


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------

def _get_rules(phase_id: str) -> list[dict[str, Any]]:
    """获取 Phase 对应的规则检查项."""
    common = [
        {
            "id": "R-LOG",
            "name": "推理日志存在且有实质内容",
            "category": "流程",
            "check": "_check_reasoning_log",
        },
        {
            "id": "R-JUDGE",
            "name": "Judge/Critique 自我评审已执行",
            "category": "流程",
            "check": "_check_judge_critique",
        },
        {
            "id": "R-SOURCE",
            "name": "结论标注来源（文件名:行号）",
            "category": "反幻觉",
            "check": "_check_source_annotation",
        },
        {
            "id": "R-CONFIDENCE",
            "name": "结论标注置信度（High/Medium/Low）",
            "category": "反幻觉",
            "check": "_check_confidence_annotation",
        },
        {
            "id": "R-NO-UTEUT",
            "name": "未输出 UT/EUT（Phase A/A.5/A.6）",
            "category": "禁止",
            "check": "_check_no_ut_eut",
        },
    ]

    phase_specific: dict[str, list[dict[str, Any]]] = {
        "A": [
            {"id": "R-MERMAID", "name": "状态机/流程图已转为 Mermaid", "category": "图片", "check": "_check_mermaid"},
            {"id": "R-IMG-TABLE", "name": "图片资产表存在", "category": "图片", "check": "_check_image_table"},
            {"id": "R-BR-DETAIL", "name": "BR 包含完整字段（非概括性描述）", "category": "质量", "check": "_check_br_detail"},
            {"id": "R-GAP-LEVEL", "name": "GAP 标注风险等级（P0/P1/P2）", "category": "质量", "check": "_check_gap_level"},
            {"id": "R-OPEN-OWNER", "name": "OPEN 标注决策方", "category": "质量", "check": "_check_open_owner"},
            {"id": "R-SE-BASIS", "name": "SE 有判定依据", "category": "质量", "check": "_check_se_basis"},
        ],
        "A.5": [
            {"id": "R-COVERAGE-EVIDENCE", "name": "覆盖判定引用技术方案原文", "category": "质量", "check": "_check_coverage_evidence"},
            {"id": "R-GAP-CLOSURE", "name": "GAP/OPEN 闭环状态已检查", "category": "质量", "check": "_check_gap_closure"},
            {"id": "R-REVERSE-AUDIT", "name": "反向审计已完成", "category": "质量", "check": "_check_reverse_audit"},
        ],
        "A.6": [
            {"id": "R-FIVE-DIM", "name": "架构/接口/数据/异常/性能五维度已检查", "category": "质量", "check": "_check_five_dimensions"},
            {"id": "R-FAILURE-MODE", "name": "Failure Mode 分析已完成", "category": "质量", "check": "_check_failure_mode"},
        ],
    }

    rules = common.copy()
    rules.extend(phase_specific.get(phase_id, []))
    return rules


# ---------------------------------------------------------------------------
# 检查函数
# ---------------------------------------------------------------------------

def _read_report(pd: Path, phase_id: str) -> str:
    report_map = REPORT_MAP
    f = pd / report_map.get(phase_id, "")
    return f.read_text(encoding="utf-8") if f.exists() else ""


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
    # 检查报告中是否有自我评审记录，或 _critique.json 存在
    has_in_report = "自我评审" in report or "Judge" in report and "Critique" in report
    has_file = (pd / "_critique.json").exists() or (pd / "_judge_result.json").exists()
    if has_in_report or has_file:
        return True, "已执行"
    return False, "报告中无自我评审记录，且无 _critique.json/_judge_result.json"


def _check_source_annotation(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    pattern = r'\[来源[:：]'
    matches = re.findall(pattern, report)
    if len(matches) >= 3:
        return True, f"{len(matches)} 处来源标注"
    return False, f"仅 {len(matches)} 处来源标注（要求 ≥3）"


def _check_confidence_annotation(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    pattern = r'\[置信度[:：]\s*(High|Medium|Low)\]|置信度[:：]\s*(High|Medium|Low)'
    matches = re.findall(pattern, report)
    if len(matches) >= 2:
        return True, f"{len(matches)} 处置信度标注"
    return False, f"仅 {len(matches)} 处置信度标注（要求 ≥2）"


def _check_no_ut_eut(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if phase_id not in ("A", "A.5", "A.6"):
        return True, "不适用"
    ut_pattern = r'\bUT-\d+|EUT-\d+|\bUT\b.*测试用例'
    matches = re.findall(ut_pattern, report)
    if matches:
        return False, f"发现 {len(matches)} 处 UT/EUT 输出"
    return True, "未输出 UT/EUT"


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
    # 检查 BR 是否有概括性描述（反例关键词）
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
    gap_lines = [l for l in report.split("\n") if "GAP-" in l]
    if not gap_lines:
        return True, "无 GAP"
    has_level = sum(1 for l in gap_lines if re.search(r'P[012]|风险等级', l))
    rate = has_level / max(len(gap_lines), 1)
    if rate >= 0.8:
        return True, f"{has_level}/{len(gap_lines)} 有风险等级"
    return False, f"仅 {has_level}/{len(gap_lines)} 有风险等级（要求 ≥80%）"


def _check_open_owner(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    open_lines = [l for l in report.split("\n") if "OPEN-" in l]
    if not open_lines:
        return True, "无 OPEN"
    has_owner = sum(1 for l in open_lines if re.search(r'决策方|产品|研发|业务', l))
    rate = has_owner / max(len(open_lines), 1)
    if rate >= 0.8:
        return True, f"{has_owner}/{len(open_lines)} 有决策方"
    return False, f"仅 {has_owner}/{len(open_lines)} 有决策方（要求 ≥80%）"


def _check_se_basis(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    se_lines = [l for l in report.split("\n") if re.match(r'.*SE-\d+', l)]
    if not se_lines:
        return True, "无 SE"
    has_basis = sum(1 for l in se_lines if "判定依据" in l or "|" in l)
    rate = has_basis / max(len(se_lines), 1)
    if rate >= 0.5:
        return True, f"{has_basis}/{len(se_lines)} 有判定依据"
    return False, f"仅 {has_basis}/{len(se_lines)} 有判定依据（要求 ≥50%）"


def _check_coverage_evidence(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    coverage_lines = [l for l in report.split("\n") if re.search(r'COVERED|PARTIAL|MISSING|IMPLICIT', l)]
    if not coverage_lines:
        return True, "无覆盖判定"
    has_evidence = sum(1 for l in coverage_lines if re.search(r'来源|证据|第\d+行|技术方案', l))
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


def _check_five_dimensions(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    dims = ["架构", "接口", "数据", "异常", "性能"]
    found = [d for d in dims if d in report]
    if len(found) >= 4:
        return True, f"{len(found)}/5 维度已检查"
    return False, f"仅 {len(found)}/5 维度（{', '.join(found)}）"


def _check_failure_mode(pd: Path, report: str, phase_id: str) -> tuple[bool, str]:
    if "Failure Mode" in report or "failure mode" in report or "故障模式" in report:
        return True, "已完成"
    return False, "报告中无 Failure Mode 分析"


# ---------------------------------------------------------------------------
# 执行率计算
# ---------------------------------------------------------------------------

_CHECK_FUNCS = {
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
}


def compute_rule_compliance(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """计算规则执行率."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return {}

    pd = _phase_dir(output_dir, project_id, phase_def)
    report = _read_report(pd, phase_id)
    rules = _get_rules(phase_id)

    results: list[dict[str, Any]] = []
    passed = 0

    for rule in rules:
        check_fn = _CHECK_FUNCS.get(rule["check"])
        if not check_fn:
            continue
        ok, detail = check_fn(pd, report, phase_id)
        results.append({
            "id": rule["id"],
            "name": rule["name"],
            "category": rule["category"],
            "passed": ok,
            "detail": detail,
        })
        if ok:
            passed += 1

    total = len(results)
    return {
        "project_id": project_id,
        "phase_id": phase_id,
        "timestamp": datetime.now().isoformat(),
        "total_rules": total,
        "passed": passed,
        "failed": total - passed,
        "compliance_rate": round(passed / max(total, 1), 2),
        "results": results,
    }


def persist_compliance(output_dir: Path, compliance: dict[str, Any]) -> None:
    """持久化规则执行率到 SQLite."""
    insert_metric(output_dir, {
        "project_id": compliance.get("project_id", ""),
        "phase_id": compliance.get("phase_id", ""),
        "metric_name": "rule_compliance_rate",
        "metric_value": compliance.get("compliance_rate", 0),
        "metric_data": {
            "total": compliance.get("total_rules", 0),
            "passed": compliance.get("passed", 0),
            "failed": compliance.get("failed", 0),
        },
        "period": "phase_run",
        "timestamp": compliance.get("timestamp", datetime.now().isoformat()),
    })


def format_compliance_report(compliance: dict[str, Any]) -> str:
    """格式化规则执行率报告."""
    if not compliance:
        return "  规则执行率: 无数据"

    rate = compliance.get("compliance_rate", 0)
    passed = compliance.get("passed", 0)
    total = compliance.get("total_rules", 0)

    lines = [
        f"  规则执行率 — Phase {compliance.get('phase_id', '?')}",
        f"  达标: {passed}/{total} ({rate:.0%})",
    ]

    results = compliance.get("results", [])
    failed = [r for r in results if not r["passed"]]
    if failed:
        lines.append(f"  未达标 ({len(failed)} 项):")
        for r in failed:
            lines.append(f"    [{r['category']}] {r['name']}: {r['detail']}")

    ok = [r for r in results if r["passed"]]
    if ok:
        lines.append(f"  已达标 ({len(ok)} 项):")
        for r in ok:
            lines.append(f"    [OK] {r['name']}: {r['detail']}")

    return "\n".join(lines)
