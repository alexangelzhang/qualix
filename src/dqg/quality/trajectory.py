"""Trajectory Compressor: 压缩 Agent 执行轨迹为训练数据.

参考 Hermes Agent 的 trajectory_compressor.py，适配 DQG 场景。

压缩策略：
1. 保护首 turn（system prompt）和尾 turn（最终输出）
2. 保护 tool_call + tool_result 对（保留工具名和摘要）
3. 压缩中间 assistant turn 的冗余推理
4. 输出 JSONL 格式，可用于 Preference 比较和 prompt 优化

用法：
    from dqg.quality.trajectory import compress_trajectory, save_trajectories
    compressed = compress_trajectory(agent_result.trajectory, agent_result)
    save_trajectories(output_dir, project_id, phase_id, [compressed])
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

PROTECT_FIRST_N = 2       # 保护前 N 条（system + 首个 user）
PROTECT_LAST_N = 2        # 保护最后 N 条（最终 assistant 输出）
TOOL_RESULT_SUMMARY_LIMIT = 500   # tool_result 摘要字符上限
MIDDLE_TURN_SUMMARY_LIMIT = 300   # 中间 assistant turn 摘要字符上限

_TOOL_RESULT_RE = re.compile(
    r"<tool_result\s+name=\"(.*?)\">\n(.*?)\n</tool_result>", re.DOTALL
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class CompressedTrajectory:
    """压缩后的 trajectory."""

    project_id: str
    phase_id: str
    agent_name: str
    agent_role: str
    model_used: str
    status: str
    duration_seconds: float
    token_usage: dict[str, int]
    original_turns: int
    compressed_turns: int
    messages: list[dict[str, str]]
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 压缩逻辑
# ---------------------------------------------------------------------------

def _summarize_tool_result(content: str) -> str:
    """压缩 tool_result：保留工具名 + 结果摘要."""
    match = _TOOL_RESULT_RE.search(content)
    if not match:
        if len(content) > TOOL_RESULT_SUMMARY_LIMIT:
            return content[:TOOL_RESULT_SUMMARY_LIMIT] + "...(truncated)"
        return content

    tool_name = match.group(1)
    result_body = match.group(2).strip()
    if len(result_body) > TOOL_RESULT_SUMMARY_LIMIT:
        result_body = result_body[:TOOL_RESULT_SUMMARY_LIMIT] + "...(truncated)"
    return f'<tool_result name="{tool_name}">\n{result_body}\n</tool_result>'


def _summarize_assistant_turn(content: str) -> str:
    """压缩中间 assistant turn：保留 tool_call 标签 + 首段摘要."""
    # 保留 tool_call 标签完整
    tool_call_match = re.search(
        r"<tool_call\s+name=\".*?\">.*?</tool_call>", content, re.DOTALL
    )
    if tool_call_match:
        return tool_call_match.group(0)

    # 非 tool_call 的中间 turn：取首段
    if len(content) > MIDDLE_TURN_SUMMARY_LIMIT:
        return content[:MIDDLE_TURN_SUMMARY_LIMIT] + "...(truncated)"
    return content


def compress_trajectory(
    trajectory: list[dict[str, str]],
    project_id: str,
    phase_id: str,
    agent_name: str = "",
    agent_role: str = "",
    model_used: str = "",
    status: str = "",
    duration_seconds: float = 0,
    token_usage: dict[str, int] | None = None,
) -> CompressedTrajectory:
    """压缩一条 trajectory.

    Args:
        trajectory: Agent.run() 产生的原始 messages 列表
        其余参数: Agent 元数据

    Returns:
        CompressedTrajectory
    """
    if not trajectory:
        return CompressedTrajectory(
            project_id=project_id,
            phase_id=phase_id,
            agent_name=agent_name,
            agent_role=agent_role,
            model_used=model_used,
            status=status,
            duration_seconds=duration_seconds,
            token_usage=token_usage or {},
            original_turns=0,
            compressed_turns=0,
            messages=[],
            timestamp=_now_iso(),
        )

    original_turns = len(trajectory)
    compressed: list[dict[str, str]] = []

    # 保护头部
    head = trajectory[:PROTECT_FIRST_N]
    # 保护尾部（避免和头部重叠）
    tail_start = max(PROTECT_FIRST_N, len(trajectory) - PROTECT_LAST_N)
    tail = trajectory[tail_start:]
    # 中间部分需要压缩
    middle = trajectory[PROTECT_FIRST_N:tail_start]

    # 头部原样保留
    compressed.extend(head)

    # 中间部分压缩
    for msg in middle:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant":
            compressed.append({
                "role": "assistant",
                "content": _summarize_assistant_turn(content),
            })
        elif role == "user" and _TOOL_RESULT_RE.search(content):
            compressed.append({
                "role": "user",
                "content": _summarize_tool_result(content),
            })
        else:
            # 其他 user message 保留（通常是 feedback）
            if len(content) > MIDDLE_TURN_SUMMARY_LIMIT:
                content = content[:MIDDLE_TURN_SUMMARY_LIMIT] + "...(truncated)"
            compressed.append({"role": role, "content": content})

    # 尾部原样保留
    compressed.extend(tail)

    return CompressedTrajectory(
        project_id=project_id,
        phase_id=phase_id,
        agent_name=agent_name,
        agent_role=agent_role,
        model_used=model_used,
        status=status,
        duration_seconds=duration_seconds,
        token_usage=token_usage or {},
        original_turns=original_turns,
        compressed_turns=len(compressed),
        messages=compressed,
        timestamp=_now_iso(),
    )


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------

def save_trajectories(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    trajectories: list[CompressedTrajectory],
) -> Path:
    """将压缩 trajectory 追加到 JSONL 文件.

    文件位置: output/<project_id>/_trajectories/<phase_id>.jsonl
    """
    traj_dir = output_dir / project_id / "_trajectories"
    traj_dir.mkdir(parents=True, exist_ok=True)
    path = traj_dir / f"{phase_id}.jsonl"

    with open(path, "a", encoding="utf-8") as f:
        for t in trajectories:
            f.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")

    return path


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
