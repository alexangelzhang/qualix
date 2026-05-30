#!/usr/bin/env python3
"""PreToolUse hook: 铁律守卫 — 7 个历史错误模式的静态检测.

规则引擎架构：每个规则定义 matchers（匹配工具名）和 check 函数。
匹配所有工具调用，内部按规则过滤。

Per-session state: /tmp/claude_ironlaw_{ppid}.json
"""

import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
from hook_utils import decision_block, get_tool_input, get_tool_name, read_stdin

# ---------------------------------------------------------------------------
# YAML rule registry (lazy-loaded)
# ---------------------------------------------------------------------------

_RULE_META: dict[str, dict] = {}  # rule_id → {why, enabled, opt_out}
_RULE_META_LOADED = False


def _load_rule_meta() -> dict[str, dict]:
    global _RULE_META, _RULE_META_LOADED
    if _RULE_META_LOADED:
        return _RULE_META
    _RULE_META_LOADED = True
    yaml_path = os.path.join(os.path.dirname(__file__), "ironlaw_rules.yaml")
    if not os.path.exists(yaml_path):
        return _RULE_META
    try:
        # 轻量 YAML 解析（无依赖）：解析 rules 列表的 id/why/enabled/opt_out/matchers
        with open(yaml_path) as _f:
            text = _f.read()
        current: dict = {}
        in_matchers = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- id:"):
                if current.get("id"):
                    _RULE_META[current["id"]] = current
                current = {"id": stripped[5:].strip().strip("'\"")}
                in_matchers = False
            elif stripped.startswith("why:") and current:
                current["why"] = stripped[4:].strip().strip("'\"")
                in_matchers = False
            elif stripped.startswith("enabled:") and current:
                current["enabled"] = "false" not in stripped.lower()
                in_matchers = False
            elif stripped.startswith("opt_out:") and current:
                current["opt_out"] = "true" in stripped.lower()
                in_matchers = False
            elif stripped.startswith("matchers:") and current:
                # 支持单行 matchers: ["A", "B"] 和多行列表两种格式
                inline = stripped[9:].strip()
                if inline.startswith("["):
                    items = [
                        s.strip().strip("'\"[]") for s in inline.strip("[]").split(",") if s.strip().strip("'\"[]")
                    ]
                    current["matchers"] = items
                    in_matchers = False
                else:
                    current["matchers"] = []
                    in_matchers = True
            elif in_matchers and stripped.startswith("- ") and current:
                current.setdefault("matchers", []).append(stripped[2:].strip().strip("'\""))
            elif stripped and not stripped.startswith("#"):
                in_matchers = False
        if current.get("id"):
            _RULE_META[current["id"]] = current
    except Exception:
        pass
    return _RULE_META


def _project_disabled_rules() -> set[str]:
    """读取 CWD/.dqg/ironlaw_overrides.yaml 的 disable 列表."""
    cwd = os.getcwd()
    override_path = os.path.join(cwd, ".dqg", "ironlaw_overrides.yaml")
    if not os.path.exists(override_path):
        return set()
    try:
        disabled: set[str] = set()
        in_disable = False
        with open(override_path) as _of:
            for line in _of:
                stripped = line.strip()
                if stripped == "disable:":
                    in_disable = True
                elif in_disable and stripped.startswith("- "):
                    disabled.add(stripped[2:].split("#")[0].strip())
                elif stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                    in_disable = False
        return disabled
    except Exception:
        return set()


def _is_rule_disabled(rule_id: str) -> bool:
    """检查规则是否被 YAML 或项目级 override 禁用。"""
    meta = _load_rule_meta()
    rule = meta.get(rule_id, {})
    if not rule.get("enabled", True):
        return True
    # opt_out: false 的规则不允许项目级禁用
    if not rule.get("opt_out", True):
        return False
    return rule_id in _project_disabled_rules()


def _enrich_reason(rule_id: str, base_reason: str) -> str:
    """在 hook 输出的 reason 末尾附 why（来自 YAML 注册表）。"""
    meta = _load_rule_meta()
    why = meta.get(rule_id, {}).get("why", "")
    if why and why not in base_reason:
        return f"{base_reason}\n\n💡 为什么有这条规则：{why}"
    return base_reason


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _state_path() -> str:
    return f"/tmp/claude_ironlaw_{os.getppid()}.json"


def _load_state() -> dict:
    path = _state_path()
    if not os.path.exists(path):
        return {"seen": {}, "created": time.time()}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"seen": {}, "created": time.time()}


