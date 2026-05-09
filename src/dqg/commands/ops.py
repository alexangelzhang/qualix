"""Ops 子命令：metrics / observe / regression.

收编原 dqg-metrics / dqg-observe / dqg-regression 孤儿入口，
统一通过 dqg-run <project_id> metrics/observe/regression 调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def cmd_metrics(args: argparse.Namespace, output_dir: Path) -> int:
    """度量自动采集（原 dqg-metrics）."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.json_utils import save_json
    from dqg.reporting.collect_metrics import collect_all_metrics, print_metrics_summary

    metrics = collect_all_metrics(output_dir, args.project_id)
    metrics_file = output_dir / f"{args.project_id}_metrics.json"
    save_json(metrics_file, metrics)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="metrics",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"metrics_file": str(metrics_file), "metrics": metrics},
            )
        )
    else:
        print_metrics_summary(metrics)
        print(f"  指标已保存: {metrics_file}")
    return 0


def cmd_observe(args: argparse.Namespace, output_dir: Path) -> int:
    """可观测性报告（原 dqg-observe）.

    子命令通过 args.observe_action 区分：report / daily。
    """
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    action = getattr(args, "observe_action", "report")
    # 注入 base_dir 供 observability 内部使用
    args.base_dir = str(output_dir.parent)

    if action == "daily":
        if cli_json_mode(args):
            from dqg.reporting.observability import (
                _append_history,
                _build_alerts,
                _load_history,
                _parse_date,
                _write_alerts,
                _write_prometheus_snapshot,
                generate_report,
            )
            from dqg.reporting.observability_anomalies import anomalies_to_alert_dicts

            out_dir = Path(args.base_dir).resolve() / "output"
            payload, json_path, md_path = generate_report(
                out_dir,
                period_name="daily",
                anchor=_parse_date(args.date),
                project_filter=args.project,
                phase_filter=args.phase,
            )
            inserted = _append_history(out_dir, "daily", payload)
            history = _load_history(out_dir)
            extra = anomalies_to_alert_dicts(payload.get("metric_anomalies") or [])
            alerts = _build_alerts(
                history,
                payload["label"],
                block_spike_ratio=args.block_spike_ratio,
                phase_failure_threshold=args.phase_failure_threshold,
                failure_library=payload.get("failure_library"),
                extra_alerts=extra,
            )
            alerts_json, alerts_md = _write_alerts(out_dir, payload["label"], alerts)
            prom_path = _write_prometheus_snapshot(out_dir, payload, alerts)
            print_cli_json(
                cli_envelope(
                    command="observe",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={
                        "observe_action": "daily",
                        "report_json": str(json_path),
                        "report_md": str(md_path),
                        "history_rows_inserted": inserted,
                        "alerts_json": str(alerts_json),
                        "alerts_md": str(alerts_md),
                        "prometheus_snapshot": str(prom_path),
                        "payload": payload,
                    },
                )
            )
            return 0
        from dqg.reporting.observability import _cmd_daily

        return int(_cmd_daily(args))

    if action == "prompt-versions":
        from dqg.store.prompt_versions import query_prompt_versions

        base = Path(getattr(args, "base_dir", ".") or ".").resolve()
        out_dir = base / "output"
        ph = getattr(args, "prompt_hash", None)
        rows = query_prompt_versions(out_dir, prompt_hash=ph, limit=50)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="observe",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={"observe_action": "prompt-versions", "rows": rows},
                )
            )
            return 0
        if not rows:
            print("  (无 prompt_versions 记录；需开启采样且 Agent 带 output_dir)")
            return 0
        for r in rows:
            print(
                f"  v{r.get('version')} hash={r.get('prompt_hash', '')[:12]}… "
                f"agent={r.get('agent_name')}/{r.get('agent_role')} run={r.get('trace_run_id', '')}"
            )
        return 0

    if action == "guard-precision":
        from dqg.reporting.guard_precision_report import write_guard_precision_report

        base = Path(getattr(args, "base_dir", ".") or ".").resolve()
        out_dir = base / "output"
        dest = write_guard_precision_report(out_dir)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="observe",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={"observe_action": "guard-precision", "report_path": str(dest)},
                )
            )
        else:
            print(f"  Guard 精度周报已写入: {dest}")
        return 0

    if cli_json_mode(args):
        from dqg.reporting.observability import _parse_date, generate_report

        output_dir_path = Path(args.base_dir).resolve() / "output"
        payload, json_path, md_path = generate_report(
            output_dir_path,
            period_name=args.period,
            anchor=_parse_date(args.date),
            project_filter=args.project,
            phase_filter=args.phase,
        )
        print_cli_json(
            cli_envelope(
                command="observe",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={
                    "observe_action": "report",
                    "period": args.period,
                    "report_json": str(json_path),
                    "report_md": str(md_path),
                    "project_count": len(payload["projects"]),
                    "payload": payload,
                },
            )
        )
        return 0

    from dqg.reporting.observability import _cmd_report

    return int(_cmd_report(args))


def cmd_regression(args: argparse.Namespace, output_dir: Path) -> int:
    """回归测试（原 dqg-regression）.

    子命令通过 args.regression_action 区分：run / trend。
    """
    from datetime import date, datetime

    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.tracking.regression import (
        _failure_history_path,
        _failure_library_root,
        _repo_root,
        _write_failure_trend_output,
        _write_run_output,
        append_failure_history,
        build_failure_trend,
        compute_exit_code,
        discover_cases,
        run_case,
    )

    action = getattr(args, "regression_action", "run")

    if action == "trend":
        payload = build_failure_trend(_failure_history_path(), period=getattr(args, "period", "weekly"))
        trend_output = (
            Path(args.regression_output_dir)
            if getattr(args, "regression_output_dir", None)
            else _failure_library_root() / "trends" / getattr(args, "period", "weekly")
        )
        json_path, md_path = _write_failure_trend_output(payload, trend_output)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="regression",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={
                        "regression_action": "trend",
                        "json_path": str(json_path),
                        "md_path": str(md_path),
                        "payload": payload,
                    },
                )
            )
        else:
            print(f"趋势结果: {json_path}")
            print(f"趋势结果: {md_path}")
        return 0

    # run
    cases = discover_cases()
    case_id = getattr(args, "case_id", None)
    if case_id:
        cases = [c for c in cases if c["case_id"] == case_id]
    if not cases:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="regression",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    extra={"regression_action": "run", "error": "no_cases", "case_id": case_id},
                )
            )
        else:
            print(f"No regression case found for: {case_id}")
        return 1

    results = [run_case(Path(c["case_dir"])) for c in cases]
    run_output = (
        Path(args.regression_output_dir)
        if getattr(args, "regression_output_dir", None)
        else _repo_root() / "regression" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    json_path, md_path = _write_run_output(results, run_output)
    append_failure_history(results, _failure_history_path(), date.today().strftime("%Y-%m-%d"))
    ec = compute_exit_code(results)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="regression",
                project_id=args.project_id,
                success=ec == 0,
                exit_code=ec,
                extra={
                    "regression_action": "run",
                    "json_path": str(json_path),
                    "md_path": str(md_path),
                    "results": results,
                },
            )
        )
    else:
        print(f"回放结果: {json_path}")
        print(f"回放结果: {md_path}")
    return ec
