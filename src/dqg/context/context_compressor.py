"""Context Compressor：adaptive loop 多轮执行时的上下文压缩.

借鉴 Hermes Agent 的 context_compressor.py 设计：
1. Tool result 裁剪（>200 chars 替换 placeholder，零 LLM 调用）
2. 结构化迭代摘要（Goal/Progress/Decisions/Next Steps）
3. Tool_call/tool_result 孤儿修复
"""

from __future__ import annotations

import re
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# 裁剪阈值
_TOOL_RESULT_MAX_CHARS = 200
_PRUNED_PLACEHOLDER = "[tool result pruned — see earlier context]"
_SUMMARY_RATIO = 0.20  # 摘要预算 = 被压缩内容量的 20%

# 结构化摘要模板
_SUMMARY_TEMPLATE = """## Context Summary (auto-generated)

### Goal
{goal}

### Progress
- Done: {done}
- In Progress: {in_progress}
- Blocked: {blocked}

### Key Decisions
{decisions}

### Critical Context
{critical}

### Next Steps
{next_steps}
"""

# Tool result 匹配
_TOOL_RESULT_RE = re.compile(r"<tool_result>[\s\S]*?</tool_result>", re.MULTILINE)
_TOOL_CALL_ID_RE = re.compile(r'tool_use_id["\s:]+([a-zA-Z0-9_-]+)')


def prune_old_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Phase 1: 裁剪旧的 tool results（零 LLM 调用）.

    保留最近 2 轮的 tool results 完整，更早的替换为 placeholder。
    """
    if len(messages) <= 4:
        return messages

    # 找到最近 2 个 assistant 消息的索引
    assistant_indices = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    if len(assistant_indices) <= 2:
        return messages

    cutoff_idx = assistant_indices[-2]
    pruned = []

    for i, msg in enumerate(messages):
        if i >= cutoff_idx:
            pruned.append(msg)
            continue

        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > _TOOL_RESULT_MAX_CHARS:
            # 检查是否是 tool result
            if msg.get("role") == "tool" or "<tool_result>" in content:
                pruned.append({
                    **msg,
                    "content": _PRUNED_PLACEHOLDER,
                    "_pruned": True,
                })
                continue

        pruned.append(msg)

    pruned_count = sum(1 for m in pruned if m.get("_pruned"))
    if pruned_count > 0:
        log.debug("Pruned %d old tool results", pruned_count)

    return pruned


def generate_structured_summary(
    messages: list[dict[str, Any]],
    phase_id: str = "",
    previous_summary: str | None = None,
) -> str:
    """Phase 2: 生成结构化摘要.

    如果有 previous_summary，做增量更新而非重新生成。
    """
    # 从消息中提取关键信息
    goal = f"Phase {phase_id} 执行" if phase_id else "任务执行"
    done_items: list[str] = []
    in_progress_items: list[str] = []
    blocked_items: list[str] = []
    decisions: list[str] = []
    critical: list[str] = []

    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # 提取已完成的步骤
        for match in re.finditer(r"Step \d+.*?(?:完成|done|passed)", content, re.IGNORECASE):
            done_items.append(match.group()[:80])

        # 提取阻断项
        for match in re.finditer(r"(?:BLOCKED|FAIL|ERROR)[:：]\s*(.+?)(?:\n|$)", content):
            blocked_items.append(match.group(1)[:80])

        # 提取决策
        for match in re.finditer(r"(?:决策|决定|选择|确认)[:：]\s*(.+?)(?:\n|$)", content):
            decisions.append(match.group(1)[:80])

        # 提取关键数值
        for match in re.finditer(r"(?:覆盖率|score|评分|达标率).*?[\d.]+%?", content, re.IGNORECASE):
            critical.append(match.group()[:80])

    # 如果有上一次摘要，增量更新
    if previous_summary:
        return _incremental_update(previous_summary, done_items, blocked_items, decisions, critical)

    return _SUMMARY_TEMPLATE.format(
        goal=goal,
        done="; ".join(done_items[:5]) or "无",
        in_progress="; ".join(in_progress_items[:3]) or "执行中",
        blocked="; ".join(blocked_items[:3]) or "无",
        decisions="\n".join(f"- {d}" for d in decisions[:5]) or "- 无",
        critical="\n".join(f"- {c}" for c in critical[:5]) or "- 无",
        next_steps="继续执行",
    )


def sanitize_tool_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Phase 3: 修复 tool_call/tool_result 孤儿对.

    压缩后可能出现 tool_call 没有对应 result，或 result 没有对应 call。
    """
    # 收集所有 tool_call IDs
    call_ids: set[str] = set()
    result_ids: set[str] = set()

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            for match in _TOOL_CALL_ID_RE.finditer(content):
                if msg.get("role") == "assistant":
                    call_ids.add(match.group(1))
                elif msg.get("role") == "tool":
                    result_ids.add(match.group(1))

        # 处理结构化 content（list of blocks）
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        call_ids.add(block.get("id", ""))
                    elif block.get("type") == "tool_result":
                        result_ids.add(block.get("tool_use_id", ""))

    orphan_calls = call_ids - result_ids
    orphan_results = result_ids - call_ids

    if not orphan_calls and not orphan_results:
        return messages

    log.debug("Fixing %d orphan calls, %d orphan results", len(orphan_calls), len(orphan_results))

    # 为孤儿 call 补 stub result
    fixed = list(messages)
    for call_id in orphan_calls:
        fixed.append({
            "role": "tool",
            "content": "[result pruned during context compression]",
            "tool_use_id": call_id,
        })

    # 删除孤儿 result（没有对应 call 的 result）
    fixed = [
        m for m in fixed
        if not (
            isinstance(m.get("content"), list)
            and any(
                isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in orphan_results
                for b in m["content"]
            )
        )
    ]

    return fixed


def compress_context(
    messages: list[dict[str, Any]],
    phase_id: str = "",
    previous_summary: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """完整的上下文压缩流程.

    Returns:
        (compressed_messages, summary)
    """
    # Phase 1: 裁剪旧 tool results
    pruned = prune_old_tool_results(messages)

    # Phase 2: 生成结构化摘要
    summary = generate_structured_summary(pruned, phase_id, previous_summary)

    # Phase 3: 修复孤儿对
    fixed = sanitize_tool_pairs(pruned)

    return fixed, summary


def _incremental_update(
    previous: str,
    new_done: list[str],
    new_blocked: list[str],
    new_decisions: list[str],
    new_critical: list[str],
) -> str:
    """增量更新摘要（保留已有信息，只追加新内容）."""
    lines = previous.split("\n")
    updated: list[str] = []

    for line in lines:
        updated.append(line)
        # 在 Done 段后追加新完成项
        if line.strip().startswith("- Done:") and new_done:
            for d in new_done[:3]:
                updated.append(f"  - [NEW] {d}")
        # 在 Blocked 段后追加新阻断项
        if line.strip().startswith("- Blocked:") and new_blocked:
            for b in new_blocked[:3]:
                updated.append(f"  - [NEW] {b}")

    # 追加新决策
    if new_decisions:
        updated.append("")
        updated.append("### New Decisions (this iteration)")
        for d in new_decisions[:3]:
            updated.append(f"- {d}")

    return "\n".join(updated)