def _save_state(state: dict) -> None:
    try:
        with open(_state_path(), "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def _is_dqg_project() -> bool:
    cwd = os.getcwd()
    return any(os.path.exists(os.path.join(cwd, m)) for m in ("src/qualix/", "skills/", "qualix-starter.md"))


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    decision: str  # "block" or "warn"
    reason: str


# ---------------------------------------------------------------------------
# Rule 1: truncation_params — _message/_status 不是工具参数
# ---------------------------------------------------------------------------


def check_truncation_params(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if "_message" in tool_input or "_status" in tool_input:
        bad_keys = [k for k in ("_message", "_status") if k in tool_input]
        return CheckResult(
            "block",
            f"[铁律守卫] tool_input 包含 {', '.join(bad_keys)}。\n\n"
            "这是工具输出截断时的警告字段，不是工具参数。\n"
            "请移除这些字段，只使用文档化的参数。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule 2+3: grep_over_code_index — code_index 优先
# ---------------------------------------------------------------------------

_CODE_SYMBOL_RE = [
    re.compile(r"def \w+|class \w+|import \w+"),
    re.compile(r"from\s+\w+.*import"),
    re.compile(r"\w+\.(py|java|ts|js|go|rs)"),
]


def check_grep_code_index(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if not _is_dqg_project():
        return None

    text = ""
    if tool_name == "Grep":
        text = tool_input.get("pattern", "")
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if re.search(r"\bgrep\b.*\.(py|java|ts|js)\b", cmd):
            text = cmd
    if not text:
        return None

    if any(p.search(text) for p in _CODE_SYMBOL_RE):
        return CheckResult(
            "block",
            "[铁律守卫] 搜索代码符号时应优先使用 code_index 工具。\n\n"
            "规则来源：CLAUDE.md > Code Index（强制）\n"
            "- code_index_search: 搜索符号\n"
            "- code_index_refs: 跨文件引用分析\n"
            "- code_index_lookup: 获取文件 AST 摘要\n\n"
            "code_index 不可用时再 fallback 到 Grep/Bash。\n"
            "如果 code_index MCP 未启动，请先确认后再用 Grep。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule 4: agent_dqg_manual — 手动模式不派 SubAgent 执行 Phase
# ---------------------------------------------------------------------------

_PHASE_RE = [
    re.compile(r"Phase\s+Q0[1-7]", re.IGNORECASE),
    re.compile(r"phase_id.*Q0[1-7]", re.IGNORECASE),
]
_SKILL_RE = [
    re.compile(r"skill.*流程.*执行|按.*skill.*执行|读取.*skill", re.IGNORECASE),
    re.compile(r"SKILL\.md", re.IGNORECASE),
    re.compile(r"执行 Agent|执行.*Phase", re.IGNORECASE),
]


def check_agent_dqg_manual(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if tool_name != "Agent" or not _is_dqg_project():
        return None
    prompt = tool_input.get("prompt", "")
    has_phase = any(p.search(prompt) for p in _PHASE_RE)
    has_skill = any(p.search(prompt) for p in _SKILL_RE)
    if has_phase and has_skill:
        return CheckResult(
            "block",
            "[铁律守卫] DQG 手动模式下禁止派 SubAgent 执行 Phase。\n\n"
            "规则来源：CLAUDE.md > 项目经验 + qualix-starter.md > 模式选择规则\n"
            "原因：SubAgent 有独立 context，产出质量不可控，主会话直接执行可实时验证。\n\n"
            "请在主会话直接读取 skill 文件并执行。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule 5: no_skip_hooks — 禁止 git commit --no-verify
# ---------------------------------------------------------------------------


def check_no_skip_hooks(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if tool_name != "Bash":
        return None
    cmd = tool_input.get("command", "")
    if "git commit" in cmd and "--no-verify" in cmd:
        return CheckResult(
            "block",
            "[铁律守卫] 禁止使用 --no-verify 跳过 pre-commit hook。\n\n"
            "规则来源：Ruff lint 必须全修（不分新旧）\n"
            "pre-commit hook 包含 ruff 检查，跳过会导致 lint 错误遗留。\n"
            "请先修复所有 ruff 错误再提交。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule 6: se_id_format — SE ID 必须三位数格式 (SE-001)
# ---------------------------------------------------------------------------

_SE_SHORT_RE = re.compile(r'"SE-(\d{1,2})"')
_SE_LONG_RE = re.compile(r'"SE-\d{3}"')


def check_se_id_format(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if tool_name not in ("Write", "Edit"):
        return None
    file_path = tool_input.get("file_path", "")
    if "structured" not in file_path and "phase_" not in file_path:
        return None
    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    if not content:
        return None
    short_matches = _SE_SHORT_RE.findall(content)
    has_long = _SE_LONG_RE.search(content)
    if short_matches and not has_long:
        examples = [f"SE-{m}" for m in short_matches[:3]]
        return CheckResult(
            "block",
            f"[铁律守卫] SE ID 格式不一致：检测到 {', '.join(examples)}。\n\n"
            "规则来源：CLAUDE.md > 项目经验\n"
            "SE ID 必须使用三位数格式（SE-001），否则 RSM 覆盖率计算会归零。\n"
            f"请将 {', '.join(examples)} 改为 {', '.join(f'SE-{int(m):03d}' for m in short_matches[:3])}。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule 7: q01_plain_text — Q01 应优先用 blocks.raw.json
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Rule 8: bootstrap_context_guard — 写相位产物前必须读取 _bootstrap_context.md
# ---------------------------------------------------------------------------

import re as _re

_PHASE_ARTIFACT_RE = _re.compile(r"phase_[a-z0-9]+_structured\.json$")


def check_bootstrap_context_guard(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    """C2: 写入 phase_*_structured.json 前，检查 sentinel 是否存在."""
    if tool_name != "Write":
        return None
    if not _is_dqg_project():
        return None

    file_path = tool_input.get("file_path", "")
    if not _PHASE_ARTIFACT_RE.search(file_path):
        return None

    # 找 _internal/ 目录（phase 根目录的子目录）
    import os as _os

    p = file_path
    phase_dir = _os.path.dirname(p)
    internal_dir = _os.path.join(phase_dir, "_internal")
    sentinel = _os.path.join(internal_dir, ".bootstrap_context_read")

    if not _os.path.exists(sentinel):
        context_path = (
            _os.path.join(internal_dir, "_bootstrap_context.md")
            if _os.path.isdir(internal_dir)
            else f"{internal_dir}/_bootstrap_context.md"
        )
        return CheckResult(
            "warn",
            f"[铁律守卫] Step 0.5 守卫：正在写入 {_os.path.basename(file_path)}，"
            f"但未发现 _bootstrap_context.md 已读取的证据。\n\n"
            f"规则来源：CLAUDE.md > 手动模式必须执行 Step 0.5\n"
            f"未读取 bootstrap context → 产物可能缺少 PROFILE_CONTEXT 章节、"
            f"decision_owner 字段、GAP P 级等必填内容。\n\n"
            f"请先执行：Read({context_path})\n"
            f"（读取后 sentinel 自动创建，再重新写入产物即可）",
        )
    return None


def check_q01_plain_text(tool_name: str, tool_input: dict[str, Any], state: dict) -> CheckResult | None:
    if tool_name != "Read":
        return None
    file_path = tool_input.get("file_path", "")
    if "plain_text.txt" not in file_path:
        return None
    if "phaseA" in file_path or "/Q01/" in file_path:
        return CheckResult(
            "warn",
            "[铁律守卫] Q01 应优先从 blocks.raw.json 提取表格数据。\n\n"
            "规则来源：PRD 表格必须结构化提取\n"
            "plain_text.txt 会丢失表格结构，导致需求遗漏。\n"
            "请先检查同目录下是否有 blocks.raw.json，优先使用。",
        )
    return None


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_CHECK_FNS: dict[str, Callable] = {
    "truncation_params": check_truncation_params,
    "grep_over_code_index": check_grep_code_index,
    "agent_dqg_manual": check_agent_dqg_manual,
    "no_skip_hooks": check_no_skip_hooks,
    "se_id_format": check_se_id_format,
    "q01_plain_text": check_q01_plain_text,
    "bootstrap_context_guard": check_bootstrap_context_guard,
}

# Fallback matchers（YAML 未加载时使用）
_FALLBACK_MATCHERS: dict[str, set[str]] = {
    "truncation_params": {"*"},
    "grep_over_code_index": {"Grep", "Bash"},
    "agent_dqg_manual": {"Agent"},
    "no_skip_hooks": {"Bash"},
    "se_id_format": {"Write", "Edit"},
    "q01_plain_text": {"Read"},
    "bootstrap_context_guard": {"Write"},
}


def _get_matchers(rule_id: str) -> set[str]:
    """从 YAML 读取 matchers；YAML 未配置时回退到硬编码默认值."""
    meta = _load_rule_meta()
    yaml_matchers = meta.get(rule_id, {}).get("matchers")
    if yaml_matchers:
        return set(yaml_matchers)
    return _FALLBACK_MATCHERS.get(rule_id, {"*"})


def _build_rules() -> list[tuple[str, set[str], Callable]]:
    return [(rule_id, _get_matchers(rule_id), fn) for rule_id, fn in _CHECK_FNS.items()]


RULES: list[tuple[str, set[str], Callable]] = _build_rules()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    data = read_stdin()
    if not data:
        return

    tool_name = get_tool_name(data)
    tool_input = get_tool_input(data)
    state = _load_state()

    for _name, matchers, check_fn in RULES:
        if "*" not in matchers and tool_name not in matchers:
            continue
        if _is_rule_disabled(_name):
            continue
        result = check_fn(tool_name, tool_input, state)
        if result:
            enriched = _enrich_reason(_name, result.reason)
            if result.decision == "block":
                decision_block(enriched)
            else:
                # "warn" — approve with visible reason
                print(json.dumps({"decision": result.decision, "reason": enriched}))
            return


if __name__ == "__main__":
    main()
