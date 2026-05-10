"""Guard telemetry: 结构化事件 + before/after pair 存档.

供 `RationalizationGuard` / `OvercorrectionGuard` 触发时调用，把运行时信号
持久化到 phase 的 `_internal/` 目录，供 `guard_precision_report` 聚合统计，
以及后续做 precision/recall 评估的原料。

设计要点:
- 失败静默（OSError / 其他异常只记 warning，不阻断 Judge 主流程）
- append-only（事件 jsonl），pair 按唯一 ts+nonce 命名避免并发冲突
- 纯无状态：internal_dir 由调用方传入
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dqg.constants import GUARD_EVENT_FILENAME, GUARD_PAIR_DIRNAME
from dqg.json_utils import save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from dqg.agents.judge_vote import JudgeVote

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _vote_snapshot(vote: JudgeVote) -> dict[str, Any]:
    """提取 JudgeVote 的关键字段用于 pair 存档（避免全量 asdict 带入多余字段）."""
    return {
        "model": vote.model,
        "overall": vote.overall,
        "verdict": vote.verdict,
        "health": vote.health,
        "raw_output": vote.raw_output,
        "issues": vote.issues,
    }


def log_guard_event(
    internal_dir: Path,
    *,
    guard: str,
    event: str,
    phase: str,
    model: str,
    detected_patterns: list[str] | tuple[str, ...] = (),
    confirmed_items: list[str] | tuple[str, ...] = (),
    pair_ref: str | None = None,
) -> None:
    """Append one structured event to `_rationalization_guard.jsonl`.

    event ∈ {LAYER1_HIT, REJUDGE_PASSED, GUARD_EXHAUSTED, CLEAN_AFTER_CONFIRM}.
    失败静默。
    """
    payload: dict[str, Any] = {
        "ts": _now_iso(),
        "guard": guard,
        "event": event,
        "phase": phase,
        "model": model,
        "detected_patterns": list(detected_patterns),
        "confirmed_items": list(confirmed_items),
    }
    if pair_ref is not None:
        payload["pair_ref"] = pair_ref

    try:
        internal_dir.mkdir(parents=True, exist_ok=True)
        event_path = internal_dir / GUARD_EVENT_FILENAME
        line = json.dumps(payload, ensure_ascii=False)
        # append-only，单行 write 属于原子操作足以应对本场景并发
        with event_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        log.warning("Failed to append guard event for phase=%s", phase, exc_info=True)
    except Exception:
        log.warning("Unexpected error appending guard event for phase=%s", phase, exc_info=True)


def save_guard_pair(
    internal_dir: Path,
    *,
    guard: str,
    phase: str,
    model: str,
    before_vote: JudgeVote,
    after_vote: JudgeVote,
    terminal_state: str,
    detected_patterns: list[str] | tuple[str, ...] = (),
    confirmed_items: list[str] | tuple[str, ...] = (),
) -> str | None:
    """Save one before/after pair to `_rationalization_pairs/` directory.

    terminal_state ∈ {REJUDGE_PASSED, GUARD_EXHAUSTED}.
    Returns relative pair_ref (e.g. `_rationalization_pairs/20260510T...json`)
    or None on failure.
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    nonce = secrets.token_hex(3)
    fname = f"{ts}_{guard[:3]}_{nonce}.json"
    rel_ref = f"{GUARD_PAIR_DIRNAME}/{fname}"

    payload = {
        "ts": _now_iso(),
        "guard": guard,
        "phase": phase,
        "model": model,
        "terminal_state": terminal_state,
        "detected_patterns": list(detected_patterns),
        "confirmed_items": list(confirmed_items),
        "before": _vote_snapshot(before_vote),
        "after": _vote_snapshot(after_vote),
    }

    try:
        pair_dir = internal_dir / GUARD_PAIR_DIRNAME
        pair_dir.mkdir(parents=True, exist_ok=True)
        save_json(pair_dir / fname, payload)
        return rel_ref
    except OSError:
        log.warning("Failed to save guard pair for phase=%s", phase, exc_info=True)
        return None
    except Exception:
        log.warning("Unexpected error saving guard pair for phase=%s", phase, exc_info=True)
        return None


__all__ = ["log_guard_event", "save_guard_pair"]
