"""Phase skill progressive disclosure：主骨架 + 按需加载详细 rubric/规则/案例.

减少 adaptive loop 多轮重试时的 token 消耗。
主 skill 文件只包含执行流程骨架，详细的 rubric、规则、案例按需加载。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=32)
def _read_skill_file(path_str: str) -> str:
    """缓存 skill 文件读取，同一路径不重复读。"""
    path = Path(path_str)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# Skill 文件中的按需加载标记格式：
# <!-- @include: path/to/detail.md -->
# <!-- @include-if-phase: C: path/to/detail.md -->
_INCLUDE_PATTERN = re.compile(r"<!--\s*@include(?:-if-phase:\s*(\S+))?\s*:\s*(.+?)\s*-->")


def resolve_skill_includes(
    skill_content: str,
    skill_dir: Path,
    phase_id: str | None = None,
    max_depth: int = 2,
) -> str:
    """解析 skill 文件中的 @include 标记，按需加载详细内容.

    Args:
        skill_content: skill 文件原始内容
        skill_dir: skill 文件所在目录（用于解析相对路径）
        phase_id: 当前 Phase ID（用于条件加载）
        max_depth: 最大递归深度（防止循环引用）

    Returns:
        展开后的 skill 内容
    """
    if max_depth <= 0:
        return skill_content

    def _replace_include(match: re.Match) -> str:
        condition_phase = match.group(1)
        include_path = match.group(2).strip()

        # 条件加载：只在指定 Phase 时展开
        if condition_phase and phase_id and condition_phase != phase_id:
            return ""  # 不匹配的 Phase，移除标记

        # 解析路径
        full_path = (skill_dir / include_path).resolve()
        if not full_path.exists():
            log.warning("Skill include not found: %s", full_path)
            return f"<!-- include not found: {include_path} -->"

        try:
            content = full_path.read_text(encoding="utf-8").strip()
            # 递归解析嵌套 include
            content = resolve_skill_includes(
                content,
                full_path.parent,
                phase_id,
                max_depth - 1,
            )
            return content
        except OSError as exc:
            log.warning("Failed to read skill include %s: %s", full_path, exc)
            return f"<!-- include error: {include_path} -->"

    return _INCLUDE_PATTERN.sub(_replace_include, skill_content)


def load_skill_progressive(
    skill_path: Path,
    phase_id: str | None = None,
) -> str:
    """加载 skill 文件，支持 progressive disclosure.

    如果 skill 文件包含 @include 标记，按需展开详细内容。
    如果没有标记，返回原始内容（向后兼容）。

    Args:
        skill_path: skill 文件路径
        phase_id: 当前 Phase ID

    Returns:
        展开后的 skill 内容
    """
    if not skill_path.exists():
        return ""

    content = _read_skill_file(str(skill_path.resolve()))

    # 检查是否有 include 标记
    if "<!-- @include" not in content:
        return content  # 无标记，原样返回

    return resolve_skill_includes(content, skill_path.parent, phase_id)


def resolve_worker_prompt(phase: str, skill_override: str | None = None) -> str:
    """Unified skill resolution for ALL execution paths.

    Consolidates cmd_agent_run, cmd_adaptive, dag_scheduler, and replay_executor.
    All paths go through load_skill_progressive() to ensure prompt equivalence.

    Args:
        phase: Phase identifier (e.g., "Q01", "Q05a", "Q06")
        skill_override: Optional path to override skill file

    Returns:
        Resolved skill content string
    """
    from qualix.core.phase_registry import PHASE_DEFS

    skill_path = Path(PHASE_DEFS[phase]["skill"])

    if skill_override:
        skill_path = Path(skill_override)

    body = load_skill_progressive(skill_path, phase)
    from qualix.context.enum_contract import render_enum_contract_prefix

    prefix = render_enum_contract_prefix(phase)
    if prefix:
        return f"{prefix}\n---\n\n{body}"
    return body


def estimate_skill_token_savings(
    skill_path: Path,
    phase_id: str,
) -> dict[str, Any]:
    """估算 progressive disclosure 的 token 节省量.

    Returns:
        {"original_chars": N, "resolved_chars": M, "savings_pct": float}
    """
    if not skill_path.exists():
        return {}

    original = skill_path.read_text(encoding="utf-8")
    resolved = load_skill_progressive(skill_path, phase_id)

    original_chars = len(original)
    resolved_chars = len(resolved)

    return {
        "original_chars": original_chars,
        "resolved_chars": resolved_chars,
        "savings_pct": 1.0 - (resolved_chars / max(original_chars, 1)),
    }
