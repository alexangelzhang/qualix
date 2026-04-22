"""Dashboard 可观测性页面：告警历史 + 日报摘要 + 指标趋势."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .cache import _cached_observe_alerts
from .constants import OUTPUT_DIR


def _load_observe_reports(period: str = "daily") -> list[dict]:
    """从文件系统加载 observe 报告列表."""
    import json
    report_dir = OUTPUT_DIR.parent / "observability" / "reports" / period
    if not report_dir.exists():
        return []
    reports = []
    for f in sorted(report_dir.glob("*.json"), reverse=True)[:10]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append(data)
        except Exception:
            pass
    return reports


def _page_observability():
    st.header("可观测性")

    tab_alerts, tab_reports, tab_metrics = st.tabs(["告警历史", "日报/周报", "指标趋势"])

    # --- 告警历史 ---
    with tab_alerts:
        alerts = _cached_observe_alerts()
        if not alerts:
            st.info("暂无 observe 告警。运行 `dqg observability daily` 生成。")
        else:
            df = pd.DataFrame(alerts)
            display_cols = [c for c in ["label", "severity", "rule", "project_id", "phase", "message"] if c in df.columns]
            if display_cols:
                # 按 severity 着色
                st.dataframe(
                    df[display_cols],
                    use_container_width=True,
                    hide_index=True,
                )
                # 统计
                col1, col2, col3 = st.columns(3)
                high = len([a for a in alerts if a.get("severity") == "HIGH"])
                medium = len([a for a in alerts if a.get("severity") == "MEDIUM"])
                with col1:
                    st.metric("HIGH", high)
                with col2:
                    st.metric("MEDIUM", medium)
                with col3:
                    st.metric("总计", len(alerts))

    # --- 日报/周报 ---
    with tab_reports:
        period = st.radio("周期", ["daily", "weekly"], horizontal=True)
        reports = _load_observe_reports(period)
        if not reports:
            st.info(f"暂无 {period} 报告。运行 `dqg observability report --period {period}` 生成。")
        else:
            for report in reports:
                label = report.get("label", "unknown")
                projects = report.get("projects", [])
                with st.expander(f"{label} ({len(projects)} 项目)", expanded=(report == reports[0])):
                    if projects:
                        rows = []
                        for p in projects:
                            rows.append({
                                "Project": p.get("project_id", ""),
                                "Approval Rate": f"{p.get('phase_approval_rate', 0):.0%}",
                                "Avg Duration(s)": f"{p.get('avg_duration_seconds', 0):.1f}",
                                "GAP Closure": f"{p.get('gap_closure_rate', 0):.0%}",
                                "BLOCK": p.get("block_count", 0),
                                "Finalized": p.get("finalized", 0),
                            })
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # --- 指标趋势 ---
    with tab_metrics:
        history = _load_metrics_history()
        if not history:
            st.info("暂无指标历史。运行 `dqg observability daily` 积累数据。")
        else:
            # 项目级趋势
            project_rows = [r for r in history if r.get("phase") == "ALL"]
            if project_rows:
                df = pd.DataFrame(project_rows)
                if "date" in df.columns and "approval_rate" in df.columns:
                    st.subheader("Approval Rate 趋势")
                    chart_df = df.pivot_table(index="date", columns="project_id", values="approval_rate")
                    st.line_chart(chart_df)

                if "date" in df.columns and "block_count" in df.columns:
                    st.subheader("BLOCK 数量趋势")
                    chart_df = df.pivot_table(index="date", columns="project_id", values="block_count")
                    st.line_chart(chart_df)


def _load_metrics_history() -> list[dict]:
    """加载 observe 指标历史."""
    import json
    path = OUTPUT_DIR.parent / "observability" / "metrics_history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows
