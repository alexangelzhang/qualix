"""Agent 工具权限控制.

按角色过滤工具：Worker 保留全部，Judge 只读，Critique 可写但不可委派。
"""

from __future__ import annotations

from typing import Callable

# 角色 → 禁止使用的工具名
ROLE_BLOCKED_TOOLS: dict[str, frozenset[str]] = {
    "worker": frozenset(),  # Worker 保留全部工具
    "judge": frozenset({
        "append_persistent_memory",  # Judge 不应写入持久记忆
        "write_to_wiki",             # Judge 不应写入 wiki
        "spawn_subagent",            # Judge 不需要委派
    }),
    "critique": frozenset({
        "spawn_subagent",            # Critique 不需要委派
    }),
    "researcher": frozenset({
        "append_persistent_memory",  # 子 agent 不应写共享 memory
        "write_to_wiki",             # 子 agent 不应写 wiki
        "spawn_subagent",            # 禁止递归委派
    }),
}


def filter_tools_by_role(tools: list[Callable], role: str) -> list[Callable]:
    """按角色过滤工具列表，移除该角色禁止使用的工具.

    Args:
        tools: 完整工具列表
        role: Agent 角色（worker/judge/critique/researcher）

    Returns:
        过滤后的工具列表
    """
    blocked = ROLE_BLOCKED_TOOLS.get(role, frozenset())
    if not blocked:
        return tools
    return [t for t in tools if t.__name__ not in blocked]
