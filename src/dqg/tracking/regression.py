"""Regression replay for curated DQG sample cases."""

from __future__ import annotations

import argparse
import difflib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from dqg.json_utils import dump_json_str, dump_jsonl, load_json_strict, save_json

VOLATILE_JSON_KEYS: Final[frozenset[str]] = frozenset(
    {
        "created_at",
        "updated_at",
        "generated_at",
        "started_at",
        "finished_at",
        "approved_at",
        "duration_seconds",
        "collected_at",
        "timestamp",
    }
)
FAILURE_LIBRARY = "failure-library"
DATE_FMT = "%Y-%m-%d"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cases_root() -> Path:
    """读取 regression/cases：走 ResourceResolver 四层回退（~/.dqg/ → 包内 → repo root）."""
    from dqg.core.resource_resolver import ResourceResolver

    try:
        return ResourceResolver().resolve_dir("regression") / "cases"
    except FileNotFoundError:
        return _repo_root() / "regression" / "cases"


def _failure_library_root() -> Path:
    """failure-library 写入 ~/.dqg/regression/failure-library/（用户可写）."""
    root = Path.home() / ".dqg" / "regression" / FAILURE_LIBRARY
    root.mkdir(parents=True, exist_ok=True)
    return root


def _failure_history_path() -> Path:
    return _failure_library_root() / "history.jsonl"


def discover_cases(cases_root: Path | None = None) -> list[dict[str, Any]]:
    root = cases_root or _cases_root()
    cases = []
    for path in sorted(root.rglob("case.json")):
        case_dir = path.parent
        data = load_json_strict(path)
        data["case_dir"] = str(case_dir)
        cases.append(data)
    return cases


