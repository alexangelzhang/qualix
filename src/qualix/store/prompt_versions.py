"""P2: Prompt 版本库 — SQLite 存储 prompt 文本快照与递增版本号."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.log import get_logger
from qualix.store.core import get_connection, row_to_dict

log = get_logger(__name__)


def _enabled() -> bool:
    return os.environ.get("DQG_PROMPT_VERSION_STORE", "1").strip().lower() not in ("0", "false", "no")


def record_prompt_snapshot(
    output_dir: Path,
    *,
    prompt_hash: str,
    prompt_text: str,
    agent_name: str = "",
    agent_role: str = "",
    trace_run_id: str = "",
) -> int | None:
    """若 `prompt_hash`+正文未出现过则插入新版本。返回 version 或 None（跳过/关闭）."""
    if not _enabled() or not prompt_hash or not prompt_text.strip():
        return None
    content_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:32]
    try:
        with get_connection(output_dir) as conn:
            hit = conn.execute(
                "SELECT 1 FROM prompt_versions WHERE prompt_hash = ? AND content_hash = ? LIMIT 1",
                (prompt_hash, content_hash),
            ).fetchone()
            if hit:
                return None
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM prompt_versions WHERE prompt_hash = ?",
                (prompt_hash,),
            ).fetchone()
            ver = int(row[0]) + 1
            conn.execute(
                """INSERT INTO prompt_versions
                (prompt_hash, content_hash, version, agent_name, agent_role, trace_run_id, prompt_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    prompt_hash,
                    content_hash,
                    ver,
                    agent_name or "",
                    agent_role or "",
                    trace_run_id or "",
                    prompt_text,
                    datetime.now().isoformat(),
                ),
            )
        return ver
    except Exception:
        log.debug("prompt_versions record failed", exc_info=True)
        return None


def query_prompt_versions(
    output_dir: Path,
    *,
    prompt_hash: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """按时间倒序列出 prompt 版本（默认截断长文本预览）。"""
    with get_connection(output_dir) as conn:
        if prompt_hash:
            rows = conn.execute(
                """SELECT id, prompt_hash, content_hash, version, agent_name, agent_role,
                          trace_run_id, substr(prompt_text,1,500) AS prompt_preview, created_at
                   FROM prompt_versions WHERE prompt_hash = ?
                   ORDER BY version DESC LIMIT ?""",
                (prompt_hash, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, prompt_hash, content_hash, version, agent_name, agent_role,
                          trace_run_id, substr(prompt_text,1,500) AS prompt_preview, created_at
                   FROM prompt_versions ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [row_to_dict(r) for r in rows]
