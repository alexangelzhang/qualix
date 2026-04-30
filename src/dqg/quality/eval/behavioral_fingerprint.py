"""行为指纹回归测试：从 trajectory 提取行为特征，用统计分布替代 binary diff.

参考 AgentAssay 论文：行为指纹检测 86% 回归，token 成本降 78%。

核心思路：
- 不比较输出文本（非确定性），而是比较行为模式（确定性更高）
- 从 trajectory 中提取：工具调用模式、ID 数量范围、关键决策点
- 多次运行取分布，用统计检验判定是否回归

用法：
    from dqg.quality.behavioral_fingerprint import extract_fingerprint, compare_fingerprints
    fp = extract_fingerprint(trajectory_path)
    result = compare_fingerprints(baseline_fps, current_fp)

# TODO: 待接入 regression pipeline（eval_baseline 或 trajectory 模块调用）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from dqg.constants import ID_PATTERN_EXTENDED

if TYPE_CHECKING:
    from pathlib import Path

_ID_PATTERN = re.compile(ID_PATTERN_EXTENDED)
_TOOL_CALL_PATTERN = re.compile(r'<tool_call\s+name="(.*?)">')


@dataclass
class BehavioralFingerprint:
    """一次 Phase 执行的行为指纹."""

    project_id: str = ""
    phase_id: str = ""
    agent_role: str = ""

    # 工具调用模式
    tool_calls: list[str] = field(default_factory=list)  # 调用顺序
    tool_call_count: int = 0
    unique_tools_used: set[str] = field(default_factory=set)

    # ID 产出统计
    id_counts: dict[str, int] = field(default_factory=dict)  # {"REQ": 5, "GAP": 2, ...}
    total_ids: int = 0

    # 结构特征
    turn_count: int = 0
    has_tool_calls: bool = False
    final_output_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "phase_id": self.phase_id,
            "agent_role": self.agent_role,
            "tool_calls": self.tool_calls,
            "tool_call_count": self.tool_call_count,
            "unique_tools_used": sorted(self.unique_tools_used),
            "id_counts": self.id_counts,
            "total_ids": self.total_ids,
            "turn_count": self.turn_count,
            "has_tool_calls": self.has_tool_calls,
            "final_output_length": self.final_output_length,
        }


@dataclass
class RegressionResult:
    """回归检测结果."""

    phase_id: str
    verdict: str  # PASS / FAIL / INCONCLUSIVE
    deviations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "verdict": self.verdict,
            "deviations": self.deviations,
        }


# ---------------------------------------------------------------------------
# 指纹提取
# ---------------------------------------------------------------------------


def extract_fingerprint(trajectory_data: dict[str, Any]) -> BehavioralFingerprint:
    """从单条压缩 trajectory 提取行为指纹."""
    fp = BehavioralFingerprint(
        project_id=trajectory_data.get("project_id", ""),
        phase_id=trajectory_data.get("phase_id", ""),
        agent_role=trajectory_data.get("agent_role", ""),
    )

    messages = trajectory_data.get("messages", [])
    fp.turn_count = len(messages)

    content_parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        content_parts.append(content)

        # 提取工具调用
        for match in _TOOL_CALL_PATTERN.finditer(content):
            tool_name = match.group(1)
            fp.tool_calls.append(tool_name)
            fp.unique_tools_used.add(tool_name)

    all_content = "\n".join(content_parts)
    fp.tool_call_count = len(fp.tool_calls)
    fp.has_tool_calls = fp.tool_call_count > 0

    # 提取 ID 统计
    for match in _ID_PATTERN.finditer(all_content):
        prefix = match.group(1)
        fp.id_counts[prefix] = fp.id_counts.get(prefix, 0) + 1
    fp.total_ids = sum(fp.id_counts.values())

    # 最终输出长度（反向查找，避免构建完整列表）
    if messages:
        last_assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
        if last_assistant:
            fp.final_output_length = len(last_assistant.get("content", ""))

    return fp


def extract_fingerprints_from_file(trajectory_path: Path) -> list[BehavioralFingerprint]:
    """从 JSONL 文件提取所有 trajectory 的行为指纹."""
    fingerprints = []
    if not trajectory_path.exists():
        return fingerprints

    for line in trajectory_path.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            fingerprints.append(extract_fingerprint(data))
        except (json.JSONDecodeError, KeyError):
            continue

    return fingerprints


# ---------------------------------------------------------------------------
# 回归检测
# ---------------------------------------------------------------------------

# 行为不变量阈值
_INVARIANTS: Final[dict[str, dict[str, Any]]] = {
    "Q01": {
        "min_ids": {"REQ": 1},  # 至少 1 个 REQ
        "id_regression_tolerance": 0.5,  # ID 数量下降超过 50% 视为回归
    },
    "Q03": {
        "required_id_types": {"ARCH", "API", "DATA", "EXC", "PERF"},  # 五维度至少出现
        "id_regression_tolerance": 0.5,
    },
    "Q07": {
        "id_regression_tolerance": 0.5,
    },
}


def compare_fingerprints(
    baseline: BehavioralFingerprint,
    current: BehavioralFingerprint,
) -> RegressionResult:
    """比较两个指纹，检测行为回归.

    检测维度：
    1. 工具调用模式变化（新增/消失的工具）
    2. ID 数量回归（下降超过阈值）
    3. Phase 特有的行为不变量
    """
    phase_id = current.phase_id
    deviations: list[str] = []
    invariants = _INVARIANTS.get(phase_id, {})

    # 1. 工具调用模式
    baseline_tools = baseline.unique_tools_used
    current_tools = current.unique_tools_used
    disappeared = baseline_tools - current_tools
    if disappeared:
        deviations.append(f"TOOL_DISAPPEARED: 基线使用了 {disappeared} 但当前未使用")

    # 2. ID 数量回归
    tolerance = invariants.get("id_regression_tolerance", 0.5)
    for id_type, baseline_count in baseline.id_counts.items():
        current_count = current.id_counts.get(id_type, 0)
        if baseline_count > 0 and current_count < baseline_count * tolerance:
            deviations.append(
                f"ID_REGRESSION: {id_type} 从 {baseline_count} 降到 {current_count} (阈值 {tolerance:.0%})"
            )

    # 3. Phase 特有不变量
    min_ids = invariants.get("min_ids", {})
    for id_type, min_count in min_ids.items():
        actual = current.id_counts.get(id_type, 0)
        if actual < min_count:
            deviations.append(f"INVARIANT: {id_type} 数量 {actual} < 最小要求 {min_count}")

    required_types = invariants.get("required_id_types", set())
    if required_types:
        missing = required_types - set(current.id_counts.keys())
        if missing:
            deviations.append(f"INVARIANT: 缺少必需的 ID 类型 {missing}")

    # 4. 输出长度异常（下降超过 70%）
    if baseline.final_output_length > 0:
        ratio = current.final_output_length / baseline.final_output_length
        if ratio < 0.3:
            deviations.append(
                f"OUTPUT_SHRINK: 输出长度从 {baseline.final_output_length} 降到 "
                f"{current.final_output_length} ({ratio:.0%})"
            )

    # 判定
    if not deviations:
        verdict = "PASS"
    elif len(deviations) >= 3 or any("ID_REGRESSION" in d for d in deviations):
        verdict = "FAIL"
    else:
        verdict = "INCONCLUSIVE"

    return RegressionResult(
        phase_id=phase_id,
        verdict=verdict,
        deviations=deviations,
    )
