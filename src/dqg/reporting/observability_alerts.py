"""Observability Alerts + Prometheus: 告警规则 + 指标导出.

从 observability.py 拆分而来。
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

from dqg.json_utils import save_json


def build_alerts(
    history: list[dict[str, Any]],
    current_label: str,
    block_spike_ratio: float,
    phase_failure_threshold: float,
    failure_library: dict[str, Any] | None = None,
    extra_alerts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    today_rows = [r for r in history if r.get("date") == current_label]
    grouped_today: dict[tuple[str, str], dict[str, Any]] = {}
    for row in today_rows:
        grouped_today[(row["project_id"], row["phase"])] = row

    for (project_id, phase), row in grouped_today.items():
        if phase == "ALL":
            historical = [
                r
                for r in history
                if r.get("project_id") == project_id and r.get("phase") == "ALL" and r.get("date") != current_label
            ]
            if historical:
                baseline = mean([float(r.get("block_count", 0)) for r in historical[-7:]])
                current = float(row.get("block_count", 0))
                if baseline > 0 and current >= baseline * block_spike_ratio:
                    alerts.append(
                        {
                            "severity": "HIGH",
                            "rule": "BLOCK_SPIKE",
                            "project_id": project_id,
                            "phase": phase,
                            "message": f"BLOCK 激增: current={current:.0f}, baseline={baseline:.2f}",
                        }
                    )
        else:
            failure_rate = float(row.get("failure_rate", 0))
            finalized = int(row.get("finalized", 0))
            if finalized > 0 and failure_rate >= phase_failure_threshold:
                alerts.append(
                    {
                        "severity": "MEDIUM",
                        "rule": "PHASE_FAILURE_RATE",
                        "project_id": project_id,
                        "phase": phase,
                        "message": f"Phase 失败率过高: {failure_rate:.2%} (threshold={phase_failure_threshold:.2%})",
                    }
                )
    if failure_library:
        for week in failure_library.get("weeks", []):
            failed_cases = int(week.get("failed_cases", 0))
            total_cases = int(week.get("total_cases", 0))
            if failed_cases > 0:
                alerts.append(
                    {
                        "severity": "HIGH",
                        "rule": "FAILURE_LIBRARY_REGRESSION",
                        "project_id": "failure-library",
                        "phase": "ALL",
                        "message": f"失败样例回归失败: week={week.get('label')}, failed={failed_cases}, total={total_cases}",
                    }
                )
    if extra_alerts:
        alerts.extend(extra_alerts)
    return alerts


def write_alerts(output_dir: Path, label: str, alerts: list[dict[str, Any]]) -> tuple[Path, Path]:
    root = output_dir.parent / "observability" / "alerts"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{label}.json"
    md_path = root / f"{label}.md"
    save_json(json_path, {"label": label, "alerts": alerts})
    # 同步写入 SQLite，供 dashboard 实时查询
    try:
        from dqg.store.observability import insert_observe_alerts

        insert_observe_alerts(output_dir, label, alerts)
    except Exception:
        pass
    lines = [f"# DQG 告警 — {label}", ""]
    if not alerts:
        lines.append("- 无异常告警")
    else:
        lines.append("| Severity | Rule | Project | Phase | Message |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in alerts:
            lines.append(
                f"| {item['severity']} | {item['rule']} | {item['project_id']} | {item['phase']} | {item['message']} |"
            )
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def write_prometheus_snapshot(output_dir: Path, payload: dict[str, Any], alerts: list[dict[str, Any]]) -> Path:
    root = output_dir.parent / "observability" / "prometheus"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{payload['label']}.prom"
    lines = [
        "# HELP dqg_project_phase_approval_rate Phase approval rate by project.",
        "# TYPE dqg_project_phase_approval_rate gauge",
        "# HELP dqg_project_avg_duration_seconds Average finalize duration by project.",
        "# TYPE dqg_project_avg_duration_seconds gauge",
        "# HELP dqg_project_gap_closure_rate GAP closure rate by project.",
        "# TYPE dqg_project_gap_closure_rate gauge",
        "# HELP dqg_project_block_count BLOCK count by project.",
        "# TYPE dqg_project_block_count gauge",
        "# HELP dqg_phase_failure_rate Phase failure rate by project and phase.",
        "# TYPE dqg_phase_failure_rate gauge",
        "# HELP dqg_alert_count Alert count in this report.",
        "# TYPE dqg_alert_count gauge",
    ]
    for item in payload["projects"]:
        project = item["project_id"]
        lines.append(f'dqg_project_phase_approval_rate{{project="{project}"}} {item["phase_approval_rate"]}')
        lines.append(f'dqg_project_avg_duration_seconds{{project="{project}"}} {item["avg_duration_seconds"]}')
        lines.append(f'dqg_project_gap_closure_rate{{project="{project}"}} {item["gap_closure_rate"]}')
        lines.append(f'dqg_project_block_count{{project="{project}"}} {item["block_count"]}')
        for phase, stat in item["phase_stats"].items():
            lines.append(f'dqg_phase_failure_rate{{project="{project}",phase="{phase}"}} {stat["failure_rate"]}')
    lines.append(f"dqg_alert_count {len(alerts)}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path
