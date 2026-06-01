"""Observability reporting and alerting based on telemetry."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Final

from qualix.constants import PHASE_DIR_MAP, REPORT_MAP
from qualix.json_utils import dump_jsonl, save_json
from qualix.reporting.collect_metrics import collect_all_metrics
from qualix.reporting.telemetry import PhaseRunRecord, load_records
from qualix.tracking.regression import build_failure_trend

ALLOWED_PHASES: Final = frozenset({"Q01", "Q04", "Q03", "Q05a", "Q05b", "Q06", "Q07"})
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
    for path in output_dir.glob("*/*_telemetry.jsonl"):
        projects.add(path.name.removesuffix("_telemetry.jsonl"))
    for path in output_dir.glob("*_telemetry.jsonl"):  # 兼容旧结构
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
    avg_duration = (
        mean([r.duration_seconds for r in finalize_records if r.duration_seconds is not None])
        if finalize_records
        else 0.0
    )
    approval_rate = (len(approve_records) / len(finalize_records)) if finalize_records else 0.0

    # 闭环时长（execute → approve 时间差，小时）
    execute_records = [r for r in records if r.action == "execute"]
    closure_hours: list[float] = []
    for phase in ALLOWED_PHASES:
        first_exec = next((r for r in execute_records if r.phase_id == phase), None)
        last_approve = next((r for r in reversed(approve_records) if r.phase_id == phase), None)
        if first_exec and last_approve and first_exec.timestamp and last_approve.timestamp:
            try:
                t0 = datetime.fromisoformat(first_exec.timestamp)
                t1 = datetime.fromisoformat(last_approve.timestamp)
                delta = (t1 - t0).total_seconds() / 3600
                if delta >= 0:
                    closure_hours.append(delta)
            except (ValueError, TypeError):
                pass
    avg_closure_hours = round(mean(closure_hours), 2) if closure_hours else 0.0

    # 误报率（force_approved / total_approved）
    force_count = sum(1 for r in approve_records if getattr(r, "force_approved", False))
    force_approve_rate = round(force_count / len(approve_records), 4) if approve_records else 0.0

    phase_stats: dict[str, dict[str, Any]] = {}
    for phase in sorted(ALLOWED_PHASES):
        phase_finalize = [r for r in finalize_records if r.phase_id == phase]
        phase_approve = [r for r in approve_records if r.phase_id == phase]
        phase_error = _phase_from_validation_errors(records, phase)
        phase_avg_duration = (
            mean([r.duration_seconds for r in phase_finalize if r.duration_seconds is not None])
            if phase_finalize
            else 0.0
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
        "avg_closure_hours": avg_closure_hours,
        "force_approve_rate": force_approve_rate,
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


def _build_trace_summary(all_records: list[PhaseRunRecord]) -> dict[str, Any]:
    """P2: 从 llm_calls 聚合分层 trace 路径（扁平 span_path）."""
    paths: Counter[str] = Counter()
    runs: set[str] = set()
    for r in all_records:
        for c in r.llm_calls:
            p = str(c.get("span_path", "") or "").strip()
            if p:
                paths[p] += 1
            tr = str(c.get("trace_run_id", "") or "").strip()
            if tr:
                runs.add(tr)
    return {
        "unique_trace_runs": len(runs),
        "span_paths": [{"path": k, "count": v} for k, v in paths.most_common(40)],
    }


def _build_prompt_effectiveness(all_records: list[PhaseRunRecord]) -> dict[str, Any]:
    """从 telemetry 记录中聚合 Prompt 效果指标."""
    from qualix.reporting.perf_tracker import estimate_llm_call_cost_usd

    calls = [{**c, "phase_id": r.phase_id} for r in all_records for c in r.llm_calls]
    if not calls:
        return {}
    hash_counter = Counter(c.get("prompt_hash", "unknown") for c in calls)
    token_map: dict[tuple[str, str], dict[str, float | int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "calls": 0, "cost_usd": 0.0}
    )
    for c in calls:
        key = (c["phase_id"], str(c.get("model_id", "unknown")))
        inp = int(c.get("input_tokens", 0) or 0)
        outp = int(c.get("output_tokens", 0) or 0)
        cc = int(c.get("cache_creation_input_tokens", 0) or 0)
        cr = int(c.get("cache_read_input_tokens", 0) or 0)
        token_map[key]["input"] += inp
        token_map[key]["output"] += outp
        token_map[key]["calls"] += 1
        token_map[key]["cost_usd"] = float(token_map[key]["cost_usd"]) + estimate_llm_call_cost_usd(inp, outp, cc, cr)
    rows = []
    cost_total = 0.0
    for k, v in sorted(token_map.items()):
        row = {
            "phase_id": k[0],
            "model_id": k[1],
            "calls": int(v["calls"]),
            "input": int(v["input"]),
            "output": int(v["output"]),
            "cost_usd": round(float(v["cost_usd"]), 4),
        }
        cost_total += float(row["cost_usd"])
        rows.append(row)
    total, hits = len(calls), sum(1 for c in calls if c.get("cache_hit"))
    sampled_payload_calls = sum(1 for c in calls if c.get("prompt_excerpt") or c.get("response_excerpt"))
    return {
        "prompt_distribution": [{"prompt_hash": h, "count": n} for h, n in hash_counter.most_common(10)],
        "token_distribution": rows,
        "cost_total_usd": round(cost_total, 4),
        "payload_sample_calls": sampled_payload_calls,
        "cache_hit_rate": round(hits / total, 4) if total else 0.0,
        "cache_hits": hits,
        "cache_total": total,
    }


def _write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"# Qualix {payload['period']} 报告")
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
    pe = payload.get("prompt_effectiveness", {})
    if pe:
        lines += ["", "## Prompt 效果", "", "### Prompt 版本分布", "", "| Prompt Hash | Count |", "| --- | ---: |"]
        lines += [f"| `{i['prompt_hash'][:12]}` | {i['count']} |" for i in pe.get("prompt_distribution", [])]
        lines += [
            "",
            "### Token / 成本聚合（粗估 USD，定价与 perf_tracker 一致）",
            "",
            "| Phase | Model | Calls | Input Tokens | Output Tokens | Est. USD |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        lines += [
            f"| {i['phase_id']} | {i['model_id']} | {i['calls']} | {i['input']:,} | {i['output']:,} | {i.get('cost_usd', 0):.4f} |"
            for i in pe.get("token_distribution", [])
        ]
        lines += ["", f"- **窗口内 Est. USD 合计:** {pe.get('cost_total_usd', 0):.4f}"]
        lines += [
            f"- **Payload 采样命中调用数:** {pe.get('payload_sample_calls', 0)}（环境变量 `QUALIX_TELEMETRY_PAYLOAD_SAMPLE_RATE`）",
            "",
            "### Cache 命中率",
            "",
            f"- 命中: {pe.get('cache_hits', 0)} / {pe.get('cache_total', 0)} ({pe.get('cache_hit_rate', 0.0):.2%})",
        ]
    ts = payload.get("trace_summary") or {}
    if ts.get("span_paths"):
        lines += [
            "",
            "## Trace 分层摘要（P2）",
            "",
            f"- 独立 trace_run 数: {ts.get('unique_trace_runs', 0)}",
            "",
            "| span_path | calls |",
            "| --- | ---: |",
        ]
        lines += [f"| `{i['path']}` | {i['count']} |" for i in ts.get("span_paths", [])]
    an = payload.get("metric_anomalies") or []
    if an:
        lines += [
            "",
            "## 指标异常（P3 Z-score / IQR）",
            "",
            "| Project | Phase | Metric | Current | Mean | Methods |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
        for x in an:
            lines.append(
                f"| {x['project_id']} | {x['phase']} | {x['metric']} | {x['current']} | {x['hist_mean']} | "
                f"{','.join(x.get('methods', []))} |"
            )
    # 运营口径节
    gp = payload.get("guard_precision", {})
    guard_rows = [{"name": name, **counters} for name, counters in gp.get("by_guard", {}).items()]
    if guard_rows:
        lines += [
            "",
            "## 运营口径",
            "",
            "### Guard 精度",
            "",
            "| Guard | 执行 | 通过 | 阻断 | 命中率 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for g in guard_rows:
            passed = g.get("pass", 0)
            blocked = g.get("blocked", 0)
            total = passed + blocked + g.get("fail", 0)
            hit_rate = blocked / total if total > 0 else 0.0
            lines.append(f"| {g.get('name', '?')} | {total} | {passed} | {blocked} | {hit_rate:.2%} |")

    has_closure = any(r.get("avg_closure_hours", 0) > 0 for r in payload.get("projects", []))
    if has_closure:
        lines += [
            "",
            "### Phase 运营（闭环时长 / 误报率）",
            "",
            "| Project | 平均闭环时长(h) | Force Approve 率 |",
            "| --- | ---: | ---: |",
        ]
        for item in payload.get("projects", []):
            lines.append(
                f"| {item['project_id']} | {item.get('avg_closure_hours', 0):.2f} | "
                f"{item.get('force_approve_rate', 0):.2%} |"
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
    from qualix.reporting.observability_alerts import build_alerts

    return build_alerts(history, current_label, block_spike_ratio, phase_failure_threshold, failure_library)


def _write_alerts(output_dir: Path, label: str, alerts: list[dict[str, Any]]) -> tuple[Path, Path]:
    from qualix.reporting.observability_alerts import write_alerts

    return write_alerts(output_dir, label, alerts)


def _write_prometheus_snapshot(output_dir: Path, payload: dict[str, Any], alerts: list[dict[str, Any]]) -> Path:
    from qualix.reporting.observability_alerts import write_prometheus_snapshot

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
    all_records: list[PhaseRunRecord] = []
    for project_id in projects:
        records = _load_period_records(output_dir, project_id, period, phase_filter)
        if not records:
            continue
        all_records.extend(records)
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
    payload["prompt_effectiveness"] = _build_prompt_effectiveness(all_records)
    payload["trace_summary"] = _build_trace_summary(all_records)
    from qualix.reporting.observability_anomalies import detect_metric_anomalies

    payload["metric_anomalies"] = detect_metric_anomalies(_load_history(output_dir), period.label)
    try:
        from qualix.reporting.guard_precision_report import build_guard_precision_summary

        payload["guard_precision"] = build_guard_precision_summary(output_dir)
    except Exception:
        payload["guard_precision"] = {}
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
    from qualix.reporting.observability_anomalies import anomalies_to_alert_dicts

    extra = anomalies_to_alert_dicts(payload.get("metric_anomalies") or [])
    alerts = _build_alerts(
        history,
        payload["label"],
        block_spike_ratio=args.block_spike_ratio,
        phase_failure_threshold=args.phase_failure_threshold,
        failure_library=payload.get("failure_library"),
        extra_alerts=extra,
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
    parser = argparse.ArgumentParser(description="Qualix observability and alerting")
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
