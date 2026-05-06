"""Dashboard DAG/Token/瀑布图 + 数据管理页."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dqg.constants import LEGACY_PHASE_ID_MAP
from dqg.json_utils import load_json
from dqg.store import get_connection, migrate_all

from .cache import (
    _cached_phase_durations,
    _cached_projects,
    _cached_token_consumption,
)
from .constants import (
    OUTPUT_DIR,
    PHASE_NAMES,
    STATUS_COLOR,
    STATUS_LABEL,
    _format_dag_comment,
    _normalize_phase_id,
)

# ---------------------------------------------------------------------------
# 流程 DAG 页
# ---------------------------------------------------------------------------


def _page_dag():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    state_path = OUTPUT_DIR / pid / "state.json"
    if not state_path.exists():
        st.warning(f"未找到 {state_path}")
        return

    state = load_json(state_path)
    raw_phases = state.get("phases", {})
    phases = {LEGACY_PHASE_ID_MAP.get(k, k): v for k, v in raw_phases.items()}

    # 流程进度卡片
    st.subheader("流程进度")
    dag_order = ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"]
    cols = st.columns(len(dag_order))
    for i, qid in enumerate(dag_order):
        ps = phases.get(qid, {})
        status = ps.get("status", "not_started")
        color = STATUS_COLOR.get(status, "#dee2e6")
        label = STATUS_LABEL.get(status, status)
        name = PHASE_NAMES.get(qid, qid)
        duration = ps.get("duration_seconds")
        dur_str = f"{duration:.0f}s" if duration else "—"
        with cols[i]:
            st.markdown(
                f"""<div style="background:{color};border-radius:8px;padding:10px 6px;text-align:center;color:{"#fff" if status != "not_started" else "#666"}">
                <div style="font-size:1.1em;font-weight:bold">{qid}</div>
                <div style="font-size:0.75em;margin:2px 0">{name}</div>
                <div style="font-size:0.8em">{label}</div>
                <div style="font-size:0.75em;opacity:0.85">{dur_str}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # 依赖关系说明
    st.caption("依赖链：Q01 → Q02(可选) → Q03 → Q04 → Q07 ｜ Q01 → Q05(可选) → Q06 → Q07")

    # 状态明细表
    st.subheader("Phase 状态明细")
    rows = []
    for qid in dag_order:
        ps = phases.get(qid, {})
        status = ps.get("status", "not_started")
        rows.append(
            {
                "Phase": qid,
                "名称": PHASE_NAMES.get(qid, qid),
                "状态": STATUS_LABEL.get(status, status),
                "耗时(s)": ps.get("duration_seconds", "—"),
                "Judge 评分": ps.get("judge_score", "—"),
                "备注": _format_dag_comment(ps.get("comment", "")),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Token 消耗页
# ---------------------------------------------------------------------------


def _page_token():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    data = _cached_token_consumption(pid)
    if not data:
        st.info("暂无 Token 消耗数据。数据在 finalize 时自动收集。")
        return

    df = pd.DataFrame(data)
    if "phase_id" in df.columns:
        df["phase_id"] = df["phase_id"].apply(_normalize_phase_id)

    # 按 Phase 的 Token 消耗堆叠柱状图
    st.subheader("Token 消耗（按 Phase）")
    token_df = df[df["metric_name"].isin(["input_tokens", "output_tokens"])]
    if not token_df.empty:
        pivot = token_df.pivot_table(
            index="phase_id", columns="metric_name", values="metric_value", aggfunc="sum", fill_value=0
        )
        st.bar_chart(pivot)

    # 成本汇总
    st.subheader("成本汇总")
    cost_df = df[df["metric_name"] == "cost_estimate_usd"]
    if not cost_df.empty:
        total_cost = cost_df["metric_value"].sum()
        col1, col2, col3 = st.columns(3)
        with col1:
            total_tokens = df[df["metric_name"] == "total_tokens"]["metric_value"].sum()
            st.metric("总 Token", f"{total_tokens:,.0f}")
        with col2:
            st.metric("总成本", f"${total_cost:.4f}")
        with col3:
            avg_tps = df[df["metric_name"] == "tokens_per_second"]["metric_value"].mean()
            st.metric("平均速度", f"{avg_tps:.1f} tok/s" if avg_tps else "—")

        # 成本饼图
        cost_by_phase = cost_df.groupby("phase_id")["metric_value"].sum().reset_index()
        cost_by_phase.columns = ["Phase", "Cost ($)"]
        st.dataframe(cost_by_phase, hide_index=True)

    # Semantic Cache 命中率
    st.subheader("Semantic Cache 命中率")
    st.caption("命中率越高，重复查询越多走缓存，节省的 token 越多")
    try:
        from dqg.cache.semantic_cache import cache_stats

        stats = cache_stats(OUTPUT_DIR)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("缓存条目数", stats["total_entries"])
            st.caption("semantic_cache 中存储的唯一查询数")
        with c2:
            st.metric("累计命中次数", stats["total_hits"])
            st.caption("历史上命中缓存的查询总次数（节省了等量 LLM 调用）")
        with c3:
            hit_rate = stats["hit_rate"]
            st.metric("整体命中率", f"{hit_rate:.0%}", delta_color="normal" if hit_rate >= 0.3 else "inverse")
            st.caption("命中率 ≥ 30% 表示缓存在有效工作；< 10% 说明查询多样性高或缓存 TTL 过短")
        with c4:
            recent_rate = stats["recent_hit_rate_24h"]
            st.metric(
                "近24h 命中率",
                f"{recent_rate:.0%}",
                delta=f"{stats['recent_hits_24h']} hits / {stats['recent_misses_24h']} misses",
            )
            st.caption("近24小时的缓存效率，反映当前工作负载的缓存友好程度")
    except Exception as e:
        st.caption(f"缓存统计暂不可用: {e}")


# ---------------------------------------------------------------------------
# 执行瀑布图页
# ---------------------------------------------------------------------------


def _page_waterfall():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    data = _cached_phase_durations(pid)
    if not data:
        st.info("暂无执行记录")
        return

    st.subheader("Phase 耗时瀑布图")
    df = pd.DataFrame(data)
    finalize_df = df[df["action"] == "finalize"].copy()
    if finalize_df.empty:
        st.info("暂无 finalize 记录")
        return

    finalize_df["duration"] = finalize_df["duration_seconds"].fillna(0)
    finalize_df = finalize_df.sort_values("timestamp")

    # 水平柱状图
    chart_df = finalize_df[["phase_id", "duration"]].set_index("phase_id")
    st.bar_chart(chart_df, horizontal=True)

    # 明细表
    st.subheader("执行明细")
    display_df = finalize_df[["phase_id", "phase_name", "status", "duration_seconds", "timestamp"]].copy()
    display_df["phase_id"] = display_df["phase_id"].apply(_normalize_phase_id)
    display_df.columns = ["Phase", "名称", "状态", "耗时(s)", "时间"]
    st.dataframe(display_df, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 数据管理页
# ---------------------------------------------------------------------------


def _page_data_management():
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
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            for t in tables:
                name = t["name"]
                count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                st.caption(f"  {name}: {count} 条记录")
    else:
        st.info("数据库尚未创建。执行迁移或运行 Phase 后自动创建。")
