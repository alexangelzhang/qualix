"""Dashboard 总览页 + 告警."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dqg.tracking.bug_cases import load_cases, summarize_cases

from .cache import _cached_observe_alerts, _cached_projects, _cached_summary
from .constants import OUTPUT_DIR
from .trend import _load_phase_score_history

# ---------------------------------------------------------------------------
# 主动监控告警
# ---------------------------------------------------------------------------

_ALERT_SCORE_THRESHOLD = 3.5
_ALERT_PASS_RATE_THRESHOLD = 0.6


def _compute_alerts(projects: list[str]) -> list[dict]:
    """扫描所有项目，生成告警列表."""
    alerts = []
    for pid in projects:
        records = _load_phase_score_history(OUTPUT_DIR, pid)
        if not records:
            continue
        # 按 phase 取最新评分
        latest_by_phase: dict[str, dict] = {}
        for r in records:
            phase = r["phase"]
            if phase not in latest_by_phase or r["judged_at"] > latest_by_phase[phase]["judged_at"]:
                latest_by_phase[phase] = r

        for phase, r in latest_by_phase.items():
            score = r.get("score")
            if score is not None and score < _ALERT_SCORE_THRESHOLD:
                alerts.append(
                    {
                        "level": "error" if score < 2.5 else "warning",
                        "project": pid,
                        "phase": phase,
                        "phase_name": r.get("phase_name", phase),
                        "score": score,
                        "msg": f"[{pid}] {r.get('phase_name', phase)} Judge 评分 {score:.1f}/5 未达标",
                    }
                )

        # 通过率告警
        summary = _cached_summary(pid)
        rate = summary.get("phase_approval_rate", 1.0)
        if rate < _ALERT_PASS_RATE_THRESHOLD and summary.get("total_finalized", 0) >= 3:
            alerts.append(
                {
                    "level": "warning",
                    "project": pid,
                    "phase": "",
                    "phase_name": "",
                    "score": None,
                    "msg": f"[{pid}] Phase 通过率 {rate:.0%} 低于 {_ALERT_PASS_RATE_THRESHOLD:.0%}",
                }
            )

    return alerts


def _show_alerts(projects: list[str]) -> None:
    alerts = _compute_alerts(projects)

    # 合并 observe 告警（来自 dqg observability daily）
    observe_alerts = _cached_observe_alerts()
    for oa in observe_alerts:
        level = "error" if oa.get("severity") == "HIGH" else "warning"
        alerts.append(
            {
                "level": level,
                "project": oa.get("project_id", ""),
                "phase": oa.get("phase", ""),
                "phase_name": "",
                "score": None,
                "msg": f"[{oa.get('rule', '')}] {oa.get('message', '')}",
            }
        )

    if not alerts:
        return

    errors = [a for a in alerts if a["level"] == "error"]
    warnings = [a for a in alerts if a["level"] == "warning"]

    if errors:
        with st.expander(f"🔴 严重告警 ({len(errors)})", expanded=True):
            for a in errors:
                st.error(a["msg"])
    if warnings:
        with st.expander(f"⚠️ 警告 ({len(warnings)})", expanded=len(errors) == 0):
            for a in warnings:
                st.warning(a["msg"])

    st.divider()


# ---------------------------------------------------------------------------
# 总览页
# ---------------------------------------------------------------------------


def _page_overview():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据。请先执行 `dqg-run <project> execute Q01` 开始。")
        _show_bug_case_summary()
        return

    # 主动监控告警
    _show_alerts(projects)

    cols = st.columns(min(len(projects), 3))
    for i, pid in enumerate(projects):
        summary = _cached_summary(pid)
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

    phase_data = summary.get("by_phase", {})
    if phase_data:
        df = pd.DataFrame([{"Phase": k, "数量": v} for k, v in sorted(phase_data.items())])
        st.bar_chart(df, x="Phase", y="数量")
