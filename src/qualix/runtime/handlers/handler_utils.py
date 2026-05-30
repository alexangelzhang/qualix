"""Shared utilities for finalize/detection handlers: async JSON write + event emission."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from qualix.json_utils import save_json
from qualix.runtime.events import EventType

if TYPE_CHECKING:
    from pathlib import Path


def async_write_json(path: Path, data: object) -> None:
    """异步落盘 JSON，不阻塞主流程，失败时记录日志."""
    from qualix.log import get_logger

    _log = get_logger(__name__)

    def _write():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_json(path, data)
        except Exception:
            _log.debug("async_write_json failed: %s", path, exc_info=True)

    threading.Thread(target=_write, daemon=True).start()


def emit_handler_event(ctx, event_type: EventType, message: str = "", **data) -> None:
    """Handler 层事件埋点（缓冲写入，失败时记录日志）."""
    try:
        from qualix.store.events import insert_event

        insert_event(
            ctx.output_dir,
            ctx.project_id,
            ctx.phase_id,
            event_type.value,
            action="finalize",
            message=message,
            data=data if data else None,
        )
    except Exception:
        from qualix.log import get_logger

        get_logger(__name__).debug(
            "emit_handler_event failed: %s/%s event=%s",
            ctx.project_id,
            ctx.phase_id,
            event_type.value,
            exc_info=True,
        )
