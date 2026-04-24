"""Dashboard 趋势页 + Phase 评分趋势页."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from pathlib import Path
import streamlit as st

from dqg.json_utils import load_json
from dqg.log import get_logger

from .cache import _cached_projects, _cached_trend
from .constants import OUTPUT_DIR

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Phase 评分历史加载
# ---------------------------------------------------------------------------


def _load_phase_score_history(output_dir: Path, project_id: str) -> list[dict]:
    """扫描所有 Phase 的 _judge_result.json 和 _archive/vN/ 历史版本，构建评分时间线."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    records = []
    proj_dir = output_dir / project_id

    for phase_id, phase_def in PHASE_DEFS.items():
        dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
        phase_path = proj_dir / dir_suffix

        # 当前版本
        judge_path = phase_path / "_internal" / "_judge_result.json"
        if judge_path.exists():
            try:
                data = load_json(judge_path)
                records.append(
                    {
                        "phase": phase_id,
                        "phase_name": phase_def.get("name", phase_id),
                        "score": data.get("overall_score"),
                        "verdict": data.get("verdict", ""),
                        "judged_at": data.get("judged_at", ""),
                        "version": "current",
                    }
                )
            except Exception:
                pass

        # 归档版本
        archive_root = phase_path / "_archive"
        if archive_root.exists():
            for ver_dir in sorted(archive_root.iterdir()):
                if not ver_dir.is_dir():
                    continue
                archived_judge = ver_dir / "_internal" / "_judge_result.json"
                if archived_judge.exists():
                    try:
                        data = load_json(archived_judge)
                        records.append(
                            {
                                "phase": phase_id,
                                "phase_name": phase_def.get("name", phase_id),
                                "score": data.get("overall_score"),
                                "verdict": data.get("verdict", ""),
                                "judged_at": data.get("judged_at", ""),
                                "version": ver_dir.name,
                            }
                        )
                    except Exception:
                        pass

    return records


# ---------------------------------------------------------------------------
# 质量趋势页
# ---------------------------------------------------------------------------


def _page_quality_trend():
    projects = _cached_projects()
    pid = st.selectbox("项目", ["全部", *projects]) if projects else None
    days = st.slider("时间范围（天）", 7, 90, 30)

    project_filter = pid if pid and pid != "全部" else None
    trend = _cached_trend(project_filter, days)

    if not trend:
        st.info("暂无趋势数据。数据会在项目执行后自动积累。")
        return

    df = pd.DataFrame(trend)
    if "day" not in df.columns or "count" not in df.columns:
        st.info("数据格式异常")
        return

    # 汇总指标
    total_finalize = int(df[df["action"] == "finalize"]["count"].sum()) if "action" in df.columns else 0
    total_approve = int(df[df["action"] == "approve"]["count"].sum()) if "action" in df.columns else 0
    approve_rate = total_approve / total_finalize if total_finalize else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总执行次数", total_finalize)
        st.caption("所有 Phase 的 finalize 调用总次数，反映团队使用频率")
    with col2:
        st.metric("通过次数", total_approve)
        st.caption("Judge 评分通过并 approve 的次数，代表真实交付质量")
    with col3:
        st.metric(
            "通过率",
            f"{approve_rate:.0%}",
            delta="良好" if approve_rate >= 0.8 else "偏低",
            delta_color="normal" if approve_rate >= 0.8 else "inverse",
        )
        st.caption("通过率 ≥ 80% 为良好；< 60% 建议排查输入材料或 Phase 标准")

    # 趋势图
    pivot = df.pivot_table(index="day", columns="action", values="count", fill_value=0)
    st.subheader("每日执行量")
    st.line_chart(pivot)

    # 耗时趋势
    if "avg_duration" in df.columns:
        duration_df = df[df["action"] == "finalize"][["day", "avg_duration"]].dropna()
        if not duration_df.empty:
            st.subheader("平均耗时趋势（秒）")
            avg_dur = duration_df["avg_duration"].mean()
            recent = duration_df.tail(3)["avg_duration"].mean()
            trend_delta = recent - avg_dur
            st.metric(
                "近3日平均耗时",
                f"{recent:.0f}s",
                delta=f"{trend_delta:+.0f}s vs 整体均值",
                delta_color="inverse" if trend_delta > 0 else "normal",
            )
            st.caption("耗时上升可能意味着输入材料复杂度增加或 Phase 标准趋严；下降通常表示流程熟练度提升")
            st.line_chart(duration_df.set_index("day"))

    # 分析结论
    st.subheader("自动分析")
    insights = []
    if approve_rate < 0.6:
        insights.append("⚠️ 通过率低于 60%，建议检查 Phase 质量标准或输入材料质量")
    elif approve_rate >= 0.9:
        insights.append("✅ 通过率高于 90%，流程运行稳定")
    if total_finalize == 0:
        insights.append("📭 暂无执行记录，请先运行 Phase")
    elif total_finalize < 5:
        insights.append(f"📊 样本量较少（{total_finalize} 次），趋势仅供参考")
    if not insights:
        insights.append("📈 数据正常，无异常信号")
    for msg in insights:
        st.caption(msg)


