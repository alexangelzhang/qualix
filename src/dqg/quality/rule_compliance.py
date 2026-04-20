"""规则执行率追踪（facade）.

扫描 Phase 产物，检测每条规则是否被实际遵守，
输出执行率报告，持久化到 SQLite。

本文件为 facade 入口，实际逻辑拆分至：
- rule_definitions.py — 规则定义常量和数据结构
- rule_checks.py — 检查函数和映射表
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.store import insert_metric

from dqg.quality.rule_definitions import get_rules
from dqg.quality.rule_checks import CHECK_FUNCS, read_report


# ---------------------------------------------------------------------------
# 执行率计算
# ---------------------------------------------------------------------------

def compute_rule_compliance(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """计算规则执行率（规则检查并行执行）."""
    from concurrent.futures import ThreadPoolExecutor

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return {}

    pd = _phase_dir(output_dir, project_id, phase_def)
    report = read_report(pd, phase_id)
    rules = get_rules(phase_id)

    def _check_one(rule: dict[str, Any]) -> dict[str, Any] | None:
        check_fn = CHECK_FUNCS.get(rule["check"])
        if not check_fn:
            return None
        ok, detail = check_fn(pd, report, phase_id)
        return {
            "id": rule["id"],
            "name": rule["name"],
            "category": rule["category"],
            "passed": ok,
            "detail": detail,
        }

    results: list[dict[str, Any]] = []
    if len(rules) <= 2:
        for rule in rules:
            r = _check_one(rule)
            if r:
                results.append(r)
    else:
        with ThreadPoolExecutor(max_workers=min(len(rules), 6)) as pool:
            for r in pool.map(_check_one, rules):
                if r:
                    results.append(r)

    passed = sum(1 for r in results if r["passed"])
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


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------

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
