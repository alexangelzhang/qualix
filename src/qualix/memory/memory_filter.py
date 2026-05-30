"""Memory 分级：解析 .qualix/MEMORY.md 条目，按类型和项目绑定过滤.

Memory 条目格式约定：
- 普通条目：`- 规则描述`
- 带项目绑定：`- [project:xxx] 规则描述`
- 带类型标签：`- [global] 通用规则` 或 `- [project:xxx] 项目特定规则`

未标注的条目视为 global（向后兼容）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROJECT_TAG_RE = re.compile(r"^\[project:([^\]]+)\]\s*")
_GLOBAL_TAG_RE = re.compile(r"^\[global\]\s*")

# Phase A 是 pipeline 起点，最容易被历史 memory 污染
# 只注入 global 规则，不注入项目特定 memory
PHASES_GLOBAL_ONLY: frozenset[str] = frozenset({"Q01"})

MEMORY_DISCLAIMER = (
    "[System note: 以下是历史记忆条目，可能已过时。"
    "请以当前 PRD/技术方案原文为准，不要让记忆覆盖原文证据。"
    "如果记忆与原文矛盾，以原文为准。]\n\n"
)


@dataclass
class MemoryEntry:
    """一条 memory 条目."""

    raw: str
    content: str  # 去掉标签后的内容
    scope: str  # "global" 或 "project:<id>"
    project_id: str  # 绑定的项目 ID，global 为空


def parse_memory_entries(mem_text: str) -> list[MemoryEntry]:
    """解析 MEMORY.md 的条目列表."""
    entries: list[MemoryEntry] = []
    for line in mem_text.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("- "):
            continue

        body = line[2:].strip()

        # 检查项目绑定标签
        proj_match = _PROJECT_TAG_RE.match(body)
        if proj_match:
            pid = proj_match.group(1).strip()
            content = body[proj_match.end() :].strip()
            entries.append(MemoryEntry(raw=line, content=content, scope=f"project:{pid}", project_id=pid))
            continue

        # 检查 global 标签
        global_match = _GLOBAL_TAG_RE.match(body)
        if global_match:
            content = body[global_match.end() :].strip()
            entries.append(MemoryEntry(raw=line, content=content, scope="global", project_id=""))
            continue

        # 无标签：视为 global（向后兼容）
        entries.append(MemoryEntry(raw=line, content=body, scope="global", project_id=""))

    return entries


def filter_memory_for_phase(
    entries: list[MemoryEntry],
    project_id: str,
    phase_id: str,
) -> str:
    """按 Phase 和项目过滤 memory 条目，返回渲染后的文本.

    规则：
    - Phase A（PHASES_GLOBAL_ONLY）：只注入 global 条目
    - 其他 Phase：注入 global + 当前项目的 project 条目
    - 其他项目的 project 条目永远不注入
    """
    global_only = phase_id in PHASES_GLOBAL_ONLY
    filtered: list[str] = []

    for entry in entries:
        if entry.scope == "global" or (not global_only and entry.project_id == project_id):
            filtered.append(f"- {entry.content}")
        # 其他项目的条目：跳过

    if not filtered:
        return ""

    return MEMORY_DISCLAIMER + "\n".join(filtered)
