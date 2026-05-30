"""RSM Mutations: Critique 反馈驱动的 RSM 变更.

从 rsm.py 拆分而来，负责：
1. RSMMutation 数据结构
2. apply_mutations — 应用变更到 RSM
3. mutations_from_critique — 从 CritiqueFeedback 提取变更
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qualix.constants import RSM_ID_PREFIXES

if TYPE_CHECKING:
    from qualix.schemas.rsm import RequirementLifecycle


@dataclass
class RSMMutation:
    """一条 RSM 变更."""

    target_id: str
    action: str  # add / modify / delete / escalate
    field: str = ""  # 要修改的字段（modify 时）
    value: str = ""  # 新值
    reason: str = ""


def apply_mutations(
    lifecycle: dict[str, RequirementLifecycle],
    mutations: list[RSMMutation],
) -> tuple[dict[str, RequirementLifecycle], list[str]]:
    """应用 Critique 反馈的 mutations 到 RSM.

    Returns:
        (updated_lifecycle, applied_descriptions)
    """
    from qualix.schemas.rsm import RequirementLifecycle

    applied: list[str] = []

    for mut in mutations:
        if mut.action == "add":
            if mut.target_id not in lifecycle:
                id_type = "GAP"
                for prefix in ("REQ", "BR", "SE", "OPEN"):
                    if mut.target_id.startswith(prefix):
                        id_type = prefix
                        break
                lifecycle[mut.target_id] = RequirementLifecycle(
                    req_id=mut.target_id,
                    id_type=id_type,
                    description=mut.value or mut.reason,
                )
                applied.append(f"ADD {mut.target_id}: {mut.value or mut.reason}")

        elif mut.action == "modify":
            if mut.target_id in lifecycle:
                item = lifecycle[mut.target_id]
                target_field = mut.field or "description"
                if hasattr(item, target_field) and mut.value:
                    setattr(item, target_field, mut.value)
                applied.append(f"MODIFY {mut.target_id}.{target_field}: {mut.reason}")

        elif mut.action == "delete":
            if mut.target_id in lifecycle:
                del lifecycle[mut.target_id]
                applied.append(f"DELETE {mut.target_id}: {mut.reason}")

        elif mut.action == "escalate" and mut.target_id in lifecycle:
            item = lifecycle[mut.target_id]
            if item.id_type == "GAP":
                item.closure_status = "未闭环"
            applied.append(f"ESCALATE {mut.target_id}: {mut.reason}")

    return lifecycle, applied


def mutations_from_critique(critique_data: dict) -> list[RSMMutation]:
    """从 CritiqueFeedback JSON 提取 RSM mutations.

    只提取 confidence >= 0.5 且 target_id 匹配 RSM ID 模式的反馈。
    """
    mutations: list[RSMMutation] = []
    items = critique_data.get("items", [])

    for item in items:
        confidence = item.get("confidence", 0)
        if confidence < 0.5:
            continue

        target_id = item.get("target_id", "")
        if not target_id:
            continue

        is_rsm_id = any(target_id.startswith(p) for p in RSM_ID_PREFIXES)
        if not is_rsm_id:
            continue

        mutations.append(
            RSMMutation(
                target_id=target_id,
                action=item.get("action", "modify"),
                value=item.get("patch", ""),
                reason=item.get("reason", ""),
            )
        )

    return mutations
