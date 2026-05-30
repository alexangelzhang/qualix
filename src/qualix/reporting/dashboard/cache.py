"""Dashboard 缓存层 + DB 初始化."""

from __future__ import annotations

import streamlit as st

from qualix.store import (
    get_all_projects,
    get_event_timeline,
    get_latest_observe_alerts,
    get_phase_durations,
    get_project_summary,
    get_quality_trend,
    get_token_consumption,
    migrate_all,
)

from .constants import OUTPUT_DIR

# ---------------------------------------------------------------------------
# 缓存：避免重复查询
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def _cached_projects():
    return get_all_projects(OUTPUT_DIR)


@st.cache_data(ttl=60)
def _cached_summary(pid):
    return get_project_summary(OUTPUT_DIR, pid)


@st.cache_data(ttl=60)
def _cached_token_consumption(pid):
    return get_token_consumption(OUTPUT_DIR, pid)


@st.cache_data(ttl=60)
def _cached_phase_durations(pid):
    return get_phase_durations(OUTPUT_DIR, pid)


@st.cache_data(ttl=60)
def _cached_event_timeline(pid, phase_id):
    return get_event_timeline(OUTPUT_DIR, pid, phase_id)


@st.cache_data(ttl=60)
def _cached_trend(pid, days):
    return get_quality_trend(OUTPUT_DIR, project_id=pid, days=days)


@st.cache_data(ttl=60)
def _cached_observe_alerts():
    return get_latest_observe_alerts(OUTPUT_DIR, limit=50)


def _ensure_db():
    db_path = OUTPUT_DIR / ".qualix" / "store.db"
    if not db_path.exists():
        result = migrate_all(OUTPUT_DIR)
        if sum(result.values()) > 0:
            st.toast(f"已迁移历史数据: {result}")
