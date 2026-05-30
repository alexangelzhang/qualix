"""P3: 历史指标异常检测 — Z-score 与 IQR 围栏（metrics_history.jsonl）."""

from __future__ import annotations

import statistics
from typing import Any, Final

# 可调：环境变量在 detect 入口读取，此处为默认值
DEFAULT_MIN_POINTS: Final[int] = 5
DEFAULT_Z_THRESHOLD: Final[float] = 2.5
DEFAULT_IQR_K: Final[float] = 1.5
DEFAULT_MAX_HISTORY: Final[int] = 42


def _float(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _quantile(sorted_vals: list[float], q: float) -> float:
    """q in [0,1], linear interpolation."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _iqr_fences(values: list[float], k: float) -> tuple[float, float]:
    s = sorted(values)
    q1 = _quantile(s, 0.25)
    q3 = _quantile(s, 0.75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def detect_metric_anomalies(
    history: list[dict[str, Any]],
    current_label: str,
    *,
    min_points: int = DEFAULT_MIN_POINTS,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    iqr_k: float = DEFAULT_IQR_K,
    max_history: int = DEFAULT_MAX_HISTORY,
) -> list[dict[str, Any]]:
    """对 `metrics_history.jsonl` 聚合行做 P3 异常检测（不含当日以外的未来日）.

    对每个 (project_id, phase) 与若干数值列，用「当日 vs 历史」对比：
    - Z-score：|z| > z_threshold 且方向表示变差
    - IQR：落入「变差方向」围栏外则记一条（与 Z 独立，双通道易检出尖峰与漂移）
    """
    if not history:
        return []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in history:
        pid = str(row.get("project_id", ""))
        ph = str(row.get("phase", ""))
        if not pid or not ph:
            continue
        grouped.setdefault((pid, ph), []).append(row)

    anomalies: list[dict[str, Any]] = []

    for (project_id, phase), rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda r: str(r.get("date", "")))
        past = [r for r in rows_sorted if str(r.get("date", "")) < current_label][-max_history:]
        today_rows = [r for r in rows_sorted if str(r.get("date", "")) == current_label]
        if not today_rows or len(past) < min_points:
            continue
        cur = today_rows[-1]

        specs: list[tuple[str, str, str]] = [
            ("approval_rate", "higher_better", "approval_rate"),
            ("failure_rate", "lower_better", "failure_rate"),
            ("gap_closure_rate", "higher_better", "gap_closure_rate"),
            ("block_count", "lower_better", "block_count"),
            ("avg_duration_seconds", "lower_better", "avg_duration_seconds"),
        ]
        for field, direction, label in specs:
            hist_vals = [x for x in (_float(r, field) for r in past) if x is not None]
            cur_v = _float(cur, field)
            if cur_v is None or len(hist_vals) < min_points:
                continue

            mean_v = statistics.mean(hist_vals)
            stdev_v = statistics.pstdev(hist_vals) if len(hist_vals) > 1 else 0.0
            z_bad = False
            z_val: float | None = None
            if stdev_v > 1e-9:
                z_val = (cur_v - mean_v) / stdev_v
                if direction == "higher_better" and z_val < -z_threshold:
                    z_bad = True
                if direction == "lower_better" and z_val > z_threshold:
                    z_bad = True

            lo, hi = _iqr_fences(hist_vals, iqr_k)
            iqr_bad = False
            if direction == "higher_better" and cur_v < lo:
                iqr_bad = True
            if direction == "lower_better" and cur_v > hi:
                iqr_bad = True

            if z_bad or iqr_bad:
                methods = []
                if z_bad:
                    methods.append("zscore")
                if iqr_bad:
                    methods.append("iqr")
                anomalies.append(
                    {
                        "project_id": project_id,
                        "phase": phase,
                        "metric": label,
                        "direction": direction,
                        "current": round(cur_v, 6),
                        "hist_mean": round(mean_v, 6),
                        "hist_stdev": round(stdev_v, 6) if stdev_v else 0.0,
                        "z_score": round(z_val, 4) if z_val is not None else None,
                        "iqr_low": round(lo, 6),
                        "iqr_high": round(hi, 6),
                        "methods": methods,
                        "history_points": len(hist_vals),
                    }
                )

    return anomalies


def anomalies_to_alert_dicts(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """转为与 `build_alerts` 一致的告警 dict."""
    out: list[dict[str, Any]] = []
    for a in anomalies:
        zs = a.get("z_score")
        zs_s = f"z={zs}" if zs is not None else "z=n/a"
        msg = (
            f"P3 指标异常 [{','.join(a.get('methods', []))}]: {a['metric']} "
            f"current={a['current']} mean={a['hist_mean']} ({zs_s}) "
            f"IQR=[{a['iqr_low']},{a['iqr_high']}] (n={a['history_points']})"
        )
        out.append(
            {
                "severity": "MEDIUM",
                "rule": "METRIC_ANOMALY",
                "project_id": a["project_id"],
                "phase": a["phase"],
                "message": msg,
            }
        )
    return out
