#!/usr/bin/env python3
"""
度量自动采集：从 output 目录的报告文件中提取覆盖率、闭环率、问题密度等指标。

用法:
    python3 scripts/collect_metrics.py <project_id>
    python3 scripts/collect_metrics.py <project_id> --compare <other_project_id>

输出:
    output/<project_id>_metrics.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dqg.constants import PHASE_DIR_MAP, REPORT_MAP


def count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def extract_table_column_counts(text: str, header_pattern: str, col_index: int) -> dict:
    """从 markdown 表格中按列提取值的计数分布。"""
    counts = {}
    in_table = False
    header_found = False

    for line in text.split("\n"):
        if header_pattern in line:
            header_found = True
            in_table = True
            continue
        if (header_found and line.strip().startswith("|--")) or line.strip().startswith("| --"):
            continue
        if in_table and line.strip().startswith("|"):
            cols = [c.strip() for c in line.split("|")]
            cols = [c for c in cols if c]  # remove empty from leading/trailing |
            if len(cols) > col_index:
                val = cols[col_index].strip().strip("*")
                counts[val] = counts.get(val, 0) + 1
        elif in_table and not line.strip().startswith("|"):
            in_table = False

    return counts


def extract_phase_a_metrics(report_path: Path) -> dict:
    """从 Phase A 报告提取指标。"""
    if not report_path.exists():
        return {"status": "NOT_FOUND"}

    text = report_path.read_text(encoding="utf-8")

    req_count = count_pattern(text, r"\|\s*REQ-\d+")
    br_count = count_pattern(text, r"\|\s*BR-\d+")
    se_count = count_pattern(text, r"\|\s*SE-\d+")
    gap_count = count_pattern(text, r"\|\s*GAP-\d+")
    open_count = count_pattern(text, r"\|\s*OPEN-\d+")

    # 提取结论
    conclusion = "未知"
    m = re.search(r"评审结论[：:]\s*\*{0,2}(.+?)\*{0,2}\s*$", text, re.MULTILINE)
    if m:
        conclusion = m.group(1).strip()

    return {
        "status": "COLLECTED",
        "req_count": req_count,
        "br_count": br_count,
        "se_count": se_count,
        "gap_count": gap_count,
        "open_count": open_count,
        "structuring_rate": 1.0 if req_count > 0 else 0.0,
        "conclusion": conclusion,
    }


def extract_phase_a5_metrics(report_path: Path) -> dict:
    """从 Phase A.5 覆盖度审计报告提取指标。"""
    if not report_path.exists():
        return {"status": "NOT_FOUND"}

    text = report_path.read_text(encoding="utf-8")

    # 从覆盖度统计表提取
    metrics = {
        "status": "COLLECTED",
        "req_coverage": {},
        "br_coverage": {},
        "se_coverage": {},
        "gap_closure": {},
        "open_closure": {},
    }

    # 提取 COVERED/PARTIAL/MISSING/IMPLICIT 计数
    for dimension, key in [("REQ", "req_coverage"), ("BR", "br_coverage"), ("SE", "se_coverage")]:
        covered = count_pattern(text, rf"(?i)\b{dimension}\b.*?COVERED")
        partial = count_pattern(text, rf"(?i)\b{dimension}\b.*?PARTIAL")
        missing = count_pattern(text, rf"(?i)\b{dimension}\b.*?MISSING")
        implicit = count_pattern(text, rf"(?i)\b{dimension}\b.*?IMPLICIT")
        total = covered + partial + missing + implicit
        metrics[key] = {
            "covered": covered,
            "partial": partial,
            "missing": missing,
            "implicit": implicit,
            "total": total,
            "coverage_rate": round((covered + implicit) / total, 2) if total > 0 else 0,
        }

    # GAP 闭环统计
    closed = count_pattern(text, r"已闭环")
    partial_closed = count_pattern(text, r"部分闭环")
    unclosed = count_pattern(text, r"未闭环")
    gap_total = closed + partial_closed + unclosed
    metrics["gap_closure"] = {
        "closed": closed,
        "partial": partial_closed,
        "unclosed": unclosed,
        "total": gap_total,
        "closure_rate": round(closed / gap_total, 2) if gap_total > 0 else 0,
    }

    return metrics


def extract_phase_a6_metrics(report_path: Path) -> dict:
    """从 Phase A.6 质量评审报告提取指标。"""
    if not report_path.exists():
        return {"status": "NOT_FOUND"}

    text = report_path.read_text(encoding="utf-8")

    # 统计各维度问题数
    arch_issues = count_pattern(text, r"ARCH-\d+")
    api_issues = count_pattern(text, r"API-\d+")
    data_issues = count_pattern(text, r"DATA-\d+")
    exc_issues = count_pattern(text, r"EXC-\d+")
    perf_issues = count_pattern(text, r"PERF-\d+")

    # Failure Mode 统计
    safe = count_pattern(text, r"\bSAFE\b")
    risk = count_pattern(text, r"\bRISK\b")
    critical_gap = count_pattern(text, r"CRITICAL_GAP")

    return {
        "status": "COLLECTED",
        "issue_density": {
            "architecture": arch_issues,
            "api_design": api_issues,
            "data_model": data_issues,
            "exception_handling": exc_issues,
            "performance": perf_issues,
            "total": arch_issues + api_issues + data_issues + exc_issues + perf_issues,
        },
        "failure_mode": {
            "safe": safe,
            "risk": risk,
            "critical_gap": critical_gap,
        },
    }


def extract_phase_c_metrics(report_path: Path) -> dict:
    """从 Phase C 单测审计报告提取指标。"""
    if not report_path.exists():
        return {"status": "NOT_FOUND"}

    text = report_path.read_text(encoding="utf-8")

    covered = count_pattern(text, r"\bCOVERED\b")
    partial = count_pattern(text, r"\bPARTIAL\b")
    missing = count_pattern(text, r"\bMISSING\b")
    wrong_target = count_pattern(text, r"\bWRONG_TARGET\b")

    # 覆盖率门禁
    line_cov = None
    branch_cov = None
    m = re.search(r"line\s*=\s*(\d+(?:\.\d+)?)\s*%", text)
    if m:
        line_cov = float(m.group(1))
    m = re.search(r"branch\s*=\s*(\d+(?:\.\d+)?)\s*%", text)
    if m:
        branch_cov = float(m.group(1))

    # 结论
    conclusion = "未知"
    m = re.search(r"结论[：:]\s*`?(\w+)`?", text)
    if m:
        conclusion = m.group(1)

    return {
        "status": "COLLECTED",
        "coverage_quality": {
            "covered": covered,
            "partial": partial,
            "missing": missing,
            "wrong_target": wrong_target,
        },
        "coverage_gate": {
            "line_coverage": line_cov,
            "branch_coverage": branch_cov,
        },
        "conclusion": conclusion,
    }


def collect_all_metrics(output_dir: Path, project_id: str) -> dict:
    """采集所有阶段的指标。"""
    phase_a_dir = output_dir / project_id / PHASE_DIR_MAP["Q01"]

    metrics = {
        "project_id": project_id,
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phases": {
            "Q01": extract_phase_a_metrics(phase_a_dir / REPORT_MAP["Q01"]),
            "Q04": extract_phase_a5_metrics(
                phase_a_dir / REPORT_MAP["Q04"]
                if (phase_a_dir / REPORT_MAP["Q04"]).exists()
                else output_dir / project_id / PHASE_DIR_MAP["Q04"] / REPORT_MAP["Q04"]
            ),
            "Q03": extract_phase_a6_metrics(
                phase_a_dir / REPORT_MAP["Q03"]
                if (phase_a_dir / REPORT_MAP["Q03"]).exists()
                else output_dir / project_id / PHASE_DIR_MAP["Q03"] / REPORT_MAP["Q03"]
            ),
            "Q06": extract_phase_c_metrics(
                output_dir / project_id / PHASE_DIR_MAP["Q06"] / REPORT_MAP["Q06"]
            ),
        },
    }

    # 计算汇总指标
    summary = {}
    a = metrics["phases"]["Q01"]
    if a.get("status") == "COLLECTED":
        summary["total_requirements"] = a["req_count"] + a["br_count"]
        summary["total_semantics"] = a["se_count"]
        summary["total_gaps"] = a["gap_count"]
        summary["total_opens"] = a["open_count"]

    a5 = metrics["phases"]["Q04"]
    if a5.get("status") == "COLLECTED":
        gap_closure = a5.get("gap_closure", {})
        summary["gap_closure_rate"] = gap_closure.get("closure_rate", 0)

    a6 = metrics["phases"]["Q03"]
    if a6.get("status") == "COLLECTED":
        summary["total_quality_issues"] = a6.get("issue_density", {}).get("total", 0)
        summary["critical_gaps"] = a6.get("failure_mode", {}).get("critical_gap", 0)

    metrics["summary"] = summary
    return metrics


def print_metrics_summary(metrics: dict):
    """打印指标摘要。"""
    print()
    print("=" * 56)
    print(f"  度量采集报告 — {metrics['project_id']}")
    print(f"  采集时间: {metrics['collected_at']}")
    print("=" * 56)

    a = metrics["phases"]["Q01"]
    if a.get("status") == "COLLECTED":
        print("\n  Phase Q01 — 需求结构化")
        print(f"    需求点: {a['req_count']} REQ + {a['br_count']} BR")
        print(f"    关键语义: {a['se_count']} SE")
        print(f"    缺口: {a['gap_count']} GAP / 待确认: {a['open_count']} OPEN")
        print(f"    结论: {a['conclusion']}")

    a5 = metrics["phases"]["Q04"]
    if a5.get("status") == "COLLECTED":
        print("\n  Phase Q04 — 覆盖度审计")
        gc = a5.get("gap_closure", {})
        print(f"    GAP 闭环: {gc.get('closed', 0)}/{gc.get('total', 0)} ({gc.get('closure_rate', 0):.0%})")

    a6 = metrics["phases"]["Q03"]
    if a6.get("status") == "COLLECTED":
        density = a6.get("issue_density", {})
        fm = a6.get("failure_mode", {})
        print("\n  Phase Q03 — 质量评审")
        print(f"    问题总数: {density.get('total', 0)} (ARCH:{density.get('architecture', 0)} API:{density.get('api_design', 0)} DATA:{density.get('data_model', 0)} EXC:{density.get('exception_handling', 0)} PERF:{density.get('performance', 0)})")
        print(f"    Failure Mode: SAFE:{fm.get('safe', 0)} RISK:{fm.get('risk', 0)} CRITICAL_GAP:{fm.get('critical_gap', 0)}")

    c = metrics["phases"]["Q06"]
    if c.get("status") == "COLLECTED":
        cq = c.get("coverage_quality", {})
        cg = c.get("coverage_gate", {})
        print("\n  Phase Q06 — 单测审计")
        print(f"    覆盖质地: COVERED:{cq.get('covered', 0)} PARTIAL:{cq.get('partial', 0)} MISSING:{cq.get('missing', 0)} WRONG_TARGET:{cq.get('wrong_target', 0)}")
        if cg.get("line_coverage") is not None:
            print(f"    覆盖率门禁: line={cg['line_coverage']}% branch={cg.get('branch_coverage', '?')}%")
        print(f"    结论: {c['conclusion']}")

    not_found = [k for k, v in metrics["phases"].items() if v.get("status") == "NOT_FOUND"]
    if not_found:
        print(f"\n  未采集: {', '.join(not_found)}")

    print()
    print("=" * 56)


def main():
    parser = argparse.ArgumentParser(description="度量自动采集")
    parser.add_argument("project_id", help="项目 ID（如 KMgHd）")
    parser.add_argument("--base-dir", default=".", help="项目根目录")

    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    output_dir = base_dir / "output"

    if not output_dir.exists():
        print(f"错误: output 目录不存在: {output_dir}", file=sys.stderr)
        sys.exit(1)

    metrics = collect_all_metrics(output_dir, args.project_id)

    # 保存 JSON
    metrics_file = output_dir / f"{args.project_id}_metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print_metrics_summary(metrics)
    print(f"  指标已保存: {metrics_file}")


if __name__ == "__main__":
    main()
