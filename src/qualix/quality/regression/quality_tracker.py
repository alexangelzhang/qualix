"""规则级质量追踪：比对结构化输出与 bug 案例库，生成健康度报告."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from qualix.constants import STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS, phase_dir_by_id
from qualix.json_utils import load_json
from qualix.tracking.bug_cases import load_cases_by_phase

if TYPE_CHECKING:
    from pathlib import Path

# 二级分类 → 检测信号映射
_PHASE_C_SIGNALS: Final = MappingProxyType(
    {
        "函数未覆盖": ["MISSING"],
        "函数正常分支未覆盖": ["MISSING", "PARTIAL"],
        "函数异常分支未覆盖": ["MISSING"],
        "函数覆盖assert不对": ["WRONG_TARGET"],
        "有单测未运行": ["MISSING"],
    }
)

_PHASE_A_SIGNALS: Final = MappingProxyType(
    {
        "需求实现遗漏": ["GAP", "OPEN"],
        "需求遗漏": ["GAP", "OPEN"],
        "需求理解未对齐": ["GAP"],
        "安全问题": ["GAP"],
        "幂等": ["GAP", "SE"],
    }
)


def _load_structured_output(output_dir: Path, project_id: str, phase: str) -> dict[str, Any] | None:
    """加载 Phase 的结构化 JSON 产物."""
    json_file = STRUCTURED_JSON_MAP.get(phase)
    if not json_file or phase not in PHASE_DEFS:
        return None
    path = phase_dir_by_id(output_dir, project_id, phase) / json_file
    return load_json(path)


def track_rule_quality(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """比对结构化输出与 bug 案例库，生成规则健康度报告."""
    cases = load_cases_by_phase(phase_id)
    structured = _load_structured_output(output_dir, project_id, phase_id)

    report: dict[str, Any] = {
        "phase": phase_id,
        "project_id": project_id,
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(cases),
        "matched_signals": [],
        "potential_new_issues": [],
        "health_score": 1.0,
    }

    if not structured:
        return report

    if phase_id == "Q06":
        _track_phase_c(structured, cases, report)
    elif phase_id == "Q01":
        _track_phase_a(structured, cases, report)
    elif phase_id == "Q03":
        _track_phase_a6(structured, cases, report)

    # 计算健康度
    open_cases = [c for c in cases if c.get("status") == "open"]
    if open_cases:
        matched = len(report["matched_signals"])
        report["health_score"] = round(1.0 - matched / max(len(open_cases), 1), 2)

    return report


def _track_phase_c(structured: dict, cases: list[dict], report: dict) -> None:
    """Phase C: 检查审计结果中是否存在已知问题模式."""
    audit_items = structured.get("audit_items", [])
    status_counts: dict[str, int] = defaultdict(int)
    for item in audit_items:
        status = item.get("status", "")
        status_counts[status] += 1

    for case in cases:
        if case.get("status") != "open":
            continue
        cat2 = case.get("source", {}).get("category2", "") or ""
        signals = _PHASE_C_SIGNALS.get(cat2, [])
        for signal in signals:
            if status_counts.get(signal, 0) > 0:
                report["matched_signals"].append(
                    {
                        "case_id": case.get("case_id"),
                        "category": cat2,
                        "signal": signal,
                        "count": status_counts[signal],
                    }
                )
                break

    if status_counts.get("WRONG_TARGET", 0) > 3:
        report["potential_new_issues"].append(
            {
                "signal": "WRONG_TARGET 数量偏高",
                "count": status_counts["WRONG_TARGET"],
                "suggestion": "检查断言强度规则是否需要加强",
            }
        )
    if status_counts.get("MISSING", 0) > 5:
        report["potential_new_issues"].append(
            {
                "signal": "MISSING 数量偏高",
                "count": status_counts["MISSING"],
                "suggestion": "检查是否有未覆盖的核心分支",
            }
        )


def _track_phase_a(structured: dict, cases: list[dict], report: dict) -> None:
    """Phase A: 检查需求分析结果中是否存在已知问题模式."""
    gaps = structured.get("gaps", [])
    gap_count = len(gaps)

    for case in cases:
        if case.get("status") != "open":
            continue
        cat2 = case.get("source", {}).get("category2", "") or ""
        if cat2 in ("需求实现遗漏", "需求遗漏") and gap_count == 0:
            report["matched_signals"].append(
                {
                    "case_id": case.get("case_id"),
                    "category": cat2,
                    "signal": "zero_gaps",
                    "suggestion": "GAP 为 0 可能意味着遗漏了隐式需求",
                }
            )
            break

    se_list = structured.get("semantic_expectations", [])
    req_list = structured.get("requirements", [])
    if req_list and not se_list:
        report["potential_new_issues"].append(
            {
                "signal": "有 REQ 但无 SE",
                "suggestion": "每个 REQ 应至少有一个可验证的 SE",
            }
        )


def _track_phase_a6(structured: dict, cases: list[dict], report: dict) -> None:
    """Phase A.6: 检查质量评审结果."""
    failure_modes = structured.get("failure_modes", [])
    critical_gaps = [fm for fm in failure_modes if fm.get("status") == "CRITICAL_GAP"]
    if critical_gaps:
        report["potential_new_issues"].append(
            {
                "signal": f"存在 {len(critical_gaps)} 个 CRITICAL_GAP",
                "suggestion": "CRITICAL_GAP 应阻断审批",
            }
        )


def format_quality_report(report: dict[str, Any]) -> str:
    """格式化规则健康度报告."""
    lines = [
        f"Skill 规则健康度 — Phase {report['phase']} ({report['project_id']})",
        f"  案例库: {report['total_cases']} 条 | 健康度: {report['health_score']:.0%}",
    ]
    if report["matched_signals"]:
        lines.append(f"  命中已知问题模式: {len(report['matched_signals'])} 条")
        for m in report["matched_signals"][:5]:
            lines.append(f"    - [{m.get('category', '')}] {m.get('signal', '')} (case: {m.get('case_id', '')})")
    if report["potential_new_issues"]:
        lines.append(f"  潜在新问题: {len(report['potential_new_issues'])} 条")
        for p in report["potential_new_issues"]:
            lines.append(f"    - {p['signal']}: {p.get('suggestion', '')}")
    return "\n".join(lines)
