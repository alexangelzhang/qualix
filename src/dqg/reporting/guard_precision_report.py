"""T9: Guard 精度周报 — 从各项目 Phase 的 _guardrail_results.json 聚合."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dqg.constants import PHASE_DIR_MAP
from dqg.json_utils import load_json

# 与 finalize / handler 命名对齐的 guard 维度（用于可观测性分桶）
KNOWN_GUARDS = (
    "finalize_checks",
    "phase_constraints",
    "rule_compliance",
    "report_semantic",
    "fabrication_detector",
    "output_completeness",
    "q05_branch_coverage",
    "weak_assert_gate",
    "mock_coincidence_check",
)


def _iter_guardrail_files(output_dir: Path) -> list[Path]:
    paths: list[Path] = []
    if not output_dir.is_dir():
        return paths
    for proj in sorted(output_dir.iterdir()):
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        for suffix in PHASE_DIR_MAP.values():
            p = proj / suffix / "_internal" / "_guardrail_results.json"
            if p.is_file():
                paths.append(p)
    return paths


def _load_results(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    return data if isinstance(data, list) else []


def build_guard_precision_summary(output_dir: Path) -> dict[str, Any]:
    """聚合 guardrail 结果：passed/failed 计数 + 三态占位."""
    by_guard: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0, "blocked": 0})
    files_read = 0
    for path in _iter_guardrail_files(output_dir):
        files_read += 1
        for row in _load_results(path):
            name = str(row.get("guardrail", "unknown"))
            passed = bool(row.get("passed", True))
            level = str(row.get("level", "")).upper()
            if passed:
                by_guard[name]["pass"] += 1
            else:
                by_guard[name]["fail"] += 1
                if level == "BLOCKED":
                    by_guard[name]["blocked"] += 1

    tri_state = {
        "拦对_启发式": "guardrail 报 FAIL/BLOCKED 且 finalize 未放行（需结合 telemetry 复核）",
        "拦错_待标注": "人工将误报样本标注到 failure-library case_category=DOC_SKILL_DRIFT",
        "漏拦_待标注": "finalize 通过但事后发现缺陷的样本写入 regression case",
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir.resolve()),
        "guardrail_files_read": files_read,
        "by_guard": dict(sorted(by_guard.items())),
        "tri_state_legend": tri_state,
        "known_guard_axis": KNOWN_GUARDS,
    }


def render_guard_precision_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Guard 精度周报（T9）",
        "",
        f"- 生成时间: `{summary['generated_at']}`",
        f"- 扫描目录: `{summary['output_dir']}`",
        f"- 读到的 `_guardrail_results.json` 文件数: **{summary['guardrail_files_read']}**",
        "",
        "## 按 guardrail 聚合（原始计数）",
        "",
        "| guardrail | pass | fail | blocked |",
        "|-----------|------|------|---------|",
    ]
    for name, c in summary.get("by_guard", {}).items():
        lines.append(f"| {name} | {c['pass']} | {c['fail']} | {c['blocked']} |")
    if not summary.get("by_guard"):
        lines.append("| （无数据） | — | — | — |")

    lines.extend(
        [
            "",
            "## 三态说明（人工闭环）",
            "",
        ]
    )
    for k, v in summary.get("tri_state_legend", {}).items():
        lines.append(f"- **{k}**: {v}")

    lines.extend(
        [
            "",
            "## 建议监控的 guard 轴",
            "",
            ", ".join(f"`{g}`" for g in summary.get("known_guard_axis", ())),
            "",
        ]
    )
    return "\n".join(lines)


def write_guard_precision_report(output_dir: Path, dest: Path | None = None) -> Path:
    """写入 Markdown 周报；默认路径 docs/observability/reports/weekly/guard_precision.md。"""
    summary = build_guard_precision_summary(output_dir)
    if dest is None:
        repo = Path(__file__).resolve().parents[3]
        dest = repo / "docs" / "observability" / "reports" / "weekly" / "guard_precision.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_guard_precision_markdown(summary), encoding="utf-8")
    return dest


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output")
    print(write_guard_precision_report(out))
