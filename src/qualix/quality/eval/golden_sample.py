"""Golden Sample 标杆对比机制.

每个 Phase 有一个标杆报告的结构指纹（golden sample），
finalize 时自动对比当前产物与标杆的结构和数量，输出差异报告。

golden sample 目录: regression/golden/<phase_dir>/golden_profile.json
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qualix.constants import GOLDEN_DIR as _GOLDEN_DIR
from qualix.constants import REPORT_MAP, STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json


def _golden_dir(base_dir: Path, phase_id: str) -> Path:
    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = phase_def.get("dir_suffix", phase_id)
    return base_dir / _GOLDEN_DIR / dir_suffix


def extract_profile(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """从当前产物提取结构指纹（golden profile）."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    profile: dict[str, Any] = {
        "phase_id": phase_id,
        "source_project": project_id,
    }

    # 结构化 JSON 统计
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        json_path = pd / json_file
        data = load_json(json_path)
        if data is not None:
            counts = _count_all_fields(data, phase_id)
            profile["item_counts"] = counts

    # 报告结构统计
    report_file = REPORT_MAP.get(phase_id)
    if report_file:
        report_path = pd / report_file
        if report_path.exists():
            try:
                content = report_path.read_text(encoding="utf-8")
                profile["report_structure"] = _analyze_report_structure(content, phase_id)
            except OSError:
                pass

    # 必须存在的文件
    expected_files = [
        "_reasoning_log.md",
        json_file or "",
        report_file or "",
    ]
    profile["expected_files"] = [f for f in expected_files if f]
    profile["actual_files"] = [f.name for f in pd.iterdir() if f.is_file()] if pd.exists() else []

    return profile


def _count_all_fields(data: dict[str, Any], phase_id: str) -> dict[str, int]:
    """统计结构化 JSON 中所有列表字段的数量."""
    counts: dict[str, int] = {}

    for key, value in data.items():
        if isinstance(value, list):
            counts[key] = len(value)

    # Phase A 特殊：分别统计 REQ 和 BR
    if phase_id == "Q01":
        reqs = data.get("requirements", [])
        counts["req_count"] = len([r for r in reqs if r.get("req_id", "").startswith("REQ-")])
        counts["br_count"] = len([r for r in reqs if r.get("req_id", "").startswith("BR-")])

    return counts


def _analyze_report_structure(content: str, phase_id: str) -> dict[str, Any]:
    """分析报告的结构特征."""
    lines = content.split("\n")
    structure: dict[str, Any] = {
        "total_lines": len(lines),
        "h2_sections": [],
        "h3_sections": [],
        "has_mermaid": "```mermaid" in content,
        "has_image_table": "图片资产" in content or "图片语义" in content,
        "has_self_review": "自我评审" in content or "Judge/Critique" in content,
        "table_count": content.count("|---|"),
    }

    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            structure["h2_sections"].append(line[3:].strip())
        elif line.startswith("### "):
            structure["h3_sections"].append(line[4:].strip())

    return structure


def save_golden(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    base_dir: Path | None = None,
) -> Path | None:
    """将当前产物保存为 golden sample."""
    profile = extract_profile(output_dir, project_id, phase_id)
    if not profile:
        return None

    gd = _golden_dir(base_dir or output_dir.parent, phase_id)
    gd.mkdir(parents=True, exist_ok=True)

    path = gd / "golden_profile.json"
    save_json(path, profile)
    return path


def load_golden(phase_id: str, base_dir: Path | None = None) -> dict[str, Any] | None:
    """加载 golden sample profile."""
    bd = base_dir or Path(".")
    gd = _golden_dir(bd, phase_id)
    path = gd / "golden_profile.json"
    return load_json(path)


