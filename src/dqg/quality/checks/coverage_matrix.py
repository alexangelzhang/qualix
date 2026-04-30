"""A.5 覆盖度结构化映射表：自动生成 REQ/BR/SE → 技术设计的初始矩阵.

从 Phase A 结构化产物提取所有 REQ/BR/SE/GAP/OPEN ID，
从技术设计文档提取章节标题/接口名，构建初始矩阵（全 MISSING）。
LLM 的任务从"自由审计"变成"填充矩阵"，输出更可控、可 diff。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from dqg.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


def extract_requirement_ids(phase_a_data: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """从 Phase A 结构化产物提取所有需求 ID.

    Returns:
        {
            "requirements": [{"id": "REQ-001", "description": "..."}],
            "business_rules": [{"id": "BR-001", "description": "..."}],
            "semantic_expectations": [{"id": "SE-001", "description": "..."}],
            "gaps": [{"id": "GAP-001", "description": "..."}],
            "open_items": [{"id": "OPEN-001", "description": "..."}],
        }
    """
    result: dict[str, list[dict[str, str]]] = {
        "requirements": [],
        "business_rules": [],
        "semantic_expectations": [],
        "gaps": [],
        "open_items": [],
    }

    for req in phase_a_data.get("requirements", []):
        req_id = req.get("req_id", "")
        desc = req.get("description", req.get("title", ""))
        if req_id.startswith("REQ-"):
            result["requirements"].append({"id": req_id, "description": desc[:120]})
        elif req_id.startswith("BR-"):
            result["business_rules"].append({"id": req_id, "description": desc[:120]})

    for se in phase_a_data.get("semantic_expectations", []):
        se_id = se.get("se_id", se.get("id", ""))
        desc = se.get("description", "")
        if se_id:
            result["semantic_expectations"].append({"id": se_id, "description": desc[:120]})

    for gap in phase_a_data.get("gaps", []):
        gap_id = gap.get("gap_id", gap.get("id", ""))
        desc = gap.get("description", "")
        if gap_id:
            result["gaps"].append({"id": gap_id, "description": desc[:120]})

    for item in phase_a_data.get("open_items", []):
        open_id = item.get("open_id", item.get("id", ""))
        desc = item.get("description", "")
        if open_id:
            result["open_items"].append({"id": open_id, "description": desc[:120]})

    return result


def extract_tech_design_sections(tech_design_path: Path) -> list[dict[str, str]]:
    """从技术设计文档提取章节标题和接口名.

    Returns:
        [{"section": "## 3.1 退款接口", "type": "heading"},
         {"section": "RefundService.refund()", "type": "interface"}]
    """
    if not tech_design_path.exists():
        return []

    text = tech_design_path.read_text(encoding="utf-8")
    sections: list[dict[str, str]] = []

    for line in text.splitlines():
        stripped = line.strip()
        # Markdown headings
        if re.match(r"^#{1,4}\s+", stripped):
            sections.append({"section": stripped, "type": "heading"})
        # Interface/method patterns (Java/Go style)
        m = re.match(r".*?(\w+(?:\.\w+)+\([^)]*\))", stripped)
        if m:
            sections.append({"section": m.group(1), "type": "interface"})

    return sections


def generate_coverage_matrix(
    output_dir: Path,
    project_id: str,
) -> dict[str, Any] | None:
    """生成 A.5 覆盖度初始矩阵.

    Returns:
        矩阵数据结构，或 None（Phase A 产物不存在时）
    """
    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]
    if not phase_a_path.exists():
        log.warning("Phase A 结构化产物不存在: %s", phase_a_path)
        return None

    phase_a_data = load_json(phase_a_path)
    if not phase_a_data:
        return None

    req_ids = extract_requirement_ids(phase_a_data)

    # 尝试读取技术设计文档
    tech_design_path = output_dir / project_id / PHASE_DIR_MAP["Q02"] / REPORT_MAP["Q02"]
    tech_sections = extract_tech_design_sections(tech_design_path)

    # 构建矩阵：每个 REQ/BR/SE/GAP/OPEN 一行，初始状态 MISSING
    matrix: dict[str, Any] = {
        "project_id": project_id,
        "tech_design_sections": tech_sections,
        "req_matrix": [
            {"id": r["id"], "description": r["description"], "status": "MISSING", "mapped_sections": [], "notes": ""}
            for r in req_ids["requirements"]
        ],
        "br_matrix": [
            {"id": r["id"], "description": r["description"], "status": "MISSING", "mapped_sections": [], "notes": ""}
            for r in req_ids["business_rules"]
        ],
        "se_matrix": [
            {
                "id": r["id"],
                "description": r["description"],
                "status": "MISSING",
                "mapped_sections": [],
                "failure_impact": "",
                "notes": "",
            }
            for r in req_ids["semantic_expectations"]
        ],
        "gap_matrix": [
            {"id": r["id"], "description": r["description"], "closure_status": "未闭环", "notes": ""}
            for r in req_ids["gaps"]
        ],
        "open_matrix": [
            {"id": r["id"], "description": r["description"], "closure_status": "未闭环", "notes": ""}
            for r in req_ids["open_items"]
        ],
        "summary": {
            "total_req": len(req_ids["requirements"]),
            "total_br": len(req_ids["business_rules"]),
            "total_se": len(req_ids["semantic_expectations"]),
            "total_gap": len(req_ids["gaps"]),
            "total_open": len(req_ids["open_items"]),
        },
    }

    return matrix


def write_coverage_matrix(output_dir: Path, project_id: str) -> Path | None:
    """生成并写入覆盖度矩阵到 Phase A.5 目录.

    Returns:
        写入的文件路径，或 None
    """
    matrix = generate_coverage_matrix(output_dir, project_id)
    if not matrix:
        return None

    a5_dir = output_dir / project_id / PHASE_DIR_MAP["Q04"]
    a5_dir.mkdir(parents=True, exist_ok=True)
    int_dir = a5_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    matrix_path = int_dir / "_coverage_matrix.json"
    save_json(matrix_path, matrix)
    log.info("覆盖度矩阵已生成: %s", matrix_path)

    # 同时生成 Markdown 版本供 LLM 填充
    md_path = int_dir / "_coverage_matrix.md"
    md_path.write_text(_render_matrix_markdown(matrix), encoding="utf-8")

    return matrix_path


def _render_matrix_markdown(matrix: dict[str, Any]) -> str:
    """将矩阵渲染为 Markdown 表格，供 LLM 填充."""
    lines = [
        "# 覆盖度审计矩阵（LLM 填充用）",
        "",
        "请逐行审计，将 status 从 MISSING 更新为 COVERED/PARTIAL/IMPLICIT，并填写 mapped_sections 和 notes。",
        "",
    ]

    # REQ
    if matrix["req_matrix"]:
        lines.append("## REQ 覆盖度")
        lines.append("")
        lines.append("| ID | 描述 | 状态 | 映射章节 | 备注 |")
        lines.append("|---|---|---|---|---|")
        for row in matrix["req_matrix"]:
            lines.append(f"| {row['id']} | {row['description'][:60]} | {row['status']} | | |")
        lines.append("")

    # BR
    if matrix["br_matrix"]:
        lines.append("## BR 覆盖度")
        lines.append("")
        lines.append("| ID | 描述 | 状态 | 映射章节 | 备注 |")
        lines.append("|---|---|---|---|---|")
        for row in matrix["br_matrix"]:
            lines.append(f"| {row['id']} | {row['description'][:60]} | {row['status']} | | |")
        lines.append("")

    # SE
    if matrix["se_matrix"]:
        lines.append("## SE 覆盖度")
        lines.append("")
        lines.append("| ID | 描述 | 状态 | 失败影响 | 映射章节 | 备注 |")
        lines.append("|---|---|---|---|---|---|")
        for row in matrix["se_matrix"]:
            lines.append(f"| {row['id']} | {row['description'][:60]} | {row['status']} | | | |")
        lines.append("")

    # GAP
    if matrix["gap_matrix"]:
        lines.append("## GAP 闭环")
        lines.append("")
        lines.append("| ID | 描述 | 闭环状态 | 备注 |")
        lines.append("|---|---|---|---|")
        for row in matrix["gap_matrix"]:
            lines.append(f"| {row['id']} | {row['description'][:60]} | {row['closure_status']} | |")
        lines.append("")

    # OPEN
    if matrix["open_matrix"]:
        lines.append("## OPEN 闭环")
        lines.append("")
        lines.append("| ID | 描述 | 闭环状态 | 备注 |")
        lines.append("|---|---|---|---|")
        for row in matrix["open_matrix"]:
            lines.append(f"| {row['id']} | {row['description'][:60]} | {row['closure_status']} | |")
        lines.append("")

    # 技术设计章节参考
    if matrix["tech_design_sections"]:
        lines.append("## 技术设计章节参考")
        lines.append("")
        for i, sec in enumerate(matrix["tech_design_sections"], 1):
            lines.append(f"{i}. [{sec['type']}] {sec['section']}")
        lines.append("")

    s = matrix["summary"]
    lines.append(
        f"统计: REQ={s['total_req']} BR={s['total_br']} SE={s['total_se']} GAP={s['total_gap']} OPEN={s['total_open']}"
    )

    return "\n".join(lines)
