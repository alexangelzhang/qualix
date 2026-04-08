"""DQG 可视化看板.

启动: streamlit run src/dqg/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dqg.tracking.bug_cases import load_cases, summarize_cases
from dqg.store import (
    get_all_projects,
    get_connection,
    get_project_summary,
    get_quality_trend,
    migrate_all,
    query_bug_cases,
    query_telemetry,
)

OUTPUT_DIR = Path("output")


def _ensure_db():
    """确保 SQLite 数据库存在，必要时迁移."""
    db_path = OUTPUT_DIR / ".dqg" / "store.db"
    if not db_path.exists():
        result = migrate_all(OUTPUT_DIR)
        if sum(result.values()) > 0:
            st.toast(f"已迁移历史数据: {result}")


def main():
    st.set_page_config(page_title="DQG 质量看板", page_icon="🔍", layout="wide")
    st.title("DQG 研发质量门禁看板")

    _ensure_db()

    # Sidebar
    st.sidebar.header("导航")
    page = st.sidebar.radio("", ["总览", "项目详情", "Bug 案例库", "质量趋势", "数据管理"])

    if page == "总览":
        _page_overview()
    elif page == "项目详情":
        _page_project_detail()
    elif page == "Bug 案例库":
        _page_bug_cases()
    elif page == "质量趋势":
        _page_quality_trend()
    elif page == "数据管理":
        _page_data_management()


def _page_overview():
    """总览页：所有项目的状态概览."""
    projects = get_all_projects(OUTPUT_DIR)

    if not projects:
        st.info("暂无项目数据。请先执行 `dqg-run <project> execute A` 开始。")
        # 也展示文件系统中的 bug cases
        _show_bug_case_summary()
        return

    # 项目卡片
    cols = st.columns(min(len(projects), 3))
    for i, pid in enumerate(projects):
        summary = get_project_summary(OUTPUT_DIR, pid)
        with cols[i % 3]:
            st.metric(
                label=pid,
                value=f"{summary['phase_approval_rate']:.0%}",
                delta=f"{summary['total_approved']}/{summary['total_finalized']} phases",
            )
            st.caption(f"平均耗时: {summary['avg_duration_seconds']:.0f}s")
            judge_scores = summary.get("latest_judge_scores", {})
            if judge_scores:
                for phase, score in judge_scores.items():
                    st.caption(f"  Judge {phase}: {score}/10")

    st.divider()
    _show_bug_case_summary()


def _show_bug_case_summary():
    """展示 bug 案例库摘要."""
    cases = load_cases()
    if not cases:
        return

    summary = summarize_cases(cases)
    st.subheader(f"Bug 案例库 ({summary['total']} 条)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Open", summary["open"])
    with col2:
        st.metric("Fixed", summary["fixed"])
    with col3:
        st.metric("总计", summary["total"])

    # 按 Phase 分布
    phase_data = summary.get("by_phase", {})
    if phase_data:
        df = pd.DataFrame(
            [{"Phase": k, "数量": v} for k, v in sorted(phase_data.items())]
        )
        st.bar_chart(df, x="Phase", y="数量")

    # 按归因分布
    col1, col2 = st.columns(2)
    with col1:
        error_data = summary.get("by_error_type", {})
        if error_data:
            labels = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}
            df = pd.DataFrame(
                [{"类型": labels.get(k, k), "数量": v} for k, v in error_data.items()]
            )
            st.dataframe(df, hide_index=True, use_container_width=True)

    with col2:
        rc_data = summary.get("by_root_cause", {})
        if rc_data:
            df = pd.DataFrame(
                [{"归因": k, "数量": v} for k, v in rc_data.items()]
            )
            st.dataframe(df, hide_index=True, use_container_width=True)


def _page_project_detail():
    """项目详情页."""
    projects = get_all_projects(OUTPUT_DIR)
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    summary = get_project_summary(OUTPUT_DIR, pid)

    # 指标卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("通过率", f"{summary['phase_approval_rate']:.0%}")
    with col2:
        st.metric("已完成", summary["total_approved"])
    with col3:
        st.metric("已校验", summary["total_finalized"])
    with col4:
        st.metric("平均耗时", f"{summary['avg_duration_seconds']:.0f}s")

    # 执行记录
    st.subheader("执行记录")
    records = query_telemetry(OUTPUT_DIR, project_id=pid, limit=50)
    if records:
        df = pd.DataFrame(records)
        display_cols = ["phase_id", "action", "status", "duration_seconds", "timestamp"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], hide_index=True, use_container_width=True)
    else:
        st.info("暂无执行记录")


def _page_bug_cases():
    """Bug 案例库详情页."""
    cases = load_cases()
    if not cases:
        st.info("暂无 bug 案例")
        return

    # 过滤器
    col1, col2, col3 = st.columns(3)
    with col1:
        phase_filter = st.selectbox("Phase", ["全部", "A", "A.5", "A.6", "C"])
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

    # 表格展示
    if filtered:
        rows = []
        for c in filtered:
            rows.append({
                "Case ID": c.get("case_id", ""),
                "Phase": c.get("phase", ""),
                "类型": {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(c.get("error_type", ""), ""),
                "严重度": c.get("severity", ""),
                "标题": c.get("title", "")[:60],
                "归因": c.get("root_cause", ""),
                "状态": c.get("status", ""),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)


def _page_quality_trend():
    """质量趋势页."""
    projects = get_all_projects(OUTPUT_DIR)
    pid = st.selectbox("项目", ["全部"] + projects) if projects else None
    days = st.slider("时间范围（天）", 7, 90, 30)

    project_filter = pid if pid and pid != "全部" else None
    trend = get_quality_trend(OUTPUT_DIR, project_id=project_filter, days=days)

    if not trend:
        st.info("暂无趋势数据。数据会在项目执行后自动积累。")
        return

    df = pd.DataFrame(trend)
    if "day" in df.columns and "count" in df.columns:
        # 按 action 分组的每日执行量
        pivot = df.pivot_table(index="day", columns="action", values="count", fill_value=0)
        st.subheader("每日执行量")
        st.line_chart(pivot)

        # 平均耗时趋势
        if "avg_duration" in df.columns:
            duration_df = df[df["action"] == "finalize"][["day", "avg_duration"]].dropna()
            if not duration_df.empty:
                st.subheader("平均耗时趋势")
                st.line_chart(duration_df.set_index("day"))


def _page_data_management():
    """数据管理页：迁移、导出."""
    st.subheader("数据迁移")
    st.caption("将现有 JSONL 历史数据迁移到 SQLite")

    if st.button("执行迁移"):
        result = migrate_all(OUTPUT_DIR)
        st.success(f"迁移完成: {result}")

    st.divider()

    st.subheader("数据库信息")
    db_path = OUTPUT_DIR / ".dqg" / "store.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        st.caption(f"路径: `{db_path}`")
        st.caption(f"大小: {size_kb:.1f} KB")

        with get_connection(OUTPUT_DIR) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            for t in tables:
                name = t["name"]
                count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
                st.caption(f"  {name}: {count} 条记录")
    else:
        st.info("数据库尚未创建。执行迁移或运行 Phase 后自动创建。")


if __name__ == "__main__":
    main()
