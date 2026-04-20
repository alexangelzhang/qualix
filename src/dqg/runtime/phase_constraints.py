"""Phase Constraints: DSL 约束断言 + 报告结构检查.

从 phase_contract.py 拆分而来，负责：
1. PHASE_CONSTRAINTS DSL 定义
2. 指标解析（_resolve_metric）
3. 约束执行（enforce_phase_constraints）
4. 报告结构检查（check_report_structure）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final
from types import MappingProxyType

from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# DSL 约束：可执行断言
# ---------------------------------------------------------------------------

# 每个 Phase 的硬性约束，格式：
# {"metric": str, "op": ">="|"<="|"=="|">"|"<", "threshold": float, "source": str, "block_if_fail": bool}
PHASE_CONSTRAINTS: Final = MappingProxyType({
    "Q03": [
        {"metric": "critical_count", "op": "==", "threshold": 0,
         "source": "phase_a6_structured.json:issues[severity=CRITICAL]",
         "block_if_fail": True, "label": "无 CRITICAL 问题"},
    ],
    "Q04": [
        {"metric": "req_coverage_rate", "op": ">=", "threshold": 0.8,
         "source": "phase_a5_structured.json:coverage_summary[dimension=REQ]",
         "block_if_fail": True, "label": "需求覆盖率 ≥ 80%"},
        {"metric": "se_coverage_rate", "op": ">=", "threshold": 0.8,
         "source": "phase_a5_structured.json:coverage_summary[dimension=SE]",
         "block_if_fail": True, "label": "SE 覆盖率 ≥ 80%"},
    ],
    "Q06": [
        {"metric": "se_coverage_rate", "op": ">=", "threshold": 0.8,
         "source": "phase_c_structured.json:audit_items[status=COVERED]",
         "block_if_fail": True, "label": "SE 覆盖率 ≥ 80%"},
    ],
    "Q07": [
        {"metric": "blocker_count", "op": "==", "threshold": 0,
         "source": "phase_d_structured.json:findings[severity=BLOCKER]",
         "block_if_fail": True, "label": "无 BLOCKER 问题"},
    ],
})


def _resolve_metric(output_dir: Path, project_id: str, phase_id: str, metric: str) -> float | None:
    """从结构化产物中解析指标值。"""
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    dir_suffix = PHASE_DIR_MAP.get(phase_id, "")
    structured_file = STRUCTURED_JSON_MAP.get(phase_id, "")
    if not dir_suffix or not structured_file:
        return None

    path = output_dir / project_id / dir_suffix / structured_file
    data = load_json(path)
    if not data:
        return None

    if metric == "critical_count":
        issues = data.get("issues", [])
        return float(sum(1 for i in issues if i.get("severity") in ("CRITICAL", "BLOCKER")))
    if metric == "blocker_count":
        findings = data.get("findings", [])
        return float(sum(1 for f in findings if f.get("severity") in ("BLOCKER", "CRITICAL")))
    if metric == "req_coverage_rate":
        summary = data.get("coverage_summary", [])
        for row in summary:
            if row.get("dimension") in ("REQ", "req"):
                return float(row.get("coverage_rate", 0))
    if metric == "se_coverage_rate":
        # Q04: coverage_summary
        summary = data.get("coverage_summary", [])
        for row in summary:
            if row.get("dimension") in ("SE", "se"):
                return float(row.get("coverage_rate", 0))
        # Q06: audit_items
        items = data.get("audit_items", [])
        if items:
            covered = sum(1 for i in items if i.get("status") == "COVERED")
            return covered / len(items)
    return None


def _eval_constraint(value: float, op: str, threshold: float) -> bool:
    ops = {">=": value >= threshold, "<=": value <= threshold,
           "==": value == threshold, ">": value > threshold, "<": value < threshold}
    return ops.get(op, False)


def enforce_phase_constraints(
    output_dir: Path, project_id: str, phase_id: str,
) -> list[dict]:
    """执行 Phase DSL 约束断言，返回违反的约束列表。

    每条违反项格式：{"label", "metric", "op", "threshold", "actual", "block_if_fail"}
    """
    constraints = PHASE_CONSTRAINTS.get(phase_id, [])
    violations = []
    for c in constraints:
        value = _resolve_metric(output_dir, project_id, phase_id, c["metric"])
        if value is None:
            continue
        if not _eval_constraint(value, c["op"], c["threshold"]):
            violations.append({
                "label": c["label"],
                "metric": c["metric"],
                "op": c["op"],
                "threshold": c["threshold"],
                "actual": value,
                "block_if_fail": c.get("block_if_fail", False),
            })
    return violations


def check_report_structure(report_content: str, phase: str) -> dict[str, Any]:
    """Check report against required_report_sections from phase_registry.

    Uses fuzzy matching: section header must contain canonical name or any alias.

    Returns:
        {"passed": bool, "missing": [str], "found": [str]}
    """
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase, {})
    required = phase_def.get("required_report_sections", [])
    if not required:
        return {"passed": True, "missing": [], "found": []}

    headers = re.findall(r"^#{2,3}\s+(.+)$", report_content, re.MULTILINE)
    headers_lower = [h.strip().lower() for h in headers]

    found = []
    missing = []
    for section in required:
        canonical = section["canonical"]
        aliases = section.get("aliases", [])
        all_names = [canonical] + aliases

        matched = False
        for name in all_names:
            name_lower = name.lower()
            if any(name_lower in h for h in headers_lower):
                matched = True
                break

        if matched:
            found.append(canonical)
        else:
            missing.append(canonical)

    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "found": found,
    }
