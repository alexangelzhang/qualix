"""Build structured handoff documents for adaptive loop iterations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dqg.agents.judge_vote import IterationRecord


def build_handoff_document(prev: "IterationRecord", next_iteration: int) -> str:
    """生成结构化交接文档（Anthropic Context Reset 模式）.

    交接文档是新 agent 实例的唯一上下文来源（除了原始 context_files），
    确保关键信息不会在 context 压缩中丢失。
    """
    parts = [
        f"# 交接文档 — 第 {next_iteration} 轮修正",
        "",
        "## Goal（任务目标）",
        "修正上一轮报告中 Judge 和 Critique 指出的问题，输出改进后的完整报告。",
        "",
    ]

    parts.append("## Progress（上一轮进展）")
    parts.append(f"- 迭代轮次: 第 {prev.iteration} 轮")
    if prev.judge_result:
        parts.append(f"- Judge 共识: {prev.judge_result.consensus}")
        parts.append(f"- Judge 均分: {prev.judge_result.avg_score:.1f}")
    parts.append("")

    parts.append("## Decisions（已确认的决策，修正时不要推翻）")
    if prev.judge_result:
        for vote in prev.judge_result.votes:
            for issue in vote.issues:
                if issue.get("severity") in ("info", "suggestion"):
                    parts.append(f"- [保留] {issue.get('description', '')}")
    if not any(line.startswith("- [保留]") for line in parts):
        parts.append("- （无需特别保留的决策）")
    parts.append("")

    parts.append("## Issues（必须修正的问题，按严重程度排序）")
    if prev.judge_result:
        issue_idx = 0
        for vote in prev.judge_result.votes:
            for issue in vote.issues:
                severity = issue.get("severity", "medium")
                if severity in ("info", "suggestion"):
                    continue
                issue_idx += 1
                parts.append(f"{issue_idx}. [{severity}] {issue.get('description', '')}")
                if issue.get("suggestion"):
                    parts.append(f"   建议: {issue['suggestion']}")
    if prev.judge_result and prev.judge_result.disagreements:
        parts.append("")
        parts.append("### Judge 分歧")
        for d in prev.judge_result.disagreements:
            parts.append(f"- {d}")
    parts.append("")

    if prev.critique_result and prev.critique_result.status != "failed":
        parts.append("## Critique 发现")
        critique_text = prev.critique_result.content
        if len(critique_text) > 2000:
            critique_text = critique_text[:2000] + "\n...(截断)"
        parts.append(critique_text)
        parts.append("")

    parts.append("## Next Steps（修正指引）")
    parts.append("1. 逐条修正上述 Issues 中的问题")
    parts.append("2. 保留 Decisions 中已确认的内容")
    parts.append("3. 修正后在报告末尾更新「自我评审记录」章节")
    parts.append("4. 确保修正不引入新问题")

    return "\n".join(parts)
