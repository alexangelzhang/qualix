"""统一 SQLite 存储层 — Facade.

将 telemetry、preference、failure-library、metrics 等 JSONL 数据
迁移到单个 SQLite 数据库，支持查询和聚合。

数据库位置: output/.dqg/store.db

实际实现已拆分到 store.core / store.telemetry / store.preferences /
store.bug_cases / store.metrics / store.judge / store.experiments /
store.dashboard 子模块。本文件 re-export 所有公开 API，保持向后兼容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# --- core ---
from dqg.store.core import get_connection  # noqa: F401
from dqg.store.core import row_to_dict as _row_to_dict  # noqa: F401

# --- telemetry ---
from dqg.store.telemetry import insert_telemetry  # noqa: F401
from dqg.store.telemetry import migrate_telemetry_jsonl  # noqa: F401
from dqg.store.telemetry import query_telemetry  # noqa: F401

# --- preferences ---
from dqg.store.preferences import insert_preference  # noqa: F401
from dqg.store.preferences import migrate_preference_jsonl  # noqa: F401
from dqg.store.preferences import query_preferences  # noqa: F401

# --- bug cases ---
from dqg.store.bug_cases import query_bug_cases  # noqa: F401
from dqg.store.bug_cases import upsert_bug_case  # noqa: F401

# --- metrics ---
from dqg.store.metrics import insert_metric  # noqa: F401
from dqg.store.metrics import query_metrics  # noqa: F401

# --- judge ---
from dqg.store.judge import insert_judge_result  # noqa: F401

# --- experiments ---
from dqg.store.experiments import get_experiment_summary  # noqa: F401
from dqg.store.experiments import insert_experiment  # noqa: F401
from dqg.store.experiments import query_experiments  # noqa: F401
from dqg.store.experiments import update_experiment  # noqa: F401

# --- events ---
from dqg.store.events import get_phase_timeline  # noqa: F401
from dqg.store.events import insert_event  # noqa: F401
from dqg.store.events import query_events  # noqa: F401

# --- observability ---
from dqg.store.observability import get_latest_observe_alerts  # noqa: F401
from dqg.store.observability import insert_observe_alerts  # noqa: F401
from dqg.store.observability import query_observe_alerts  # noqa: F401

# --- dashboard ---
from dqg.store.dashboard import get_all_projects  # noqa: F401
from dqg.store.dashboard import get_event_timeline  # noqa: F401
from dqg.store.dashboard import get_phase_durations  # noqa: F401
from dqg.store.dashboard import get_phase_scores  # noqa: F401
from dqg.store.dashboard import get_project_summary  # noqa: F401
from dqg.store.dashboard import get_quality_trend  # noqa: F401
from dqg.store.dashboard import get_token_consumption  # noqa: F401


# ---------------------------------------------------------------------------
# Migration orchestrator (stays here — it coordinates sub-modules)
# ---------------------------------------------------------------------------

def migrate_all(output_dir: Path, base_dir: Path | None = None) -> dict[str, int]:
    """一键迁移所有 JSONL 数据到 SQLite."""
    base = base_dir or output_dir.parent
    return {
        "telemetry": migrate_telemetry_jsonl(output_dir),
        "preferences": migrate_preference_jsonl(base, output_dir),
    }