def classify_diff(*, expected_exists: bool, actual_exists: bool, changed: bool) -> str:
    if not expected_exists and actual_exists:
        return "新增"
    if expected_exists and not actual_exists:
        return "回归"
    if changed:
        return "偏移"
    return "一致"


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if key in VOLATILE_JSON_KEYS:
                normalized[key] = "<normalized>"
            else:
                normalized[key] = _normalize_json_value(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def _normalize_text(file_path: str, text: str) -> str:
    if file_path.endswith(".json"):
        data = json.loads(text)
        return dump_json_str(_normalize_json_value(data), indent=2, sort_keys=True)
    return text


def _relative_files(actual_dir: Path, expected_dir: Path, include: list[str] | None) -> list[str]:
    if include:
        return sorted(include)

    files = set()
    for root in (actual_dir, expected_dir):
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    files.add(str(path.relative_to(root)))
    return sorted(files)


def run_case(case_dir: Path) -> dict[str, Any]:
    meta = load_json_strict(case_dir / "case.json")
    actual_dir = Path(meta["actual_dir"])
    if not actual_dir.is_absolute():
        actual_dir = _repo_root() / actual_dir
    expected_dir = case_dir / "expected"
    include = meta.get("include")

    diffs = []
    for rel in _relative_files(actual_dir, expected_dir, include):
        expected_path = expected_dir / rel
        actual_path = actual_dir / rel
        expected_exists = expected_path.exists()
        actual_exists = actual_path.exists()

        expected_text = expected_path.read_text(encoding="utf-8") if expected_exists else ""
        actual_text = actual_path.read_text(encoding="utf-8") if actual_exists else ""
        normalized_expected = _normalize_text(rel, expected_text) if expected_exists else ""
        normalized_actual = _normalize_text(rel, actual_text) if actual_exists else ""
        changed = normalized_expected != normalized_actual
        status = classify_diff(expected_exists=expected_exists, actual_exists=actual_exists, changed=changed)

        diff_lines: list[str] = []
        if status == "偏移":
            diff_lines = list(
                difflib.unified_diff(
                    normalized_expected.splitlines(),
                    normalized_actual.splitlines(),
                    fromfile=f"expected/{rel}",
                    tofile=f"actual/{rel}",
                    lineterm="",
                )
            )
        diffs.append(
            {
                "file": rel,
                "status": status,
                "diff": "\n".join(diff_lines),
            }
        )

    summary = {
        "case_id": meta["case_id"],
        "sample_type": meta.get("sample_type", ""),
        "library": meta.get("library", "curated"),
        "error_type": meta.get("error_type", ""),
        "case_kind": meta.get("case_kind", ""),
        "trigger_condition": meta.get("trigger_condition", ""),
        "fix_strategy": meta.get("fix_strategy", ""),
        "regression_case": meta.get("regression_case", ""),
        "diffs": diffs,
        "stats": {
            "一致": sum(1 for item in diffs if item["status"] == "一致"),
            "新增": sum(1 for item in diffs if item["status"] == "新增"),
            "回归": sum(1 for item in diffs if item["status"] == "回归"),
            "偏移": sum(1 for item in diffs if item["status"] == "偏移"),
        },
    }
    summary["passed"] = (
        summary["stats"]["新增"] == 0 and summary["stats"]["回归"] == 0 and summary["stats"]["偏移"] == 0
    )
    return summary


def summarize_failure_library(results: list[dict[str, Any]]) -> dict[str, Any]:
    library_results = [item for item in results if item.get("library") == FAILURE_LIBRARY]
    by_error_type: dict[str, dict[str, Any]] = {}
    for item in library_results:
        error_type = item.get("error_type") or "未分类"
        bucket = by_error_type.setdefault(error_type, {"total": 0, "failed": 0, "pass_rate": 0.0})
        bucket["total"] += 1
        if not item.get("passed", False):
            bucket["failed"] += 1
    for bucket in by_error_type.values():
        bucket["pass_rate"] = (
            round((bucket["total"] - bucket["failed"]) / bucket["total"], 4) if bucket["total"] else 0.0
        )
    return {
        "totals": {
            "cases": len(library_results),
            "failed": sum(1 for item in library_results if not item.get("passed", False)),
        },
        "by_error_type": by_error_type,
    }


def compute_exit_code(results: list[dict[str, Any]]) -> int:
    return 1 if any(not item.get("passed", False) for item in results) else 0


def append_failure_history(results: list[dict[str, Any]], history_path: Path, label: str) -> int:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in results:
        if item.get("library") != FAILURE_LIBRARY:
            continue
        rows.append(
            {
                "date": label,
                "case_id": item["case_id"],
                "error_type": item.get("error_type", "未分类"),
                "case_kind": item.get("case_kind", ""),
                "passed": bool(item.get("passed", False)),
            }
        )
    with open(history_path, "a", encoding="utf-8") as file:
        for row in rows:
            file.write(dump_jsonl(row))
    return len(rows)


def _load_failure_history(history_path: Path) -> list[dict[str, Any]]:
    if not history_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _week_label(value: str) -> str:
    anchor = datetime.strptime(value, DATE_FMT).date()
    week_start = anchor - timedelta(days=anchor.weekday())
    week_end = week_start + timedelta(days=6)
    return f"{week_start.strftime(DATE_FMT)}_to_{week_end.strftime(DATE_FMT)}"


def build_failure_trend(history_path: Path, period: str = "weekly") -> dict[str, Any]:
    if period != "weekly":
        raise ValueError(f"Unsupported failure trend period: {period}")
    rows = _load_failure_history(history_path)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = _week_label(row["date"])
        grouped.setdefault(label, []).append(row)

    weeks = []
    for label in sorted(grouped):
        week_rows = grouped[label]
        by_error_type: dict[str, dict[str, Any]] = {}
        for row in week_rows:
            error_type = row.get("error_type", "未分类")
            bucket = by_error_type.setdefault(error_type, {"total": 0, "failed": 0, "pass_rate": 0.0})
            bucket["total"] += 1
            if not row.get("passed", False):
                bucket["failed"] += 1
        for bucket in by_error_type.values():
            bucket["pass_rate"] = (
                round((bucket["total"] - bucket["failed"]) / bucket["total"], 4) if bucket["total"] else 0.0
            )
        weeks.append(
            {
                "label": label,
                "total_cases": len(week_rows),
                "failed_cases": sum(1 for row in week_rows if not row.get("passed", False)),
                "by_error_type": by_error_type,
            }
        )
    return {"period": period, "weeks": weeks}


def _write_failure_trend_output(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "summary.json"
    md_path = output_dir / "summary.md"
    save_json(json_path, payload)

    lines = [f"# Failure Library {payload['period'].title()} Trend", ""]
    lines.append("| Week | Total | Failed |")
    lines.append("| --- | ---: | ---: |")
    for item in payload["weeks"]:
        lines.append(f"| {item['label']} | {item['total_cases']} | {item['failed_cases']} |")
    lines.append("")
    for item in payload["weeks"]:
        lines.append(f"## {item['label']}")
        lines.append("")
        lines.append("| Error Type | Total | Failed | Pass Rate |")
        lines.append("| --- | ---: | ---: | ---: |")
        for error_type, stats in item["by_error_type"].items():
            lines.append(f"| {error_type} | {stats['total']} | {stats['failed']} | {stats['pass_rate']:.2%} |")
        lines.append("")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def _write_run_output(results: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "summary.json"
    md_path = output_dir / "summary.md"
    failure_summary = summarize_failure_library(results)
    save_json(json_path, {"cases": results, "failure_library": failure_summary})

    lines = ["# DQG Regression Summary", ""]
    lines.append("| Case | Type | 一致 | 新增 | 回归 | 偏移 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for result in results:
        stats = result["stats"]
        lines.append(
            f"| {result['case_id']} | {result.get('sample_type', '')} | {stats['一致']} | {stats['新增']} | {stats['回归']} | {stats['偏移']} |"
        )
    lines.append("")
    if failure_summary["totals"]["cases"]:
        lines.append("## Failure Library Summary")
        lines.append("")
        lines.append("| Error Type | Total | Failed | Pass Rate |")
        lines.append("| --- | ---: | ---: | ---: |")
        for error_type, stats in failure_summary["by_error_type"].items():
            lines.append(f"| {error_type} | {stats['total']} | {stats['failed']} | {stats['pass_rate']:.2%} |")
        lines.append("")
    for result in results:
        lines.append(f"## {result['case_id']}")
        lines.append("")
        if result.get("library") == FAILURE_LIBRARY:
            lines.append(f"- Error Type: `{result.get('error_type')}`")
            lines.append(f"- Case Kind: `{result.get('case_kind')}`")
            lines.append(f"- Trigger Condition: {result.get('trigger_condition')}")
            lines.append(f"- Fix Strategy: {result.get('fix_strategy')}")
            lines.append(f"- Regression Case: `{result.get('regression_case')}`")
        for item in result["diffs"]:
            if item["status"] == "一致":
                continue
            lines.append(f"- `{item['file']}`: {item['status']}")
            if item["diff"]:
                lines.append("")
                lines.append("```diff")
                lines.append(item["diff"])
                lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="DQG regression replay")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run curated regression cases")
    p_run.add_argument("--case", dest="case_id", default=None, help="只运行指定 case")
    p_run.add_argument(
        "--output-dir",
        default=None,
        help="输出目录，默认 regression/runs/<timestamp>",
    )
    p_trend = sub.add_parser("trend", help="Build failure-library trend report")
    p_trend.add_argument("--period", choices=["weekly"], default="weekly")
    p_trend.add_argument("--output-dir", default=None, help="输出目录，默认 regression/failure-library/trends/<period>")

    p_prompt = sub.add_parser("prompt-eval", help="Run offline prompt A/B eval for Q05/Q06")
    p_prompt.add_argument("--case", dest="case_id", default=None, help="指定 case_id")
    p_prompt.add_argument("--phase", choices=["Q05", "Q06"], default=None, help="筛选 phase")

    p_impact = sub.add_parser("rule-impact", help="Profile rule change → metric impact report")
    p_impact.add_argument("--profile", required=True, help="Profile ID (e.g. java-ddd-tmf)")
    p_impact.add_argument("--output-dir", default=None, help="输出目录，默认 regression/rule-impact/<profile>")

    args = parser.parse_args()
    if args.command == "trend":
        payload = build_failure_trend(_failure_history_path(), period=args.period)
        output_dir = Path(args.output_dir) if args.output_dir else _failure_library_root() / "trends" / args.period
        json_path, md_path = _write_failure_trend_output(payload, output_dir)
        print(f"趋势结果: {json_path}")
        print(f"趋势结果: {md_path}")
        return 0

    if args.command == "prompt-eval":
        from dqg.tracking.prompt_eval import run_prompt_comparison

        return run_prompt_comparison(args.case_id, args.phase, _cases_root())

    if args.command == "rule-impact":
        from dqg.tracking.rule_impact import run_rule_impact

        return run_rule_impact(args.profile, args.output_dir)

    cases = discover_cases()
    if args.case_id:
        cases = [case for case in cases if case["case_id"] == args.case_id]
    if not cases:
        raise SystemExit(f"No regression case found for: {args.case_id}")
    results = [run_case(Path(case["case_dir"])) for case in cases]

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else _repo_root() / "regression" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    json_path, md_path = _write_run_output(results, output_dir)
    append_failure_history(results, _failure_history_path(), date.today().strftime(DATE_FMT))
    print(f"回放结果: {json_path}")
    print(f"回放结果: {md_path}")
    return compute_exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
