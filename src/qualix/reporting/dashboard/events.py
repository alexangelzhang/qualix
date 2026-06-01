"""Dashboard 事件追踪页 + Bug 案例库页."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from qualix.tracking.bug_cases import load_cases

from .cache import _cached_event_timeline, _cached_projects

# ---------------------------------------------------------------------------
# 事件追踪页
# ---------------------------------------------------------------------------


def _page_events():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    phase_filter = st.selectbox("Phase", ["全部", "Q01", "Q02", "Q03", "Q04", "Q05a", "Q05b", "Q06", "Q07"])
    phase_id = None if phase_filter == "全部" else phase_filter

    events = _cached_event_timeline(pid, phase_id)
    if not events:
        st.info("暂无事件数据。事件在 Phase 执行时自动记录。")
        return

    st.subheader(f"事件时间线 ({len(events)} 条)")

    # 事件类型分布
    df = pd.DataFrame(events)
    if "event_type" in df.columns:
        type_counts = df["event_type"].value_counts().reset_index()
        type_counts.columns = ["事件类型", "数量"]
        col1, col2 = st.columns([1, 2])
        with col1:
            st.dataframe(type_counts, hide_index=True, width="stretch")
        with col2:
            st.bar_chart(type_counts, x="事件类型", y="数量")

    # 事件明细
    st.subheader("事件明细")
    display_cols = ["phase_id", "event_type", "action", "message", "timestamp"]
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Bug 案例库页
# ---------------------------------------------------------------------------


def _page_bug_cases():
    cases = load_cases()
    if not cases:
        st.info("暂无 bug 案例")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        phase_filter = st.selectbox("Phase", ["全部", "Q01", "Q04", "Q03", "Q06"])
    with col2:
        status_filter = st.selectbox("状态", ["全部", "open", "fixed"])
    with col3:
        type_filter = st.selectbox("类型", ["全部", "FN", "FP", "WRONG"])

    filtered = cases
    if phase_filter != "全部":
        filtered = [c for c in filtered if c.get("phase") == phase_filter]
    if status_filter != "全部":
        filtered = [c for c in filtered if c.get("status") == status_filter]
    if type_filter != "全部":
        filtered = [c for c in filtered if c.get("error_type") == type_filter]

    st.caption(f"共 {len(filtered)} 条")
    if filtered:
        rows = []
        for c in filtered:
            rows.append(
                {
                    "Case ID": c.get("case_id", ""),
                    "Phase": c.get("phase", ""),
                    "类型": {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(c.get("error_type", ""), ""),
                    "严重度": c.get("severity", ""),
                    "标题": c.get("title", "")[:60],
                    "归因": c.get("root_cause", ""),
                    "状态": c.get("status", ""),
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
