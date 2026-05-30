"""Phase Contract 构造纯函数（不写盘）.

与 ``phase_contract.generate_phase_contract`` 的区别：
- 本模块只构造 dict，供只读场景（``qualix-run spec``）使用
- ``phase_contract.generate_phase_contract`` 仍然是执行流程的写盘入口（内部调本模块）

拆分原因：原 ``phase_contract.py`` 已 391 行接近 400 行铁律上限，新增纯函数版
放独立文件避免超限，并把"构造"和"持久化"语义分离。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def build_phase_contract(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """纯函数：构造 contract 字典，不写盘。

    供 ``qualix-run spec`` 等只读场景消费。``generate_phase_contract`` 调用本函数
    后再写盘。

    Returns:
        contract dict；phase_id 未注册时返回 None
    """
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.runtime.phase_contract import (
        _collect_evidence_refs,
        _extract_verification_targets,
        _get_hard_checks,
    )

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    return {
        "project_id": project_id,
        "phase_id": phase_id,
        "done_definition": list(phase_def.get("approve_checklist", [])),
        "verification_targets": _extract_verification_targets(output_dir, project_id, phase_id),
        "evidence_refs": _collect_evidence_refs(output_dir, project_id, phase_id),
        "hard_checks": _get_hard_checks(phase_id),
        "status": "active",
    }
