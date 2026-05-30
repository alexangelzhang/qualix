"""统一 SQLite 存储层 — Facade.

将 telemetry、preference、failure-library、metrics 等 JSONL 数据
迁移到单个 SQLite 数据库，支持查询和聚合。

数据库位置: output/.qualix/store.db

实际实现已拆分到 store.core / store.telemetry / store.preferences /
store.bug_cases / store.metrics / store.judge / store.experiments /
store.dashboard 子模块。本文件 re-export 所有公开 API，保持向后兼容。
"""

from __future__ import annotations

from pathlib import Path

# --- bug cases ---
from qualix.store.bug_cases import (
    query_bug_cases,
    upsert_bug_case,
)

# --- core ---
from qualix.store.core import get_connection
from qualix.store.core import row_to_dict as _row_to_dict

# --- dashboard ---
from qualix.store.dashboard import (
    get_all_projects,
    get_event_timeline,
    get_phase_durations,
    get_phase_scores,
    get_project_summary,
    get_quality_trend,
    get_token_consumption,
)

# --- events ---
from qualix.store.events import (
    get_phase_timeline,
    insert_event,
    query_events,
)

# --- experiments ---
from qualix.store.experiments import (
    get_experiment_summary,
    insert_experiment,
    query_experiments,
    update_experiment,
)

# --- judge ---
from qualix.store.judge import insert_judge_result

# --- metrics ---
from qualix.store.metrics import (
    insert_metric,
    query_metrics,
)

# --- observability ---
from qualix.store.observability import (
    get_latest_observe_alerts,
    insert_observe_alerts,
    query_observe_alerts,
)

# --- preferences ---
from qualix.store.preferences import (
    insert_preference,
    migrate_preference_jsonl,
    query_preferences,
)

# --- prompt versions (P2) ---
from qualix.store.prompt_versions import (
    query_prompt_versions,
    record_prompt_snapshot,
)

# --- telemetry ---
from qualix.store.telemetry import (
    insert_telemetry,
    migrate_telemetry_jsonl,
    query_telemetry,
)

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
