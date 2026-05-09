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
    from dqg.json_utils import save_json
    from dqg.reporting.collect_metrics import collect_all_metrics, print_metrics_summary

    metrics = collect_all_metrics(output_dir, args.project_id)
    metrics_file = output_dir / f"{args.project_id}_metrics.json"
    save_json(metrics_file, metrics)
    print_metrics_summary(metrics)
    print(f"  指标已保存: {metrics_file}")
    return 0


def cmd_observe(args: argparse.Namespace, output_dir: Path) -> int:
    """可观测性报告（原 dqg-observe）.

    子命令通过 args.observe_action 区分：report / daily。
    """
    from dqg.reporting.observability import _cmd_daily, _cmd_report

    action = getattr(args, "observe_action", "report")
    # 注入 base_dir 供 observability 内部使用
    args.base_dir = str(output_dir.parent)

    if action == "daily":
        return int(_cmd_daily(args))
    if action == "guard-precision":
        from pathlib import Path

        from dqg.reporting.guard_precision_report import write_guard_precision_report

        base = Path(getattr(args, "base_dir", ".") or ".").resolve()
        out_dir = base / "output"
        dest = write_guard_precision_report(out_dir)
        print(f"  Guard 精度周报已写入: {dest}")
        return 0
    return int(_cmd_report(args))


def cmd_regression(args: argparse.Namespace, output_dir: Path) -> int:
    """回归测试（原 dqg-regression）.

    子命令通过 args.regression_action 区分：run / trend。
    """
    from datetime import date, datetime

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
        print(f"趋势结果: {json_path}")
        print(f"趋势结果: {md_path}")
        return 0

    # run
    cases = discover_cases()
    case_id = getattr(args, "case_id", None)
    if case_id:
        cases = [c for c in cases if c["case_id"] == case_id]
    if not cases:
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
    print(f"回放结果: {json_path}")
    print(f"回放结果: {md_path}")
    return compute_exit_code(results)
