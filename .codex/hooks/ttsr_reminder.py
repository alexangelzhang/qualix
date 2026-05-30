#!/usr/bin/env python3
"""PostToolUse hook: Time-Traveling Stream Rules — 高频违规迹象检测 + context 注入.

灵感来自 oh-my-pi 的 TTSR 机制：规则不预埋 system prompt，只在检测到违规迹象时
作为 reminder 注入 context。零 context tax，按需触发。

检测两类高频铁律违规（来自 failure-library 3460 条案例统计）：
  1. SE-based 模式：Q05a/Q05b/Q06 产物中按 SE 汇总而非 EUT 逐条
  2. 缺 --json：qualix-run 输出包含 prose 结构而非 JSON（忘加 --json）
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from hook_utils import decision_warn, get_tool_input, get_tool_name, read_stdin

# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------

# SE-based 模式的特征：输出里出现 "SE-\d+" 作为 eut_id，或 audit_items 按 SE 分组
_SE_BASED_PATTERNS = [
    re.compile(r'"eut_id"\s*:\s*"SE-\d+"'),          # eut_id 直接用 SE 编号
    re.compile(r'"audit_items".*?"se_id".*?"count"', re.DOTALL),  # 按 SE 聚合计数
    re.compile(r'SE-\d+.*?覆盖.*?(?:个|条|项)\s*EUT', re.DOTALL),  # prose：N个EUT对应SE
]

# 缺 --json 的特征：Bash 执行了 qualix-run 但输出是人类可读格式（不是 JSON 对象/数组）
_QUALIX_RUN_RE = re.compile(r'qualix[-_]run\s+\S+\s+\S+')
_JSON_START_RE = re.compile(r'^\s*[\[{]')
_PROSE_QUALIX_PATTERNS = [
    re.compile(r'(?:状态|Phase|phase)\s*[:：]\s*(?:not_started|in_progress|completed)', re.IGNORECASE),
    re.compile(r'✅|❌|⏭️|📋'),  # emoji 是 prose 输出的强特征
    re.compile(r'^\s*=+\s*$', re.MULTILINE),  # 分割线
]


def _detect_se_based(output: str) -> bool:
    return any(p.search(output) for p in _SE_BASED_PATTERNS)


def _detect_missing_json_flag(tool_name: str, tool_input: dict, output: str) -> bool:
    if tool_name not in ("Bash",):
        return False
    command = tool_input.get("command", "")
    if not _QUALIX_RUN_RE.search(command):
        return False
    # 有 --json 就不提醒
    if "--json" in command:
        return False
    # 检查输出是否是 prose（有非 JSON 结构的 qualix 输出）
    if _JSON_START_RE.match(output):
        return False
    return any(p.search(output) for p in _PROSE_QUALIX_PATTERNS)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def main():
    raw = read_stdin()
    tool_name = get_tool_name(raw)
    tool_input = get_tool_input(raw)

    # 取工具输出
    output = ""
    if isinstance(raw, dict):
        result = raw.get("toolUseResult", raw.get("output", ""))
        if isinstance(result, str):
            output = result
        elif isinstance(result, dict):
            output = result.get("output", result.get("content", ""))
            if isinstance(output, list):
                output = " ".join(
                    p.get("text", "") for p in output if isinstance(p, dict)
                )

    reminders: list[str] = []

    if _detect_se_based(output):
        reminders.append(
            "【TTSR-铁律2】检测到 SE-based 模式迹象。"
            "Q05a/Q05b/Q06 MUST 每条 audit_item 独立对应一个 eut_id，"
            "NEVER 用 SE 编号作为 eut_id，NEVER 按 SE 汇总。"
            "当前输出可能违反此铁律，请检查并修正。"
        )

    if _detect_missing_json_flag(tool_name, tool_input, output):
        reminders.append(
            "【TTSR-铁律3】qualix-run 输出疑似 prose 格式。"
            "所有 qualix-run 调用 MUST 加 --json 标志，让输出可被稳定解析。"
            "请在命令末尾补加 --json 后重试。"
        )

    if reminders:
        decision_warn("\n".join(reminders))
    else:
        # 无违规，放行（不输出任何内容）
        sys.exit(0)


if __name__ == "__main__":
    main()
