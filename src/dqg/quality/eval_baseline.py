"""Eval-Driven Development：量化质量基线.

为每个 Phase 定义固定的评估指标，finalize 时自动计算并对比历史基线。
指标退化超过阈值时触发 WARNING，形成数据驱动的迭代闭环。

指标分两类：
1. 确定性指标（从结构化 JSON 计算，精确）
2. LLM-based 指标（需要语义判断，用 Judge 评分代理）
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)

# 指标退化阈值：超过此值触发 WARNING
REGRESSION_THRESHOLD = 0.05  # 5% 退化


# ---------------------------------------------------------------------------
# Phase 指标定义
# ---------------------------------------------------------------------------

PHASE_METRICS: dict[str, list[dict[str, Any]]] = {
    "Q01": [
        {"id": "req_count", "name": "REQ 数量", "type": "count", "field": "requirements", "filter": lambda r: r.get("req_id", "").startswith("REQ-")},
        {"id": "br_count", "name": "BR 数量", "type": "count", "field": "requirements", "filter": lambda r: r.get("req_id", "").startswith("BR-")},
        {"id": "se_count", "name": "SE 数量", "type": "count", "field": "semantic_expectations"},
        {"id": "gap_count", "name": "GAP 数量", "type": "count", "field": "gaps"},
        {"id": "open_count", "name": "OPEN 数量", "type": "count", "field": "open_items"},
        {"id": "se_with_basis", "name": "SE 有判定依据率", "type": "ratio", "numerator_fn": "_count_se_with_basis", "denominator_field": "semantic_expectations"},
        {"id": "gap_with_risk", "name": "GAP 有风险等级率", "type": "ratio", "numerator_fn": "_count_gap_with_risk", "denominator_field": "gaps"},
        {"id": "open_with_owner", "name": "OPEN 有决策方率", "type": "ratio", "numerator_fn": "_count_open_with_owner", "denominator_field": "open_items"},
    ],
    "Q04": [
        {"id": "req_coverage_rate", "name": "REQ 覆盖率", "type": "custom", "fn": "_calc_coverage_rate", "args": {"dimension": "REQ"}},
        {"id": "se_coverage_rate", "name": "SE 覆盖率", "type": "custom", "fn": "_calc_coverage_rate", "args": {"dimension": "SE"}},
        {"id": "gap_closure_rate", "name": "GAP 闭环率", "type": "custom", "fn": "_calc_closure_rate", "args": {"field": "gap_closure"}},
        {"id": "missing_count", "name": "MISSING 数量", "type": "custom", "fn": "_count_status", "args": {"status": "MISSING"}},
    ],
    "Q03": [
        {"id": "critical_count", "name": "Critical 问题数", "type": "json_field", "field": "critical_count"},
        {"id": "important_count", "name": "Important 问题数", "type": "json_field", "field": "important_count"},
        {"id": "total_issues", "name": "总问题数", "type": "custom", "fn": "_count_issues"},
        {"id": "fm_count", "name": "Failure Mode 数量", "type": "count", "field": "failure_modes"},
    ],
    "Q05": [
        {"id": "eut_count", "name": "EUT 数量", "type": "count", "field": "eut_matrix"},
        {"id": "happy_path_ratio", "name": "Happy Path 占比", "type": "custom", "fn": "_calc_path_ratio", "args": {"path_type": "Happy"}},
        {"id": "exception_path_ratio", "name": "Exception Path 占比", "type": "custom", "fn": "_calc_path_ratio", "args": {"path_type": "Exception"}},
    ],
    "Q06": [
        {"id": "covered_rate", "name": "COVERED 率", "type": "custom", "fn": "_count_status_rate", "args": {"status": "COVERED"}},
        {"id": "wrong_target_count", "name": "WRONG_TARGET 数量", "type": "custom", "fn": "_count_status", "args": {"status": "WRONG_TARGET"}},
        {"id": "missing_count", "name": "MISSING 数量", "type": "custom", "fn": "_count_status", "args": {"status": "MISSING"}},
    ],
    "Q07": [
        {"id": "critical_count", "name": "Critical 问题数", "type": "json_field", "field": "critical_count"},
        {"id": "total_findings", "name": "总发现数", "type": "count", "field": "issues"},
        {"id": "blocker_count", "name": "BLOCKER 数量", "type": "custom", "fn": "_count_severity", "args": {"severity": "CRITICAL"}},
    ],
}


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------


def compute_eval_metrics(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """计算指定 Phase 的评估指标."""
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    dir_suffix = PHASE_DIR_MAP.get(phase_id)
    if not json_file or not dir_suffix:
        return None

    json_path = output_dir / project_id / dir_suffix / json_file
    data = load_json(json_path)
    if not data:
        return None

    metric_defs = PHASE_METRICS.get(phase_id, [])
    if not metric_defs:
        return None

    metrics: dict[str, float] = {}
    for mdef in metric_defs:
        value = _compute_single_metric(mdef, data)
        if value is not None:
            metrics[mdef["id"]] = value

    return {
        "project_id": project_id,
        "phase_id": phase_id,
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics,
    }


def compare_with_baseline(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    current_metrics: dict[str, Any],
) -> dict[str, Any]:
    """对比当前指标与历史基线，输出 delta."""
    baseline = _load_baseline(output_dir, project_id, phase_id)

    comparisons: list[dict[str, Any]] = []
    regressions: list[str] = []

    current = current_metrics.get("metrics", {})

    for metric_id, current_value in current.items():
        baseline_value = baseline.get(metric_id)
        if baseline_value is None:
            comparisons.append({
                "metric": metric_id,
                "current": current_value,
                "baseline": None,
                "delta": None,
                "status": "NEW",
            })
            continue

        if isinstance(current_value, (int, float)) and isinstance(baseline_value, (int, float)):
            delta = current_value - baseline_value
            # 对于 rate 类指标，退化 = 下降；对于 count 类指标（如 MISSING），退化 = 上升
            is_rate = "rate" in metric_id or "ratio" in metric_id or "basis" in metric_id or "owner" in metric_id or "risk" in metric_id
            is_regression = (delta < -REGRESSION_THRESHOLD) if is_rate else False

            status = "REGRESSION" if is_regression else "IMPROVED" if delta > REGRESSION_THRESHOLD else "STABLE"
            comparisons.append({
                "metric": metric_id,
                "current": round(current_value, 4),
                "baseline": round(baseline_value, 4),
                "delta": round(delta, 4),
                "status": status,
            })
            if is_regression:
                regressions.append(f"{metric_id}: {baseline_value:.2%} → {current_value:.2%} (delta={delta:+.2%})")
        else:
            comparisons.append({
                "metric": metric_id,
                "current": current_value,
                "baseline": baseline_value,
                "delta": None,
                "status": "UNCHANGED" if current_value == baseline_value else "CHANGED",
            })

    return {
        "comparisons": comparisons,
        "regressions": regressions,
        "has_regression": len(regressions) > 0,
    }


def write_eval_metrics(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """计算指标 + 对比基线 + 写入文件."""
    metrics = compute_eval_metrics(output_dir, project_id, phase_id)
    if not metrics:
        return None

    comparison = compare_with_baseline(output_dir, project_id, phase_id, metrics)

    # 写入当前指标
    from dqg.constants import PHASE_DIR_MAP
    dir_suffix = PHASE_DIR_MAP.get(phase_id, f"phase{phase_id}")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    result = {**metrics, **comparison}
    metrics_path = int_dir / "_eval_metrics.json"
    save_json(metrics_path, result)

    # 更新基线（用当前值作为下次的基线）
    _save_baseline(output_dir, project_id, phase_id, metrics["metrics"])

    # 日志
    if comparison["has_regression"]:
        for r in comparison["regressions"]:
            log.warning("Eval regression: Phase %s %s", phase_id, r)
    else:
        log.info("Eval metrics: Phase %s — %d metrics, no regression", phase_id, len(metrics["metrics"]))

    return metrics_path


# ---------------------------------------------------------------------------
# 内部计算函数
# ---------------------------------------------------------------------------


def _compute_single_metric(mdef: dict[str, Any], data: dict[str, Any]) -> float | None:
    """计算单个指标."""
    mtype = mdef["type"]

    if mtype == "count":
        items = data.get(mdef["field"], [])
        if not isinstance(items, list):
            return None
        filt = mdef.get("filter")
        if filt:
            return sum(1 for item in items if filt(item))
        return len(items)

    if mtype == "json_field":
        return data.get(mdef["field"], 0)

    if mtype == "ratio":
        denom_items = data.get(mdef["denominator_field"], [])
        if not denom_items:
            return None
        numerator_fn = _METRIC_FNS.get(mdef["numerator_fn"])
        if not numerator_fn:
            return None
        numerator = numerator_fn(data)
        return numerator / len(denom_items) if len(denom_items) > 0 else 0.0

    if mtype == "custom":
        fn = _METRIC_FNS.get(mdef["fn"])
        if not fn:
            return None
        return fn(data, **mdef.get("args", {}))

    return None


def _count_se_with_basis(data: dict[str, Any]) -> int:
    """统计有判定依据的 SE 数量."""
    se_list = data.get("semantic_expectations", [])
    return sum(1 for se in se_list if se.get("mapping_target") or se.get("judgment_basis"))


def _count_gap_with_risk(data: dict[str, Any]) -> int:
    """统计有风险等级的 GAP 数量."""
    gaps = data.get("gaps", [])
    return sum(1 for g in gaps if g.get("risk"))


def _count_open_with_owner(data: dict[str, Any]) -> int:
    """统计有决策方的 OPEN 数量."""
    opens = data.get("open_items", [])
    return sum(1 for o in opens if o.get("decision_owner"))


def _calc_coverage_rate(data: dict[str, Any], dimension: str = "REQ") -> float:
    """计算覆盖率."""
    summary = data.get("coverage_summary", [])
    for s in summary:
        if s.get("dimension") == dimension:
            return s.get("coverage_rate", 0.0)
    return 0.0


def _calc_closure_rate(data: dict[str, Any], field: str = "gap_closure") -> float:
    """计算闭环率."""
    items = data.get(field, [])
    if not items:
        return 0.0
    closed = sum(1 for i in items if i.get("status") in ("已闭环", "部分闭环"))
    return closed / len(items)


def _count_status(data: dict[str, Any], status: str = "MISSING") -> int:
    """统计特定覆盖状态的数量."""
    for field in ("se_coverage", "req_coverage", "scenarios"):
        items = data.get(field, [])
        if items:
            return sum(1 for i in items if i.get("status") == status)
    return 0


def _count_status_rate(data: dict[str, Any], status: str = "COVERED") -> float:
    """统计特定覆盖状态的比率."""
    for field in ("se_coverage", "req_coverage", "scenarios"):
        items = data.get(field, [])
        if items:
            count = sum(1 for i in items if i.get("status") == status)
            return count / len(items) if items else 0.0
    return 0.0


def _count_issues(data: dict[str, Any]) -> int:
    """统计总问题数."""
    return len(data.get("issues", []))


def _count_severity(data: dict[str, Any], severity: str = "CRITICAL") -> int:
    """统计特定严重级别的问题数."""
    return sum(1 for i in data.get("issues", []) if i.get("severity") == severity)


def _calc_path_ratio(data: dict[str, Any], path_type: str = "Happy") -> float:
    """计算 EUT 路径类型占比."""
    euts = data.get("eut_matrix", [])
    if not euts:
        return 0.0
    count = sum(1 for e in euts if e.get("route_type", "").startswith(path_type) or e.get("path_type", "").startswith(path_type))
    return count / len(euts)


# 函数注册表
_METRIC_FNS: dict[str, Any] = {
    "_count_se_with_basis": _count_se_with_basis,
    "_count_gap_with_risk": _count_gap_with_risk,
    "_count_open_with_owner": _count_open_with_owner,
    "_calc_coverage_rate": _calc_coverage_rate,
    "_calc_closure_rate": _calc_closure_rate,
    "_count_status": _count_status,
    "_count_status_rate": _count_status_rate,
    "_count_issues": _count_issues,
    "_count_severity": _count_severity,
    "_calc_path_ratio": _calc_path_ratio,
}


# ---------------------------------------------------------------------------
# 基线管理
# ---------------------------------------------------------------------------


def _load_baseline(output_dir: Path, project_id: str, phase_id: str) -> dict[str, float]:
    """加载历史基线."""
    baseline_path = output_dir / project_id / "_eval_baseline.json"
    if not baseline_path.exists():
        return {}
    data = load_json(baseline_path)
    if not isinstance(data, dict):
        return {}
    return data.get(phase_id, {})


def _save_baseline(output_dir: Path, project_id: str, phase_id: str, metrics: dict[str, float]) -> None:
    """保存基线（更新指定 Phase 的指标）."""
    baseline_path = output_dir / project_id / "_eval_baseline.json"
    baseline: dict[str, Any] = {}
    if baseline_path.exists():
        data = load_json(baseline_path)
        if isinstance(data, dict):
            baseline = data
    baseline[phase_id] = metrics
    save_json(baseline_path, baseline)


# ---------------------------------------------------------------------------
# Backward-compat re-export: holdout validation moved to eval_holdout.py
# ---------------------------------------------------------------------------
from dqg.quality.eval_holdout import validate_against_holdout  # noqa: F401
