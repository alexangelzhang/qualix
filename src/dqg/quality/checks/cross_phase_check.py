"""跨 Phase ID 引用完整性校验.

确保下游 Phase 引用的 ID 在上游 Phase 产物中确实存在。
例如：Phase B 的 EUT 绑定了 SE-001，Phase A 必须有 SE-001。
"""

from __future__ import annotations

from pathlib import Path

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json
from dqg.runtime.gate_verdict import compute_file_hash
from dqg.text_utils import expand_eut_ids


def _extract_ids(data: dict, key: str, id_field: str) -> set[str]:
    """从结构化 JSON 中提取 ID 集合."""
    items = data.get(key, [])
    if not isinstance(items, list):
        return set()
    return {item.get(id_field, "") for item in items if isinstance(item, dict) and item.get(id_field)}


def check_cross_phase_refs(output_dir: Path, project_id: str) -> tuple[list[str], dict[str, str]]:
    """校验跨 Phase 的 ID 引用完整性.

    Returns:
        (errors, upstream_hashes):
            errors: 引用缺失列表，空表示全部通过
            upstream_hashes: 实际读取的上游产物文件相对路径 → MD5 哈希
    """
    errors: list[str] = []
    upstream_hashes: dict[str, str] = {}
    base = output_dir / project_id

    def _record_hash(path: Path) -> None:
        if path.exists():
            upstream_hashes[str(path.relative_to(base))] = compute_file_hash(path)

    # 加载 Phase A 产物
    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]
    phase_a = load_json(phase_a_path)

    if not phase_a:
        return [], {}  # Phase A 没有结构化产物，跳过

    _record_hash(phase_a_path)

    # Phase A 中定义的 ID
    req_ids = _extract_ids(phase_a, "requirements", "req_id")
    se_ids = _extract_ids(phase_a, "semantic_expectations", "se_id")
    gap_ids = _extract_ids(phase_a, "gaps", "gap_id")
    open_ids = _extract_ids(phase_a, "open_items", "open_id")

    # 校验 Phase A.5：覆盖矩阵引用的 REQ/BR/SE/GAP/OPEN 是否存在
    phase_a5_path = output_dir / project_id / PHASE_DIR_MAP["Q04"] / STRUCTURED_JSON_MAP["Q04"]
    phase_a5 = load_json(phase_a5_path)
    if not phase_a5:
        phase_a5_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q04"]
        phase_a5 = load_json(phase_a5_path)

    if phase_a5:
        _record_hash(phase_a5_path)
        for item in phase_a5.get("req_coverage", []):
            ref_id = item.get("req_id", "")
            if ref_id and ref_id not in req_ids:
                errors.append(f"Phase Q04 引用了 {ref_id}，但 Phase Q01 中不存在")

        for item in phase_a5.get("se_coverage", []):
            ref_id = item.get("se_id", "")
            if ref_id and ref_id not in se_ids:
                errors.append(f"Phase Q04 引用了 {ref_id}，但 Phase Q01 中不存在")

        for item in phase_a5.get("gap_closure", []):
            ref_id = item.get("gap_id", "")
            if ref_id and ref_id not in gap_ids:
                errors.append(f"Phase Q04 引用了 {ref_id}，但 Phase Q01 中不存在")

        for item in phase_a5.get("open_closure", []):
            ref_id = item.get("open_id", "")
            if ref_id and ref_id not in open_ids:
                errors.append(f"Phase Q04 引用了 {ref_id}，但 Phase Q01 中不存在")

    # 校验 Phase B：EUT 绑定的 SE 是否存在
    phase_b_path = output_dir / project_id / PHASE_DIR_MAP["Q05"] / STRUCTURED_JSON_MAP["Q05"]
    phase_b = load_json(phase_b_path)

    if phase_b:
        _record_hash(phase_b_path)
        for item in phase_b.get("eut_items", []):
            bound_se = item.get("bound_se", "")
            if bound_se and bound_se not in se_ids and bound_se not in req_ids:
                errors.append(f"Phase Q05 EUT {item.get('eut_id', '?')} 绑定了 {bound_se}，但 Phase Q01 中不存在")

    # 校验 Phase C：审计的 EUT ID 是否在 Phase B 中存在
    phase_c_path = output_dir / project_id / PHASE_DIR_MAP["Q06"] / STRUCTURED_JSON_MAP["Q06"]
    phase_c = load_json(phase_c_path)

    if phase_b and phase_c:
        eut_ids = _extract_ids(phase_b, "eut_items", "eut_id")
        for item in phase_c.get("audit_items", []):
            ref_raw = item.get("eut_id", "")
            if not ref_raw:
                continue
            expanded = expand_eut_ids(ref_raw)
            missing = expanded - eut_ids
            if missing:
                errors.append(f"Phase Q06 审计了 {', '.join(sorted(missing))}，但 Phase Q05 中不存在")

    return errors, upstream_hashes
