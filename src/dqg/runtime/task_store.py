"""Task store：长任务执行记录 + 断点恢复基础设施.

每次 adaptive/dag/agent-run 都有 task_id，记录执行过程中的事件和检查点，
支持崩溃后恢复和进度查询。

表结构：
- task_runs: 任务级记录（一次 adaptive/dag 执行 = 一个 task_run）
- task_events: 任务内事件流（每个 iteration/phase 完成 = 一个 event）
- task_checkpoints: 可恢复的检查点（包含恢复所需的完整状态快照）
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from dqg.json_utils import dump_json_str
from dqg.log import get_logger
from dqg.store import get_connection

if False:  # TYPE_CHECKING
    from pathlib import Path

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema（追加到现有 DB）
# ---------------------------------------------------------------------------

_TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    task_type TEXT NOT NULL,
    project_id TEXT NOT NULL,
    phase_id TEXT DEFAULT '',
    status TEXT DEFAULT 'running',
    config TEXT DEFAULT '{}',
    result_summary TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_taskrun_project ON task_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_taskrun_status ON task_runs(status);
CREATE INDEX IF NOT EXISTS idx_taskrun_type ON task_runs(task_type);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT DEFAULT '{}',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_runs(task_id)
);
CREATE INDEX IF NOT EXISTS idx_taskevent_task ON task_events(task_id);

CREATE TABLE IF NOT EXISTS task_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    phase_id TEXT DEFAULT '',
    iteration INTEGER DEFAULT 0,
    state_snapshot TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(task_id, checkpoint_id),
    FOREIGN KEY (task_id) REFERENCES task_runs(task_id)
);
CREATE INDEX IF NOT EXISTS idx_taskcp_task ON task_checkpoints(task_id);
"""

# Schema 初始化标记
_task_schema_initialized: set[str] = set()


def _ensure_task_schema(output_dir: Path) -> None:
    """确保 task 表已创建（幂等）."""
    db_key = str(output_dir)
    if db_key in _task_schema_initialized:
        return
    with get_connection(output_dir) as conn:
        conn.executescript(_TASK_SCHEMA)
    _task_schema_initialized.add(db_key)


# ---------------------------------------------------------------------------
# Task Run CRUD
# ---------------------------------------------------------------------------


def create_task_run(
    output_dir: Path,
    task_type: str,
    project_id: str,
    phase_id: str = "",
    config: dict[str, Any] | None = None,
) -> str:
    """创建新的 task run，返回 task_id."""
    _ensure_task_schema(output_dir)
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO task_runs (task_id, task_type, project_id, phase_id, status, config, started_at)
            VALUES (?, ?, ?, ?, 'running', ?, ?)""",
            (task_id, task_type, project_id, phase_id, dump_json_str(config or {}), now),
        )

    log.info("Task created: %s (%s) for %s/%s", task_id, task_type, project_id, phase_id)
    return task_id


def complete_task_run(
    output_dir: Path,
    task_id: str,
    status: str = "completed",
    result_summary: str = "",
    error: str = "",
) -> None:
    """标记 task run 完成."""
    _ensure_task_schema(output_dir)
    now = datetime.now().isoformat()
    with get_connection(output_dir) as conn:
        conn.execute(
            """UPDATE task_runs SET status=?, result_summary=?, error=?, finished_at=?
            WHERE task_id=?""",
            (status, result_summary, error, now, task_id),
        )


def get_task_run(output_dir: Path, task_id: str) -> dict[str, Any] | None:
    """获取 task run 详情."""
    _ensure_task_schema(output_dir)
    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT * FROM task_runs WHERE task_id=?", (task_id,),
        ).fetchone()
    return dict(row) if row else None


def list_task_runs(
    output_dir: Path,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """列出 task runs."""
    _ensure_task_schema(output_dir)
    query = "SELECT * FROM task_runs WHERE 1=1"
    params: list[Any] = []
    if project_id:
        query += " AND project_id=?"
        params.append(project_id)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Task Events
# ---------------------------------------------------------------------------


def add_task_event(
    output_dir: Path,
    task_id: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
) -> None:
    """记录 task 事件."""
    _ensure_task_schema(output_dir)
    now = datetime.now().isoformat()
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO task_events (task_id, event_type, event_data, timestamp)
            VALUES (?, ?, ?, ?)""",
            (task_id, event_type, dump_json_str(event_data or {}), now),
        )


