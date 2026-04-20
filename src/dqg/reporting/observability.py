"""Observability reporting and alerting based on telemetry."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Final

from dqg.json_utils import dump_jsonl, save_json
from dqg.reporting.collect_metrics import collect_all_metrics
from dqg.constants import PHASE_DIR_MAP, REPORT_MAP
from dqg.tracking.regression import build_failure_trend
from dqg.reporting.telemetry import PhaseRunRecord, load_records

ALLOWED_PHASES: Final = frozenset({"Q01", "Q04", "Q03", "Q05", "Q06", "Q07"})
DATE_FMT = "%Y-%m-%d"


@dataclass
class Period:
    start: datetime
    end: datetime
    label: str


def _parse_date(value: str | None) -> date:
    if value is None:
        return datetime.now().date()
    return datetime.strptime(value, DATE_FMT).date()


def _build_period(period: str, anchor: date) -> Period:
    if period == "daily":
        start = datetime.combine(anchor, datetime.min.time())
        end = start + timedelta(days=1)
        return Period(start=start, end=end, label=anchor.strftime(DATE_FMT))
    if period == "weekly":
        week_start = anchor - timedelta(days=anchor.weekday())
        start = datetime.combine(week_start, datetime.min.time())
        end = start + timedelta(days=7)
        week_end = week_start + timedelta(days=6)
        return Period(start=start, end=end, label=f"{week_start.strftime(DATE_FMT)}_to_{week_end.strftime(DATE_FMT)}")
    raise ValueError(f"Unsupported period: {period}")


def _record_in_period(record: PhaseRunRecord, period: Period) -> bool:
    ts = datetime.fromisoformat(record.timestamp)
    return period.start <= ts < period.end


def _discover_projects(output_dir: Path) -> list[str]:
    projects: set[str] = set()
    # 新结构： output/{project_id}/{project_id}_telemetry.jsonl
    for path in output_dir.glob("*/*_telemetry.jsonl"):
        projects.add(path.name.removesuffix("_telemetry.jsonl"))
    # 兼容旧结构： output/{project_id}_telemetry.jsonl
    for path in output_dir.glob("*_telemetry.jsonl"):
        projects.add(path.name.removesuffix("_telemetry.jsonl"))
    return sorted(projects)


def _load_period_records(
    output_dir: Path,
    project_id: str,
    period: Period,
    phase_filter: str | None,
) -> list[PhaseRunRecord]:
    records = load_records(output_dir, project_id)
    in_period = [r for r in records if _record_in_period(r, period)]
    if phase_filter:
        in_period = [r for r in in_period if r.phase_id == phase_filter]
    return in_period


def _phase_from_validation_errors(records: list[PhaseRunRecord], phase: str) -> int:
    return sum(1 for r in records if r.phase_id == phase and r.action == "finalize" and bool(r.validation_errors))


def _extract_phase_d_blockers(output_dir: Path, project_id: str) -> int:
    report = output_dir / project_id / PHASE_DIR_MAP["Q07"] / REPORT_MAP["Q07"]
    if not report.exists():
        return 0
    text = report.read_text(encoding="utf-8")
    return len(re.findall(r"\bBLOCKER\b", text))


def _project_metrics(output_dir: Path, project_id: str, records: list[PhaseRunRecord]) -> dict[str, Any]:
    finalize_records = [r for r in records if r.action == "finalize"]
    approve_records = [r for r in records if r.action == "approve"]
    avg_duration = mean([r.duration_seconds for r in finalize_records if r.duration_seconds is not None]) if finalize_records else 0.0
    approval_rate = (len(approve_records) / len(finalize_records)) if finalize_records else 0.0

    phase_stats: dict[str, dict[str, Any]] = {}
    for phase in sorted(ALLOWED_PHASES):
        phase_finalize = [r for r in finalize_records if r.phase_id == phase]
        phase_approve = [r for r in approve_records if r.phase_id == phase]
        phase_error = _phase_from_validation_errors(records, phase)
        phase_avg_duration = (
            mean([r.duration_seconds for r in phase_finalize if r.duration_seconds is not None]) if phase_finalize else 0.0
        )
        phase_stats[phase] = {
            "finalized": len(phase_finalize),
            "approved": len(phase_approve),
            "approval_rate": round((len(phase_approve) / len(phase_finalize)), 4) if phase_finalize else 0.0,
            "avg_duration_seconds": round(phase_avg_duration, 2),
            "validation_error_count": phase_error,
            "failure_rate": round((phase_error / len(phase_finalize)), 4) if phase_finalize else 0.0,
        }

    collected = collect_all_metrics(output_dir, project_id)
    gap_closure_rate = float(collected.get("summary", {}).get("gap_closure_rate", 0.0))
    critical_gaps = int(collected.get("summary", {}).get("critical_gaps", 0))
    blockers = _extract_phase_d_blockers(output_dir, project_id)
    block_count = critical_gaps + blockers

    return {
        "project_id": project_id,
        "record_count": len(records),
        "finalized": len(finalize_records),
        "approved": len(approve_records),
        "phase_approval_rate": round(approval_rate, 4),
        "avg_duration_seconds": round(avg_duration, 2),
        "gap_closure_rate": round(gap_closure_rate, 4),
        "block_count": block_count,
        "phase_stats": phase_stats,
    }


def _report_paths(output_dir: Path, period_name: str, label: str) -> tuple[Path, Path]:
    root = output_dir.parent / "observability" / "reports" / period_name
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{label}.json", root / f"{label}.md"


def _history_path(output_dir: Path) -> Path:
    root = output_dir.parent / "observability"
    root.mkdir(parents=True, exist_ok=True)
    return root / "metrics_history.jsonl"


def _failure_history_path(output_dir: Path) -> Path:
    return output_dir.parent / "regression" / "failure-library" / "history.jsonl"


def _write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"# DQG {payload['period']} 报告")
    lines.append("")
    lines.append(f"- 时间窗口: `{payload['window']['start']}` ~ `{payload['window']['end']}`")
    lines.append(f"- 项目过滤: `{payload['filters']['project'] or 'all'}`")
    lines.append(f"- Phase 过滤: `{payload['filters']['phase'] or 'all'}`")
    lines.append("")
    lines.append("## 项目摘要")
    lines.append("")
    lines.append("| Project | Approval Rate | Avg Duration(s) | GAP Closure | BLOCK | Finalized |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for item in payload["projects"]:
        lines.append(
            f"| {item['project_id']} | {item['phase_approval_rate']:.2%} | {item['avg_duration_seconds']:.2f} | "
            f"{item['gap_closure_rate']:.2%} | {item['block_count']} | {item['finalized']} |"
        )
    lines.append("")
    lines.append("## Phase 明细")
    lines.append("")
    lines.append("| Project | Phase | Approval Rate | Failure Rate | Avg Duration(s) |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for item in payload["projects"]:
        for phase, stat in item["phase_stats"].items():
            if stat["finalized"] == 0 and stat["approved"] == 0:
                continue
            lines.append(
                f"| {item['project_id']} | {phase} | {stat['approval_rate']:.2%} | "
                f"{stat['failure_rate']:.2%} | {stat['avg_duration_seconds']:.2f} |"
            )
    failure_library = payload.get("failure_library", {})
    weeks = failure_library.get("weeks", [])
    if weeks:
        lines.append("")
        lines.append("## Failure Library")
        lines.append("")
        lines.append("| Week | Error Type | Total | Failed | Pass Rate |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for week in weeks:
            for error_type, stat in week["by_error_type"].items():
                lines.append(
                    f"| {week['label']} | {error_type} | {stat['total']} | {stat['failed']} | {stat['pass_rate']:.2%} |"
                )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _append_history(output_dir: Path, period_name: str, report_payload: dict[str, Any]) -> int:
    path = _history_path(output_dir)
    rows = []
    for item in report_payload["projects"]:
        rows.append(
            {
                "date": report_payload["label"],
                "period": period_name,
                "project_id": item["project_id"],
                "phase": "ALL",
                "approval_rate": item["phase_approval_rate"],
                "avg_duration_seconds": item["avg_duration_seconds"],
                "gap_closure_rate": item["gap_closure_rate"],
                "block_count": item["block_count"],
                "finalized": item["finalized"],
            }
        )
        for phase, stat in item["phase_stats"].items():
            rows.append(
                {
                    "date": report_payload["label"],
                    "period": period_name,
                    "project_id": item["project_id"],
                    "phase": phase,
                    "approval_rate": stat["approval_rate"],
                    "failure_rate": stat["failure_rate"],
                    "avg_duration_seconds": stat["avg_duration_seconds"],
                    "validation_error_count": stat["validation_error_count"],
                    "finalized": stat["finalized"],
                }
            )
    with open(path, "a", encoding="utf-8") as file:
        for row in rows:
            file.write(dump_jsonl(row))
    return len(rows)


def _load_history(output_dir: Path) -> list[dict[str, Any]]:
    path = _history_path(output_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _build_alerts(
    history: list[dict[str, Any]],
    current_label: str,
    block_spike_ratio: float,
    phase_failure_threshold: float,
    failure_library: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from dqg.reporting.observability_alerts import build_alerts
    return build_alerts(history, current_label, block_spike_ratio, phase_failure_threshold, failure_library)


def _write_alerts(output_dir: Path, label: str, alerts: list[dict[str, Any]]) -> tuple[Path, Path]:
    from dqg.reporting.observability_alerts import write_alerts
    return write_alerts(output_dir, label, alerts)


def _write_prometheus_snapshot(output_dir: Path, payload: dict[str, Any], alerts: list[dict[str, Any]]) -> Path:
    from dqg.reporting.observability_alerts import write_prometheus_snapshot
    return write_prometheus_snapshot(output_dir, payload, alerts)


def generate_report(
    output_dir: Path,
    *,
    period_name: str,
    anchor: date,
    project_filter: str | None = None,
    phase_filter: str | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    period = _build_period(period_name, anchor)
    projects = [project_filter] if project_filter else _discover_projects(output_dir)
    rows = []
    for project_id in projects:
        records = _load_period_records(output_dir, project_id, period, phase_filter)
        if not records:
            continue
        rows.append(_project_metrics(output_dir, project_id, records))
    payload = {
        "label": period.label,
        "period": period_name,
        "window": {
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
        },
        "filters": {
            "project": project_filter,
            "phase": phase_filter,
        },
        "projects": rows,
    }
    payload["failure_library"] = build_failure_trend(_failure_history_path(output_dir), period="weekly")
    json_path, md_path = _report_paths(output_dir, period_name, period.label)
    save_json(json_path, payload)
    _write_markdown_report(md_path, payload)
    return payload, json_path, md_path


def _cmd_report(args: argparse.Namespace) -> int:
    output_dir = Path(args.base_dir).resolve() / "output"
    payload, json_path, md_path = generate_report(
        output_dir,
        period_name=args.period,
        anchor=_parse_date(args.date),
        project_filter=args.project,
        phase_filter=args.phase,
    )
    print(f"报告已生成: {json_path}")
    print(f"报告已生成: {md_path}")
    print(f"项目数: {len(payload['projects'])}")
    return 0


def _cmd_daily(args: argparse.Namespace) -> int:
    output_dir = Path(args.base_dir).resolve() / "output"
    payload, json_path, md_path = generate_report(
        output_dir,
        period_name="daily",
        anchor=_parse_date(args.date),
        project_filter=args.project,
        phase_filter=args.phase,
    )
    inserted = _append_history(output_dir, "daily", payload)
    history = _load_history(output_dir)
    alerts = _build_alerts(
        history,
        payload["label"],
        block_spike_ratio=args.block_spike_ratio,
        phase_failure_threshold=args.phase_failure_threshold,
        failure_library=payload.get("failure_library"),
    )
    alerts_json, alerts_md = _write_alerts(output_dir, payload["label"], alerts)
    prom_path = _write_prometheus_snapshot(output_dir, payload, alerts)
    print(f"日报已生成: {json_path}")
    print(f"日报已生成: {md_path}")
    print(f"历史入库行数: {inserted}")
    print(f"告警输出: {alerts_json}")
    print(f"告警输出: {alerts_md}")
    print(f"Prometheus 指标: {prom_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DQG observability and alerting")
    parser.add_argument("--base-dir", default=".", help="项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="生成日报/周报")
    p_report.add_argument("--period", choices=["daily", "weekly"], default="daily")
    p_report.add_argument("--date", default=None, help="锚点日期 YYYY-MM-DD，默认今天")
    p_report.add_argument("--project", default=None, help="项目过滤")
    p_report.add_argument("--phase", default=None, choices=sorted(ALLOWED_PHASES), help="Phase 过滤")
    p_report.set_defaults(handler=_cmd_report)

    p_daily = sub.add_parser("daily", help="生成每日报告 + 入库 + 告警（可用于 cron）")
    p_daily.add_argument("--date", default=None, help="锚点日期 YYYY-MM-DD，默认今天")
    p_daily.add_argument("--project", default=None, help="项目过滤")
    p_daily.add_argument("--phase", default=None, choices=sorted(ALLOWED_PHASES), help="Phase 过滤")
    p_daily.add_argument("--block-spike-ratio", type=float, default=2.0, help="BLOCK 激增阈值倍数")
    p_daily.add_argument("--phase-failure-threshold", type=float, default=0.5, help="Phase 失败率阈值")
    p_daily.set_defaults(handler=_cmd_daily)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
