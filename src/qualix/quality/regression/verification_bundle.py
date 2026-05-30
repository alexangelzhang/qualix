"""Verification Bundle：统一验证包.

把分散的 compile_check、coverage_gate、weak_assert、blast_radius、
business_mutations、auto_checks 的结果收成一个 _verification_bundle.json。

Judge 评审时先看 verification bundle（确定性证据），再做语义判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from qualix.json_utils import load_json, save_json
from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


def _check_reasoning_log(int_dir: Path, phase_dir: Path) -> dict[str, str]:
    reasoning_log = int_dir / "_reasoning_log.md"
    if not reasoning_log.exists():
        reasoning_log = phase_dir / "_reasoning_log.md"
    if reasoning_log.exists():
        content = reasoning_log.read_text(encoding="utf-8", errors="ignore")
        import re as _re

        step_count = len(_re.findall(r"#{2,3}\s+Step", content))
        return {
            "name": "reasoning_log",
            "status": "PASS" if step_count >= 2 else "WARNING",
            "detail": f"{step_count} Steps 记录",
            "source": str(reasoning_log),
        }
    return {"name": "reasoning_log", "status": "FAIL", "detail": "不存在", "source": ""}


def _check_weak_assert(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_weak_assert_context.md"
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8", errors="ignore")
    signal_count = content.count("ASSERT_NOT_NULL_ONLY") + content.count("CONSTANT_BOOLEAN_ASSERT")
    return {
        "name": "weak_assert",
        "status": "WARNING" if signal_count > 0 else "PASS",
        "detail": f"{signal_count} 个弱断言信号",
        "source": str(path),
    }


def _check_file_exists(int_dir: Path, filename: str, name: str, detail: str) -> dict[str, str] | None:
    path = int_dir / filename
    if not path.exists():
        return None
    return {"name": name, "status": "PASS", "detail": detail, "source": str(path)}


def _check_data_patterns(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_data_patterns.json"
    if not path.exists():
        return None
    data = load_json(path)
    pattern_count = len(data.get("top_patterns", [])) if data else 0
    return {
        "name": "data_patterns",
        "status": "PASS" if pattern_count > 0 else "SKIP",
        "detail": f"{pattern_count} 种故障数据模式",
        "source": str(path),
    }


def _check_se_code_mapping(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_se_code_mapping.json"
    if not path.exists():
        return None
    data = load_json(path)
    found = data.get("found", 0) if data else 0
    total = data.get("total_se", 0) if data else 0
    return {
        "name": "se_code_mapping",
        "status": "PASS" if found > 0 else "SKIP",
        "detail": f"{found}/{total} SE 找到代码匹配",
        "source": str(path),
    }


def _check_incremental_coverage(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_incremental_coverage.json"
    if not path.exists():
        return None
    data = load_json(path)
    if not data:
        return None
    inc = data.get("incremental", {})
    inc_line = inc.get("line", {}).get("rate", 0)
    inc_branch = inc.get("branch", {}).get("rate", 0)
    matched_count = len(data.get("matched_files", []))
    status = "PASS"
    if matched_count > 0 and (inc_line < 0.80 or inc_branch < 0.80):
        status = "WARNING"
    return {
        "name": "incremental_coverage",
        "status": status,
        "detail": f"blast radius 内 {matched_count} 文件: line={inc_line:.1%} branch={inc_branch:.1%}",
        "source": str(path),
    }


def _check_requirement_graph(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_requirement_graph.json"
    if not path.exists():
        return None
    data = load_json(path)
    if not data:
        return None
    anomaly_count = data.get("anomaly_count", 0)
    coverage = data.get("coverage_summary", {})
    br_cov = coverage.get("br_se_coverage", 0)
    status = "PASS" if anomaly_count == 0 else "WARNING"
    high_anomalies = [a for a in data.get("anomalies", []) if a.get("severity") == "HIGH"]
    if high_anomalies:
        status = "WARNING"
    return {
        "name": "requirement_graph",
        "status": status,
        "detail": f"{anomaly_count} 异常 (BR→SE 覆盖率={br_cov:.0%})",
        "source": str(path),
    }


def _check_requirement_smells(int_dir: Path) -> dict[str, str] | None:
    path = int_dir / "_requirement_smells.json"
    if not path.exists():
        return None
    data = load_json(path)
    if not data:
        return None
    smell_count = data.get("smell_count", 0)
    quality = data.get("quality_score", 1.0)
    status = "PASS" if smell_count == 0 else ("WARNING" if quality >= 0.7 else "FAIL")
    return {
        "name": "requirement_smells",
        "status": status,
        "detail": f"{smell_count} 异味 (质量分={quality:.2f})",
        "source": str(path),
    }


def _check_auto_checks(int_dir: Path) -> list[dict[str, str]]:
    path = int_dir / "_auto_checks.json"
    if not path.exists():
        return []
    data = load_json(path)
    if not data or not isinstance(data, list):
        return []
    return [
        {
            "name": f"auto_check:{ac.get('check_id', '?')}",
            "status": "FAIL" if ac.get("severity") == "BLOCKED" else "WARNING",
            "detail": ac.get("message", ""),
            "source": str(path),
        }
        for ac in data
    ]


def collect_verification_bundle(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """收集所有验证结果到统一 bundle."""
    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    phase_dir = output_dir / project_id / dir_suffix
    int_dir = phase_dir / "_internal"

    checks: list[dict[str, str]] = []

    checks.append(_check_reasoning_log(int_dir, phase_dir))

    for result in (
        _check_weak_assert(int_dir),
        _check_file_exists(int_dir, "_blast_radius.md", "blast_radius", "影响范围已分析"),
        _check_file_exists(int_dir, "_business_mutations.md", "business_mutations", "变异规则已生成"),
        _check_file_exists(int_dir, "_coverage_matrix.json", "coverage_matrix", "覆盖度矩阵已生成"),
        _check_data_patterns(int_dir),
        _check_se_code_mapping(int_dir),
        _check_incremental_coverage(int_dir),
        _check_requirement_graph(int_dir),
        _check_requirement_smells(int_dir),
    ):
        if result:
            checks.append(result)

    checks.extend(_check_auto_checks(int_dir))

    pass_count = sum(1 for c in checks if c["status"] == "PASS")
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    skip_count = sum(1 for c in checks if c["status"] == "SKIP")
    warn_count = sum(1 for c in checks if c["status"] == "WARNING")

    return {
        "phase_id": phase_id,
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "pass": pass_count,
            "fail": fail_count,
            "warning": warn_count,
            "skip": skip_count,
        },
    }


def write_verification_bundle(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """收集验证结果并写入文件."""
    bundle = collect_verification_bundle(output_dir, project_id, phase_id)
    if not bundle["checks"]:
        return None

    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    bundle_path = int_dir / "_verification_bundle.json"
    save_json(bundle_path, bundle)

    s = bundle["summary"]
    log.info(
        "Verification bundle: Phase %s — %d checks (%d pass, %d fail, %d warn)",
        phase_id,
        s["total"],
        s["pass"],
        s["fail"],
        s["warning"],
    )
    return bundle_path


def render_bundle_for_judge(bundle: dict[str, Any]) -> str:
    """渲染 verification bundle 为 Judge 可消费的 prompt 片段."""
    lines = [
        "## VERIFICATION_BUNDLE — 确定性验证结果（Judge 必须优先参考）",
        "",
        "以下是自动化工具的验证结果，Judge 应先看这些确定性证据，再做语义判断。",
        "",
    ]

    for check in bundle.get("checks", []):
        icon = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️", "SKIP": "⏭"}.get(check["status"], "?")
        lines.append(f"- {icon} **{check['name']}**: {check['detail']}")

    s = bundle.get("summary", {})
    lines.append("")
    lines.append(
        f"> 汇总: {s.get('total', 0)} checks — {s.get('pass', 0)} pass, {s.get('fail', 0)} fail, {s.get('warning', 0)} warning"
    )

    return "\n".join(lines)