# ---------------------------------------------------------------------------
# Phase 评分趋势页
# ---------------------------------------------------------------------------


def _page_phase_score_trend():
    st.subheader("Phase 评分趋势")
    st.caption("追踪每个 Phase 多次执行的 Judge 评分变化，识别质量改善或退化")

    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    output_dir = OUTPUT_DIR
    records = _load_phase_score_history(output_dir, pid)

    if not records:
        st.info("暂无评分历史。Phase 执行并 finalize 后会自动积累。")
        return

    df = pd.DataFrame(records)
    df = df[df["score"].notna()].copy()

    if df.empty:
        st.info("暂无有效评分数据")
        return

    # 汇总指标
    avg_score = df["score"].mean()
    pass_count = (df["score"] >= 3.5).sum()
    pass_rate = pass_count / len(df)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("平均 Judge 评分", f"{avg_score:.2f}/5")
        st.caption("所有 Phase 所有版本的 Judge 评分均值")
    with col2:
        st.metric("通过次数", f"{pass_count}/{len(df)}")
        st.caption("评分 ≥ 3.5 视为通过")
    with col3:
        st.metric("通过率", f"{pass_rate:.0%}", delta_color="normal" if pass_rate >= 0.8 else "inverse")
        st.caption("通过率 ≥ 80% 为健康水位")

    # 各 Phase 最新评分对比
    st.subheader("各 Phase 最新评分")
    latest = df.sort_values("judged_at").groupby("phase").last().reset_index()
    latest = latest.sort_values("phase")
    if not latest.empty:
        bar_data = latest.set_index("phase_name")["score"]
        st.bar_chart(bar_data)

        # 评分明细表
        display_cols = ["phase", "phase_name", "score", "verdict", "judged_at", "version"]
        display_cols = [c for c in display_cols if c in latest.columns]
        st.dataframe(
            latest[display_cols].rename(
                columns={
                    "phase": "Phase ID",
                    "phase_name": "Phase 名称",
                    "score": "评分",
                    "verdict": "判定",
                    "judged_at": "评审时间",
                    "version": "版本",
                }
            ),
            hide_index=True,
        )

    # 多版本趋势（有归档数据时才显示）
    multi_version = df[df["version"] != "current"]
    if not multi_version.empty:
        st.subheader("多版本评分趋势（有重置记录的 Phase）")
        phases_with_history = multi_version["phase"].unique().tolist()
        selected = st.multiselect("选择 Phase", phases_with_history, default=phases_with_history[:3])
        if selected:
            trend_df = df[df["phase"].isin(selected)].copy()
            trend_df = trend_df.sort_values(["phase", "judged_at"])
            trend_df["run_index"] = trend_df.groupby("phase").cumcount() + 1
            pivot = trend_df.pivot_table(index="run_index", columns="phase_name", values="score")
            st.line_chart(pivot)
            st.caption("横轴为执行次序（第1次、第2次...），纵轴为 Judge 评分（满分5分）")

    # 自动分析
    st.subheader("自动分析")
    insights = []
    low_phases = latest[latest["score"] < 3.5]["phase_name"].tolist() if not latest.empty else []
    if low_phases:
        insights.append(f"⚠️ 以下 Phase 评分未达标（< 3.5）：{', '.join(low_phases)}")
    if avg_score >= 4.0:
        insights.append("✅ 整体评分优秀（均值 ≥ 4.0），质量稳定")
    elif avg_score < 3.0:
        insights.append("🔴 整体评分偏低（均值 < 3.0），建议排查 Skill 规则或输入材料")
    if not insights:
        insights.append("📈 评分正常，无异常信号")
    for msg in insights:
        st.caption(msg)
