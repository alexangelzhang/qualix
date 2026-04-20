"""Events store: 全链路事件持久化.

采用内存缓冲 + 批量写入策略，避免频繁 SQLite I/O 影响主流程性能。
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.store.core import get_connection

# ---------------------------------------------------------------------------
# 内存缓冲：事件先写入 buffer，批量 flush 到 SQLite
# ---------------------------------------------------------------------------

_buffer: list[tuple] = []
_buffer_lock = threading.Lock()
_FLUSH_THRESHOLD = 20  # 缓冲满 20 条自动 flush


def insert_event(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    event_type: str,
    *,
    action: str = "",
    message: str = "",
    data: dict[str, Any] | None = None,
    duration_ms: int = 0,
    timestamp: str | None = None,
) -> None:
    """缓冲一条事件记录。达到阈值时自动 flush。"""
    ts = timestamp or datetime.now().isoformat()
    data_json = dump_json_str(data or {}, indent=None)
    row = (project_id, phase_id, event_type, action, message, data_json, duration_ms, ts)

    with _buffer_lock:
        _buffer.append((output_dir, row))
        if len(_buffer) >= _FLUSH_THRESHOLD:
            _flush_buffer_locked()


def flush_events() -> int:
    """手动 flush 缓冲区，返回写入条数。供 finalize/approve 结束时调用。"""
    with _buffer_lock:
        return _flush_buffer_locked()


def _flush_buffer_locked() -> int:
    """在持有锁的情况下批量写入（内部方法）。"""
    global _buffer
    if not _buffer:
        return 0

    # 按 output_dir 分组批量写入
    groups: dict[str, list[tuple]] = {}
    for output_dir, row in _buffer:
        key = str(output_dir)
        groups.setdefault(key, []).append(row)

    written = 0
    for dir_str, rows in groups.items():
        try:
            with get_connection(Path(dir_str)) as conn:
                conn.executemany(
                    """INSERT INTO events
                    (project_id, phase_id, event_type, action, message, data_json, duration_ms, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                written += len(rows)
        except Exception:
            pass  # 静默失败不阻断主流程

    _buffer = []
    return written


def query_events(
    output_dir: Path,
    *,
    project_id: str | None = None,
    phase_id: str | None = None,
    event_type: str | None = None,
    action: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """查询事件记录."""
    clauses: list[str] = []
    params: list[Any] = []
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if phase_id:
        clauses.append("phase_id = ?")
        params.append(phase_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if action:
        clauses.append("action = ?")
        params.append(action)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_phase_timeline(
    output_dir: Path,
    project_id: str,
    phase_id: str | None = None,
) -> list[dict[str, Any]]:
    """获取 phase 执行时间线（按时间正序），用于瀑布图."""
    clauses = ["project_id = ?"]
    params: list[Any] = [project_id]
    if phase_id:
        clauses.append("phase_id = ?")
        params.append(phase_id)

    where = f"WHERE {' AND '.join(clauses)}"
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM events {where} ORDER BY id ASC",  # noqa: S608
            params,
        ).fetchall()
        return [dict(r) for r in rows]
