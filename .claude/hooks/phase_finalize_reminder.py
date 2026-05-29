#!/usr/bin/env python3
"""PostToolUse hook: Phase 执行完成后，检测未 finalize 状态并注入提醒.

触发条件：Bash 工具调用，命令包含 "dqg-run" 且包含 "execute"。
检测逻辑：
  1. 从命令中提取 project_id 和 phase_id
  2. 读取 state.json，确认该 Phase 处于 in_progress（execute 完成但未 finalize）
  3. 注入提醒："Phase 执行完成，请运行 finalize"

fail-open：任何异常静默退出 0，不阻断正常工作流。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from hook_utils import inject, read_stdin

# DQG output 目录相对项目根目录的路径（按 phase_service.py 约定）
_OUTPUT_SUBDIR = "output"


def _find_project_root() -> Path | None:
    """从当前目录向上找到含 pyproject.toml 或 dqg_starter.md 的 DQG 项目根目录。"""
    cwd = Path(os.getcwd())
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "dqg_starter.md").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _parse_execute_command(cmd: str) -> tuple[str, str] | None:
    """从 dqg-run <pid> execute <phase> 中提取 (project_id, phase_id)。

    支持格式：
      dqg-run <pid> execute <phase>
      dqg-run <pid> execute <phase> [options...]
    返回 None 表示解析失败或不是 execute 命令。
    """
    # 匹配 dqg-run 后跟 project_id，再跟 execute，再跟 phase_id
    m = re.search(r"dqg-run\s+(\S+)\s+execute\s+(\S+)", cmd)
    if not m:
        return None
    project_id = m.group(1)
    phase_id = m.group(2)
    # 排除 --help、-h 等选项作为 phase_id
    if phase_id.startswith("-"):
        return None
    return project_id, phase_id


def _read_phase_status(project_root: Path, project_id: str, phase_id: str) -> str | None:
    """读取 state.json 中指定 Phase 的状态，返回 status 字符串或 None。"""
    state_path = project_root / _OUTPUT_SUBDIR / project_id / "state.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        phases = data.get("phases", {})
        phase_data = phases.get(phase_id, {})
        return phase_data.get("status")
    except Exception:
        return None


def main() -> None:
    data = read_stdin()
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    # 只关心 execute 命令
    tool_input = data.get("tool_input", {})
    cmd = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if "dqg-run" not in cmd or "execute" not in cmd:
        sys.exit(0)

    parsed = _parse_execute_command(cmd)
    if not parsed:
        sys.exit(0)

    project_id, phase_id = parsed

    project_root = _find_project_root()
    if not project_root:
        sys.exit(0)

    status = _read_phase_status(project_root, project_id, phase_id)

    # 只在 in_progress 状态时注入提醒（execute 已完成但未 finalize）
    if status == "in_progress":
        inject(
            f"[Phase Finalize 提醒] {phase_id} 已执行完成，当前状态 in_progress。\n"
            f"请运行 `dqg-run {project_id} finalize {phase_id} --json` 提交 Phase 产物。\n"
            "finalize 是收尾四步的必选项，不调用 finalize 则 Phase 不算完成。"
        )

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
