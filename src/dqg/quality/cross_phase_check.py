"""跨 Phase ID 引用完整性校验.

确保下游 Phase 引用的 ID 在上游 Phase 产物中确实存在。
例如：Phase B 的 EUT 绑定了 SE-001，Phase A 必须有 SE-001。
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json


def _extract_ids(data: dict, key: str, id_field: str) -> set[str]:
    """从结构化 JSON 中提取 ID 集合."""
    items = data.get(key, [])
    if not isinstance(items, list):
        return set()
    return {item.get(id_field, "") for item in items if isinstance(item, dict) and item.get(id_field)}


def check_cross_phase_refs(output_dir: Path, project_id: str) -> list[str]:
    """校验跨 Phase 的 ID 引用完整性.

    Returns:
        []: 全部通过
        ["error1", ...]: 引用缺失列表
    """
    errors: list[str] = []

    # 加载 Phase A 产物
    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["A"] / STRUCTURED_JSON_MAP["A"]
    phase_a = load_json(phase_a_path)

    if not phase_a:
        return []  # Phase A 没有结构化产物，跳过

    # Phase A 中定义的 ID
    req_ids = _extract_ids(phase_a, "requirements", "req_id")
    se_ids = _extract_ids(phase_a, "semantic_expectations", "se_id")
    gap_ids = _extract_ids(phase_a, "gaps", "gap_id")
    open_ids = _extract_ids(phase_a, "open_items", "open_id")

    # 校验 Phase A.5：覆盖矩阵引用的 REQ/BR/SE/GAP/OPEN 是否存在
    phase_a5_path = output_dir / project_id / PHASE_DIR_MAP["A.5"] / STRUCTURED_JSON_MAP["A.5"]
    phase_a5 = load_json(phase_a5_path)
    if not phase_a5:
        phase_a5_path = output_dir / project_id / PHASE_DIR_MAP["A"] / STRUCTURED_JSON_MAP["A.5"]
        phase_a5 = load_json(phase_a5_path)

    if phase_a5:
        for item in phase_a5.get("req_coverage", []):
            ref_id = item.get("req_id", "")
            if ref_id and ref_id not in req_ids:
                errors.append(f"Phase A.5 引用了 {ref_id}，但 Phase A 中不存在")

        for item in phase_a5.get("se_coverage", []):
            ref_id = item.get("se_id", "")
            if ref_id and ref_id not in se_ids:
                errors.append(f"Phase A.5 引用了 {ref_id}，但 Phase A 中不存在")

        for item in phase_a5.get("gap_closure", []):
            ref_id = item.get("gap_id", "")
            if ref_id and ref_id not in gap_ids:
                errors.append(f"Phase A.5 引用了 {ref_id}，但 Phase A 中不存在")

        for item in phase_a5.get("open_closure", []):
            ref_id = item.get("open_id", "")
            if ref_id and ref_id not in open_ids:
                errors.append(f"Phase A.5 引用了 {ref_id}，但 Phase A 中不存在")

    # 校验 Phase B：EUT 绑定的 SE 是否存在
    phase_b_path = output_dir / project_id / PHASE_DIR_MAP["B"] / STRUCTURED_JSON_MAP["B"]
    phase_b = load_json(phase_b_path)

    if phase_b:
        for item in phase_b.get("eut_items", []):
            bound_se = item.get("bound_se", "")
            if bound_se and bound_se not in se_ids and bound_se not in req_ids:
                errors.append(f"Phase B EUT {item.get('eut_id', '?')} 绑定了 {bound_se}，但 Phase A 中不存在")

    # 校验 Phase C：审计的 EUT ID 是否在 Phase B 中存在
    phase_c_path = output_dir / project_id / PHASE_DIR_MAP["C"] / STRUCTURED_JSON_MAP["C"]
    phase_c = load_json(phase_c_path)

    if phase_b and phase_c:
        eut_ids = _extract_ids(phase_b, "eut_items", "eut_id")
        for item in phase_c.get("audit_items", []):
            ref_id = item.get("eut_id", "")
            if ref_id and ref_id not in eut_ids:
                errors.append(f"Phase C 审计了 {ref_id}，但 Phase B 中不存在")

    return errors
