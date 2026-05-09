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


def validate_eut_id_subset(phase_b: dict | None, phase_c: dict | None) -> list[str]:
    """校验 Q06 `audit_items` 中出现的 EUT ID 均为 Q05 `eut_items` 的子集（phantom EUT 阻断）.

    - phase_b 缺失（文件不存在 / 读取失败）而 Q06 已引用 EUT → 报错（历史上 `phase_b` 为 falsy 时整条校验被跳过）。
    - Q05 `eut_items` 为空但 Q06 引用任意 EUT → 每条引用单独报错（与旧行为一致）。
    """
    errors: list[str] = []
    if not phase_c or not isinstance(phase_c, dict):
        return errors
    audit_items = phase_c.get("audit_items", [])
    if not isinstance(audit_items, list):
        return errors

    has_eut_ref = False
    for item in audit_items:
        if isinstance(item, dict) and item.get("eut_id"):
            has_eut_ref = True
            break
    if not has_eut_ref:
        return errors

    if phase_b is None:
        errors.append(
            "Phase Q06 audit_items 引用了 EUT，但未找到 Phase Q05 结构化产物 phase_b_structured.json（无法对齐 Q05→Q06 EUT 子集）"
        )
        return errors

    eut_ids = _extract_ids(phase_b, "eut_items", "eut_id")
    for item in audit_items:
        if not isinstance(item, dict):
            continue
        ref_raw = item.get("eut_id", "")
        if not ref_raw:
            continue
        expanded = expand_eut_ids(ref_raw)
        missing = expanded - eut_ids
        if missing:
            errors.append(f"Phase Q06 审计了 {', '.join(sorted(missing))}，但 Phase Q05 中不存在")
    return errors


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

    # 校验 Phase C：审计的 EUT ID 是否为 Phase B 的子集（phantom EUT）
    phase_c_path = output_dir / project_id / PHASE_DIR_MAP["Q06"] / STRUCTURED_JSON_MAP["Q06"]
    phase_c = load_json(phase_c_path)

    if phase_c:
        _record_hash(phase_c_path)
        errors.extend(validate_eut_id_subset(phase_b, phase_c))

    return errors, upstream_hashes
