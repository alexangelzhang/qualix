"""Agent 写入内容安全扫描.

在 append_persistent_memory 和 write_to_wiki 入口拦截，
检测 prompt injection、凭证泄露、不可见 unicode 字符。

参考 Hermes Agent 的 _scan_memory_content 模式，适配 Qualix 场景。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 威胁模式（正则 + 分类 ID）
# ---------------------------------------------------------------------------

_THREAT_PATTERNS: list[tuple[str, str]] = [
    # Prompt injection
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions", "prompt_injection"),
    (r"you\s+are\s+now\s+", "role_hijack"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don't\s+have)\s+(restrictions|limits|rules)", "bypass_restrictions"),
    # 凭证泄露
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
    (r"wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget"),
    (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)", "read_secrets"),
    # SSH / 后门
    (r"authorized_keys", "ssh_backdoor"),
    (r"\$HOME/\.ssh|~/\.ssh", "ssh_access"),
    # Qualix 特有：篡改 Phase 状态或 skill
    (r"state\.json", "state_tampering"),
    (r"PhaseStatus\.(APPROVED|SKIPPED)", "status_bypass"),
]

# 不可见 unicode 字符（用于隐藏注入指令）
_INVISIBLE_CHARS: set[str] = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM
    "\u202a",  # LTR embedding
    "\u202b",  # RTL embedding
    "\u202c",  # pop directional
    "\u202d",  # LTR override
    "\u202e",  # RTL override
}
_INVISIBLE_RE = re.compile("[" + "".join(_INVISIBLE_CHARS) + "]")


def scan_content(content: str) -> str | None:
    """扫描 Agent 写入内容，返回拦截原因或 None（安全）.

    Returns:
        None 表示内容安全，str 表示被拦截的原因。
    """
    if not content or not content.strip():
        return None

    # 1. 不可见 unicode 字符检测（单次正则扫描）
    match = _INVISIBLE_RE.search(content)
    if match:
        char = match.group()
        return f"Blocked: 内容包含不可见 unicode 字符 U+{ord(char):04X}，可能是 prompt injection 攻击。"

    # 2. 威胁模式匹配
    for pattern, threat_id in _THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return (
                f"Blocked: 内容匹配威胁模式 '{threat_id}'。"
                f"Memory/Wiki 条目会注入到后续所有 Agent 的 prompt 中，"
                f"不允许包含注入或泄露 payload。"
            )

    return None
