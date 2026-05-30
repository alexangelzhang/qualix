#!/usr/bin/env python3
"""Shared utilities for CC hook scripts.

Python port of the ar-hook-utils.cjs pattern from autoresearch.
All functions fail-open: hooks should never block legitimate work due to errors.

Usage in a hook script:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from hook_utils import read_stdin, is_enabled, block, inject, allow
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Core I/O
# ---------------------------------------------------------------------------


def read_stdin() -> dict:
    """Fail-open JSON parse from stdin. Returns empty dict on any error."""
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return {}


def block(reason: str) -> None:
    """Block current tool call with reason message. Exits 2."""
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def inject(text: str) -> None:
    """Inject text as additionalContext into Claude's conversation. Exits 0."""
    sys.stdout.write(json.dumps({"additionalContext": text}))
    sys.exit(0)


def allow() -> None:
    """Allow current tool call without injection. Exits 0."""
    sys.exit(0)


def decision_block(reason: str) -> None:
    """Block via PreToolUse/PostToolUse decision JSON API. Exits 0.

    Use this instead of block() for PreToolUse/PostToolUse hooks — CC reads the
    JSON {"decision":"block","reason":"..."} from stdout to display the reason.
    """
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def decision_warn(reason: str) -> None:
    """Inject warning via PostToolUse decision JSON without blocking. Exits 0.

    Outputs {"decision":"approve","reason":"..."} so CC shows the reason to
    Claude without blocking the tool call.
    """
    sys.stdout.write(json.dumps({"decision": "approve", "reason": reason}))
    sys.exit(0)


# ---------------------------------------------------------------------------
# Hook enable/disable
# ---------------------------------------------------------------------------


def is_enabled(hook_name: str) -> bool:
    """Check CC_DISABLE_{HOOK_NAME}=1 env var. Defaults to enabled."""
    key = "CC_DISABLE_" + hook_name.upper().replace("-", "_")
    return os.environ.get(key, "") != "1"


# ---------------------------------------------------------------------------
# Event data helpers
# ---------------------------------------------------------------------------


def get_tool_name(data: dict) -> str:
    return data.get("tool_name", "")


def get_tool_input(data: dict) -> dict:
    ti = data.get("tool_input", {})
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except Exception:
            return {}
    return ti if isinstance(ti, dict) else {}


def get_bash_command(data: dict) -> str:
    return get_tool_input(data).get("command", "")


def get_prompt(data: dict) -> str:
    return data.get("prompt", "")


def get_session_id(data: dict) -> str:
    return data.get("session_id", "")


# ---------------------------------------------------------------------------
# Session state (per cwd+session, stored in /tmp)
# ---------------------------------------------------------------------------


def _state_path(data: dict) -> Path:
    sid = get_session_id(data)
    cwd = os.getcwd()
    h = hashlib.md5(f"{cwd}:{sid}".encode()).hexdigest()[:12]
    return Path(f"/tmp/cc-session-{h}.json")


def load_session_state(data: dict) -> dict:
    """Load per-session state dict. Returns empty dict if not found."""
    try:
        return json.loads(_state_path(data).read_text())
    except Exception:
        return {}


def save_session_state(data: dict, state: dict) -> None:
    """Persist per-session state dict. Fails silently."""
    from contextlib import suppress

    with suppress(Exception):
        _state_path(data).write_text(json.dumps(state))


def increment_counter(data: dict, field: str) -> int:
    """Increment a named counter in session state, return new value."""
    state = load_session_state(data)
    state[field] = state.get(field, 0) + 1
    save_session_state(data, state)
    return state[field]
