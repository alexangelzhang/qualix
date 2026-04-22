"""Critique 可执行反馈 Schema.

Critique 输出从自然语言意见升级为结构化可执行反馈。
每条反馈包含 target_id、action、patch，Worker 修正时直接消费。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CritiqueAction(StrEnum):
    ADD = "add"           # 新增一条 REQ/GAP/SE 等
    MODIFY = "modify"     # 修改已有条目的内容
    DELETE = "delete"      # 删除误报/重复条目
    ESCALATE = "escalate"  # 升级严重等级或标记为 BLOCKER


class CritiqueFeedbackItem(BaseModel):
    """单条可执行反馈."""

    target_id: str = Field(
        min_length=1,
        description="要操作的 ID（如 REQ-001、GAP-002）。新增时填期望的 ID。",
    )
    action: CritiqueAction = Field(
        description="操作类型：add/modify/delete/escalate",
    )
    reason: str = Field(
        min_length=1,
        description="为什么需要这个修改（必须引用具体证据）",
    )
    patch: str = Field(
        default="",
        description="具体修改内容。modify 时填新的 description；add 时填完整条目内容；delete 时可为空。",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="置信度 0-1。低于 0.5 的反馈 Worker 可以忽略。",
    )
    evidence_source: str = Field(
        default="",
        description="证据来源（如 'PRD 第3段' 或 'Phase Q01 REQ-001'）",
    )


class CritiqueFeedback(BaseModel):
    """Critique 的完整可执行反馈."""

    phase_id: str = Field(min_length=1)
    items: list[CritiqueFeedbackItem] = Field(default_factory=list)
    summary: str = Field(
        default="",
        description="一句话总结：最严重的问题是什么",
    )

    @property
    def actionable_items(self) -> list[CritiqueFeedbackItem]:
        """过滤掉低置信度的反馈，只返回可执行的."""
        return [item for item in self.items if item.confidence >= 0.5]

    @property
    def high_confidence_items(self) -> list[CritiqueFeedbackItem]:
        """高置信度反馈（>= 0.8）."""
        return [item for item in self.items if item.confidence >= 0.8]

    def render_for_worker(self) -> str:
        """渲染为 Worker 可直接消费的修正指令."""
        if not self.actionable_items:
            return "无可执行的修正建议。"

        lines = [f"## Critique 可执行反馈 — Phase {self.phase_id}\n"]
        if self.summary:
            lines.append(f"**核心问题**: {self.summary}\n")

        for i, item in enumerate(self.actionable_items, 1):
            conf_tag = "HIGH" if item.confidence >= 0.8 else "MED"
            lines.append(f"### [{conf_tag}] {i}. {item.action.upper()} {item.target_id}")
            lines.append(f"- 原因: {item.reason}")
            if item.patch:
                lines.append(f"- 修改内容: {item.patch}")
            if item.evidence_source:
                lines.append(f"- 证据: {item.evidence_source}")
            lines.append("")

        return "\n".join(lines)