def get_task_events(output_dir: Path, task_id: str) -> list[dict[str, Any]]:
    """获取 task 的所有事件."""
    _ensure_task_schema(output_dir)
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM task_events WHERE task_id=? ORDER BY timestamp",
            (task_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_events_slice(
    output_dir: Path,
    task_id: str,
    from_id: int | None = None,
    to_id: int | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """位置切片：获取指定范围的事件，支持回退、跳转、重读.

    支持两种切片方式（可组合）：
    - 按 event id 范围：from_id / to_id（基于自增主键，精确定位）
    - 按时间范围：from_timestamp / to_timestamp（ISO 格式）

    Args:
        from_id: 起始 event id（含），None 表示从头
        to_id: 结束 event id（含），None 表示到尾
        from_timestamp: 起始时间（含），ISO 格式
        to_timestamp: 结束时间（含），ISO 格式
        event_type: 只返回指定类型的事件
        limit: 最大返回数量
    """
    _ensure_task_schema(output_dir)
    query = "SELECT * FROM task_events WHERE task_id=?"
    params: list[Any] = [task_id]

    if from_id is not None:
        query += " AND id >= ?"
        params.append(from_id)
    if to_id is not None:
        query += " AND id <= ?"
        params.append(to_id)
    if from_timestamp:
        query += " AND timestamp >= ?"
        params.append(from_timestamp)
    if to_timestamp:
        query += " AND timestamp <= ?"
        params.append(to_timestamp)
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    query += " ORDER BY id ASC LIMIT ?"
    params.append(limit)

    with get_connection(output_dir) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def replay_from_checkpoint(
    output_dir: Path,
    task_id: str,
    checkpoint_id: str,
) -> dict[str, Any] | None:
    """从指定 checkpoint 重放：返回 checkpoint 状态 + 该 checkpoint 之后的所有事件.

    用于崩溃恢复或从任意检查点重新开始。

    Returns:
        {
            "checkpoint": {...},  # checkpoint 状态快照
            "events_after": [...],  # checkpoint 之后的事件
        }
    """
    _ensure_task_schema(output_dir)

    # 获取 checkpoint
    with get_connection(output_dir) as conn:
        cp_row = conn.execute(
            "SELECT * FROM task_checkpoints WHERE task_id=? AND checkpoint_id=?",
            (task_id, checkpoint_id),
        ).fetchone()

    if not cp_row:
        return None

    checkpoint = dict(cp_row)
    cp_timestamp = checkpoint.get("created_at", "")

    # 获取 checkpoint 之后的事件
    events_after = get_events_slice(
        output_dir, task_id,
        from_timestamp=cp_timestamp,
        limit=500,
    )

    return {
        "checkpoint": checkpoint,
        "events_after": events_after,
    }


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


def save_checkpoint(
    output_dir: Path,
    task_id: str,
    checkpoint_id: str,
    phase_id: str = "",
    iteration: int = 0,
    state_snapshot: dict[str, Any] | None = None,
) -> None:
    """保存检查点（upsert）."""
    _ensure_task_schema(output_dir)
    now = datetime.now().isoformat()
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO task_checkpoints (task_id, checkpoint_id, phase_id, iteration, state_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, checkpoint_id) DO UPDATE SET
                phase_id=excluded.phase_id, iteration=excluded.iteration,
                state_snapshot=excluded.state_snapshot, created_at=excluded.created_at""",
            (task_id, checkpoint_id, phase_id, iteration, dump_json_str(state_snapshot or {}), now),
        )


def get_latest_checkpoint(
    output_dir: Path,
    task_id: str,
) -> dict[str, Any] | None:
    """获取最新检查点."""
    _ensure_task_schema(output_dir)
    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT * FROM task_checkpoints WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def get_resumable_task(
    output_dir: Path,
    project_id: str,
    task_type: str | None = None,
) -> dict[str, Any] | None:
    """查找可恢复的 task（status=running 且有 checkpoint）."""
    _ensure_task_schema(output_dir)
    query = """
        SELECT tr.*, tc.checkpoint_id, tc.phase_id as cp_phase, tc.iteration, tc.state_snapshot
        FROM task_runs tr
        JOIN task_checkpoints tc ON tr.task_id = tc.task_id
        WHERE tr.project_id=? AND tr.status='running'
    """
    params: list[Any] = [project_id]
    if task_type:
        query += " AND tr.task_type=?"
        params.append(task_type)
    query += " ORDER BY tc.created_at DESC LIMIT 1"

    with get_connection(output_dir) as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None
