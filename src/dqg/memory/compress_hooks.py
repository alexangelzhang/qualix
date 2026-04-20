"""Memory on_pre_compress 钩子：压缩前提取关键中间状态.

当 adaptive loop 压缩 context 时，可能丢失重要的中间发现。
此钩子在压缩前提取关键信息到持久化存储，防止信息丢失。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)


def on_pre_compress(
    messages: list[dict[str, Any]],
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """压缩前钩子：提取即将被丢弃的关键中间状态.

    Returns:
        提取的状态摘要
    """
    extracted = {
        "fixed_issues": [],
        "confirmed_decisions": [],
        "key_findings": [],
        "iteration_scores": [],
    }

    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # 提取已修复的问题（防止下一轮 Judge 重复指出）
        for match in re.finditer(r"(?:已修复|已修正|fixed|resolved)[:：]\s*(.+?)(?:\n|$)", content, re.IGNORECASE):
            extracted["fixed_issues"].append(match.group(1).strip()[:100])

        # 提取已确认的决策
        for match in re.finditer(r"(?:确认|决定|approved|confirmed)[:：]\s*(.+?)(?:\n|$)", content, re.IGNORECASE):
            extracted["confirmed_decisions"].append(match.group(1).strip()[:100])

        # 提取 Judge 评分
        for match in re.finditer(r"(?:score|评分|overall)[:：]\s*([\d.]+)", content, re.IGNORECASE):
            try:
                extracted["iteration_scores"].append(float(match.group(1)))
            except ValueError:
                pass

        # 提取关键发现（BLOCKER/CRITICAL）
        for match in re.finditer(r"\[(?:BLOCKER|CRITICAL)\]\s*(.+?)(?:\n|$)", content):
            extracted["key_findings"].append(match.group(1).strip()[:100])

    # 去重
    extracted["fixed_issues"] = list(dict.fromkeys(extracted["fixed_issues"]))
    extracted["confirmed_decisions"] = list(dict.fromkeys(extracted["confirmed_decisions"]))
    extracted["key_findings"] = list(dict.fromkeys(extracted["key_findings"]))

    # 持久化
    if any(v for v in extracted.values()):
        _save_compress_state(output_dir, project_id, phase_id, extracted)
        log.info(
            "Pre-compress: extracted %d fixed issues, %d decisions, %d findings",
            len(extracted["fixed_issues"]),
            len(extracted["confirmed_decisions"]),
            len(extracted["key_findings"]),
        )

    return extracted


def get_compress_state(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """获取上次压缩时提取的状态（供下一轮注入）."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    state_path = output_dir / project_id / dir_suffix / "_internal" / "_compress_state.json"
    return load_json(state_path)


def _save_compress_state(
    output_dir: Path, project_id: str, phase_id: str, state: dict[str, Any],
) -> None:
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    state_path = int_dir / "_compress_state.json"

    # 合并已有状态（增量追加）
    existing = load_json(state_path) or {}
    for key in ("fixed_issues", "confirmed_decisions", "key_findings", "iteration_scores"):
        merged = list(dict.fromkeys((existing.get(key, []) + state.get(key, []))))
        state[key] = merged[-20:]  # 保留最近 20 条

    save_json(state_path, state)
