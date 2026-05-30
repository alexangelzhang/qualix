"""Build structured handoff documents for adaptive loop iterations."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qualix.agents.judge_vote import IterationRecord


def build_handoff_document(
    prev: IterationRecord,
    next_iteration: int,
    anchor_facts: str | None = None,
) -> str:
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

    if anchor_facts:
        parts.append(anchor_facts)
        parts.append("")

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
    if prev.schema_errors:
        parts.append("### 结构化输出 / Schema（finalize 同源 Pydantic 校验失败，必须优先修复）")
        for idx, err in enumerate(prev.schema_errors, 1):
            parts.append(f"S-{idx}. [schema] {err}")
        parts.append("")
    if prev.judge_result:
        # 分两组：有精确 item_ref 的优先单独列出，让 Fixer 定点修改
        precise_issues: list[tuple[str, dict]] = []
        general_issues: list[tuple[str, dict]] = []
        issue_idx = 0
        for vote in prev.judge_result.votes:
            for issue in vote.issues:
                severity = issue.get("severity", "medium")
                if severity in ("info", "suggestion"):
                    continue
                issue_idx += 1
                issue_id = f"J-{prev.iteration:02d}-{issue_idx:03d}"
                if issue.get("item_ref"):
                    precise_issues.append((issue_id, issue))
                else:
                    general_issues.append((issue_id, issue))

        if precise_issues:
            parts.append("### 精确修改项（ONLY 修改 item_ref 指定的位置，不要重写其他内容）")
            for issue_id, issue in precise_issues:
                severity = issue.get("severity", "medium")
                parts.append(f"- [{issue_id}][{severity}] item_ref=`{issue['item_ref']}`: {issue.get('description', '')}")
                hint = issue.get("fix_hint") or issue.get("suggestion", "")
                if hint:
                    parts.append(f"  修改提示: {hint}")
            parts.append("")

        if general_issues:
            parts.append("### 通用修正项")
            for idx, (issue_id, issue) in enumerate(general_issues, 1):
                severity = issue.get("severity", "medium")
                parts.append(f"{idx}. [{issue_id}][{severity}] {issue.get('description', '')}")
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


_ANCHOR_ID_RE = re.compile(r"(REQ|BR|SE)-\d+")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 chars per token for mixed zh/en."""
    return len(text) * 2 // 3


def extract_anchor_summary(upstream_text: str, max_tokens: int = 800) -> str:
    """Extract REQ/BR/SE lines from upstream context as anchor summary.

    Groups by type (REQ, BR, SE), preserves order within each group,
    truncates to max_tokens.
    """
    if not upstream_text.strip():
        return ""

    groups: dict[str, list[str]] = {"REQ": [], "BR": [], "SE": []}
    for line in upstream_text.splitlines():
        stripped = line.strip()
        m = _ANCHOR_ID_RE.search(stripped)
        if m:
            prefix = m.group(1)
            if prefix in groups:
                groups[prefix].append(stripped)

    if not any(groups.values()):
        return ""

    parts: list[str] = [
        "## Anchor（原始需求锚点 — 修正时不可偏离）",
        "",
        "以下是本 Phase 的原始需求事实，每轮修正必须对齐：",
        "",
    ]

    section_names = {"REQ": "核心需求 (REQ)", "BR": "关键业务规则 (BR)", "SE": "语义元素 (SE)"}
    for prefix, title in section_names.items():
        items = groups[prefix]
        if items:
            parts.append(f"### {title}")
            parts.extend(items)
            parts.append("")

    result = "\n".join(parts)

    # Truncate to max_tokens
    if _estimate_tokens(result) > max_tokens:
        budget_chars = max_tokens * 3 // 2  # inverse of estimate
        result = result[:budget_chars].rsplit("\n", 1)[0]

    return result