def compare_with_golden(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """对比当前产物与 golden sample.

    Returns:
        差异报告，无 golden sample 时返回 None
    """
    golden = load_golden(phase_id, base_dir or output_dir.parent)
    if not golden:
        return None

    current = extract_profile(output_dir, project_id, phase_id)
    if not current:
        return None

    diff: dict[str, Any] = {
        "phase_id": phase_id,
        "golden_source": golden.get("source_project", ""),
        "current_project": project_id,
        "issues": [],
        "score": 0,
        "max_score": 0,
    }

    # 1. 数量对比
    golden_counts = golden.get("item_counts", {})
    current_counts = current.get("item_counts", {})

    for field, golden_count in golden_counts.items():
        diff["max_score"] += 1
        current_count = current_counts.get(field, 0)
        if current_count >= golden_count:
            diff["score"] += 1
        else:
            diff["issues"].append(
                {
                    "type": "BELOW_GOLDEN",
                    "field": field,
                    "golden": golden_count,
                    "current": current_count,
                    "message": f"{field}: 当前 {current_count} 低于标杆 {golden_count}",
                }
            )

    # 2. 报告结构对比
    golden_struct = golden.get("report_structure", {})
    current_struct = current.get("report_structure", {})

    # Mermaid 图
    diff["max_score"] += 1
    if golden_struct.get("has_mermaid") and not current_struct.get("has_mermaid"):
        diff["issues"].append(
            {
                "type": "MISSING_STRUCTURE",
                "field": "mermaid",
                "message": "标杆报告包含 Mermaid 图，当前报告缺失",
            }
        )
    else:
        diff["score"] += 1

    # 图片资产表
    diff["max_score"] += 1
    if golden_struct.get("has_image_table") and not current_struct.get("has_image_table"):
        diff["issues"].append(
            {
                "type": "MISSING_STRUCTURE",
                "field": "image_table",
                "message": "标杆报告包含图片资产表，当前报告缺失",
            }
        )
    else:
        diff["score"] += 1

    # 自我评审记录
    diff["max_score"] += 1
    if golden_struct.get("has_self_review") and not current_struct.get("has_self_review"):
        diff["issues"].append(
            {
                "type": "MISSING_STRUCTURE",
                "field": "self_review",
                "message": "标杆报告包含自我评审记录，当前报告缺失",
            }
        )
    else:
        diff["score"] += 1

    # H2 章节对比
    golden_h2 = set(golden_struct.get("h2_sections", []))
    current_h2 = set(current_struct.get("h2_sections", []))
    missing_h2 = golden_h2 - current_h2
    if missing_h2:
        for section in missing_h2:
            diff["issues"].append(
                {
                    "type": "MISSING_SECTION",
                    "field": f"h2:{section}",
                    "message": f"标杆报告包含章节「{section}」，当前报告缺失",
                }
            )

    # 报告行数对比（允许 20% 波动）
    golden_lines = golden_struct.get("total_lines", 0)
    current_lines = current_struct.get("total_lines", 0)
    if golden_lines > 0 and current_lines < golden_lines * 0.8:
        diff["issues"].append(
            {
                "type": "SHORT_REPORT",
                "field": "total_lines",
                "golden": golden_lines,
                "current": current_lines,
                "message": f"报告行数 {current_lines} 低于标杆的 80%（{golden_lines} 行）",
            }
        )

    # 必须文件对比
    golden_files = set(golden.get("expected_files", []))
    current_files = set(current.get("actual_files", []))
    missing_files = golden_files - current_files
    for f in missing_files:
        diff["issues"].append(
            {
                "type": "MISSING_FILE",
                "field": f,
                "message": f"标杆要求文件 {f} 缺失",
            }
        )

    return diff


def format_golden_diff(diff: dict[str, Any]) -> str:
    """格式化 golden sample 差异报告."""
    if not diff:
        return "  无 golden sample，跳过标杆对比"

    score = diff.get("score", 0)
    max_score = diff.get("max_score", 1)
    pct = score / max(max_score, 1) * 100
    issues = diff.get("issues", [])

    lines = [
        f"  Golden Sample 对比 — Phase {diff.get('phase_id', '?')}",
        f"  标杆来源: {diff.get('golden_source', '?')}",
        f"  达标率: {score}/{max_score} ({pct:.0f}%)",
    ]

    if issues:
        lines.append(f"  差异 ({len(issues)} 项):")
        for issue in issues:
            lines.append(f"    [{issue['type']}] {issue['message']}")
    else:
        lines.append("  全部达标")

    return "\n".join(lines)
