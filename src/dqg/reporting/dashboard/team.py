"""团队视图 — 从飞书 bitable 拉取多用户执行数据."""

from __future__ import annotations

import streamlit as st

_BASE_TOKEN = "FQtabFSMTauogmstiydc46PFnRf"
_TABLE_ID = "tblN5rGXczqUBk3p"


def _fetch_records(limit: int = 500) -> list[dict]:
    """从 bitable 拉取记录，失败返回空列表."""
    try:
        from dqg.feishu.client import bitable_list_records, is_logged_in

        if not is_logged_in():
            return []
        return bitable_list_records(_BASE_TOKEN, _TABLE_ID, page_size=min(limit, 100))
    except Exception:
        return []


def _page_team() -> None:
    st.header("👥 团队视图")
    st.caption("数据来源：飞书多维表格，实时拉取所有用户的执行记录")

    with st.spinner("正在从飞书拉取团队数据..."):
        records = _fetch_records()

    if not records:
        st.warning("暂无数据，或 larkkit 未登录。请运行 `uvx larkkit auth login` 后刷新。")
        return

    import pandas as pd

    df = pd.DataFrame(records)

    # 过滤掉空行（只有默认文本字段的记录）
    if "项目ID" in df.columns:
        df = df[df["项目ID"].notna() & (df["项目ID"] != "")]
    else:
        st.warning("表格字段结构不匹配，请检查 bitable 字段配置。")
        return

    if df.empty:
        st.info("暂无有效执行记录。")
        return

    # 数值转换
    if "Judge评分" in df.columns:
        df["Judge评分"] = pd.to_numeric(df["Judge评分"], errors="coerce")
    if "耗时(秒)" in df.columns:
        df["耗时(秒)"] = pd.to_numeric(df["耗时(秒)"], errors="coerce")

    # ── 筛选栏 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        projects = ["全部", *sorted(df["项目ID"].dropna().unique().tolist())]
        sel_project = st.selectbox("项目", projects)
    with col2:
        users = ["全部", *sorted(df["用户"].dropna().unique().tolist())] if "用户" in df.columns else ["全部"]
        sel_user = st.selectbox("用户", users)
    with col3:
        phases = ["全部", *sorted(df["Phase"].dropna().unique().tolist())] if "Phase" in df.columns else ["全部"]
        sel_phase = st.selectbox("Phase", phases)

    filtered = df.copy()
    if sel_project != "全部":
        filtered = filtered[filtered["项目ID"] == sel_project]
    if sel_user != "全部" and "用户" in filtered.columns:
        filtered = filtered[filtered["用户"] == sel_user]
    if sel_phase != "全部" and "Phase" in filtered.columns:
        filtered = filtered[filtered["Phase"] == sel_phase]

    # ── 汇总指标 ──
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总执行次数", len(filtered))
    if "是否通过" in filtered.columns:
        pass_count = (filtered["是否通过"] == "是").sum()
        m2.metric("通过次数", pass_count)
        m3.metric("通过率", f"{pass_count / len(filtered) * 100:.1f}%" if len(filtered) > 0 else "N/A")
    if "Judge评分" in filtered.columns:
        avg_score = filtered["Judge评分"].mean()
        m4.metric("平均 Judge 评分", f"{avg_score:.2f}" if not pd.isna(avg_score) else "N/A")

    # ── 按用户汇总 ──
    st.divider()
    st.subheader("按用户汇总")
    if "用户" in filtered.columns and "Judge评分" in filtered.columns:
        user_summary = (
            filtered.groupby("用户")
            .agg(
                执行次数=("项目ID", "count"),
                平均评分=("Judge评分", "mean"),
                通过次数=("是否通过", lambda x: (x == "是").sum()),
            )
            .reset_index()
        )
        user_summary["通过率"] = (user_summary["通过次数"] / user_summary["执行次数"] * 100).round(1).astype(str) + "%"
        user_summary["平均评分"] = user_summary["平均评分"].round(2)
        st.dataframe(user_summary, use_container_width=True)

    # ── 按 Phase 汇总 ──
    st.subheader("按 Phase 汇总")
    if "Phase" in filtered.columns and "Judge评分" in filtered.columns:
        phase_summary = (
            filtered.groupby("Phase")
            .agg(
                执行次数=("项目ID", "count"),
                平均评分=("Judge评分", "mean"),
                通过次数=("是否通过", lambda x: (x == "是").sum()),
            )
            .reset_index()
            .sort_values("Phase")
        )
        phase_summary["通过率"] = (phase_summary["通过次数"] / phase_summary["执行次数"] * 100).round(1).astype(
            str
        ) + "%"
        phase_summary["平均评分"] = phase_summary["平均评分"].round(2)
        st.dataframe(phase_summary, use_container_width=True)

    # ── 原始记录 ──
    st.divider()
    with st.expander("原始记录", expanded=False):
        display_cols = [
            c
            for c in ["时间", "用户", "项目ID", "Phase", "Phase名称", "Judge评分", "是否通过", "耗时(秒)", "Profile"]
            if c in filtered.columns
        ]
        st.dataframe(
            filtered[display_cols].sort_values("时间", ascending=False)
            if "时间" in filtered.columns
            else filtered[display_cols],
            use_container_width=True,
        )
