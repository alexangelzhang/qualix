"""Dashboard 可观测性页面：告警历史 + 日报摘要 + 指标趋势 + Guard/LLM 明细."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from qualix.log import get_logger

from .cache import _cached_observe_alerts, _cached_projects
from .constants import OUTPUT_DIR

log = get_logger(__name__)


def _load_observe_reports(period: str = "daily") -> list[dict]:
    """从文件系统加载 observe 报告列表."""
    from qualix.json_utils import load_json

    report_dir = OUTPUT_DIR.parent / "observability" / "reports" / period
    if not report_dir.exists():
        return []
    reports = []
    for f in sorted(report_dir.glob("*.json"), reverse=True)[:10]:
        try:
            data = load_json(f)
            if data is not None:
                reports.append(data)
        except Exception:
            log.debug("Failed to load observe report %s", f, exc_info=True)
    return reports


def _guard_precision_doc_path() -> Path:
    """与 `write_guard_precision_report` 默认路径一致（cwd=仓库根时）."""
    return OUTPUT_DIR.parent / "docs" / "observability" / "reports" / "weekly" / "guard_precision.md"


def _render_guard_and_llm_tab() -> None:
    """Guard 精度周报 + Telemetry 中 llm_calls（含 P0 payload 摘录）。"""
    from qualix.reporting.guard_precision_report import build_guard_precision_summary
    from qualix.store import query_telemetry

    st.subheader("Guard 精度周报")
    summary = build_guard_precision_summary(OUTPUT_DIR)
    st.caption(
        f"已读 guardrail 结果文件数: {summary.get('guardrail_files_read', 0)} · 生成时间 {summary.get('generated_at', '')}"
    )
    byg = summary.get("by_guard") or {}
    if byg:
        g_rows = [{"guardrail": k, **v} for k, v in sorted(byg.items())]
        st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)
    gp_md = _guard_precision_doc_path()
    if gp_md.is_file():
        with st.expander("Markdown 周报全文", expanded=False):
            st.markdown(gp_md.read_text(encoding="utf-8"))
    else:
        st.caption("未找到 guard_precision.md。运行 `qualix-run … observe guard-precision` 或在 finalize 后自动生成。")

    st.divider()
    st.subheader("Telemetry · LLM 调用明细")
    projects = _cached_projects()
    if not projects:
        st.info("无项目；请先产生 telemetry 记录。")
        return
    pid = st.selectbox("项目", projects, key="telemetry_llm_project")
    lim = st.slider("最近 finalize 条数", 5, 200, 40, key="telemetry_llm_limit")
    only_ex = st.checkbox("仅显示含 prompt/response 摘录的调用", True, key="telemetry_llm_only_excerpt")
    rows = query_telemetry(OUTPUT_DIR, project_id=pid, action="finalize", limit=int(lim))
    if not rows:
        st.caption("该项目无 finalize 的 telemetry。")
        return
    for r in rows:
        calls = r.get("llm_calls")
        if isinstance(calls, str):
            try:
                calls = json.loads(calls)
            except json.JSONDecodeError:
                calls = []
        if not isinstance(calls, list) or not calls:
            continue
        ts = str(r.get("timestamp", ""))[:19]
        phase = r.get("phase_id", "")
        rid = r.get("id", ts)
        shown = []
        for j, c in enumerate(calls):
            if not isinstance(c, dict):
                continue
            if only_ex and not (c.get("prompt_excerpt") or c.get("response_excerpt")):
                continue
            shown.append((j, c))
        if not shown:
            continue
        with st.expander(f"{ts} · {phase} · {len(shown)} 条采样/展示", expanded=False):
            for j, c in shown:
                span = c.get("span_path", "") or ""
                st.markdown(
                    f"**#{j}** `{span}` · `{c.get('model_id', '')}` · hash `{str(c.get('prompt_hash', ''))[:12]}`"
                )
                if c.get("prompt_excerpt"):
                    st.text_area(
                        "prompt_excerpt",
                        str(c["prompt_excerpt"]),
                        height=220,
                        key=f"pex_{pid}_{rid}_{j}",
                        disabled=True,
                    )
                if c.get("response_excerpt"):
                    st.text_area(
                        "response_excerpt",
                        str(c["response_excerpt"]),
                        height=160,
                        key=f"rex_{pid}_{rid}_{j}",
                        disabled=True,
                    )


def _page_observability():
    st.header("可观测性")

    tab_alerts, tab_reports, tab_metrics, tab_guard_llm = st.tabs(["告警历史", "日报/周报", "指标趋势", "Guard与LLM"])

    # --- 告警历史 ---
    with tab_alerts:
        alerts = _cached_observe_alerts()
        if not alerts:
            st.info("暂无 observe 告警。运行 `qualix-run observe daily` 生成。")
        else:
            df = pd.DataFrame(alerts)
            display_cols = [
                c for c in ["label", "severity", "rule", "project_id", "phase", "message"] if c in df.columns
            ]
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
            st.info(f"暂无 {period} 报告。运行 `qualix-run observe report --period {period}` 生成。")
        else:
            for report in reports:
                label = report.get("label", "unknown")
                projects = report.get("projects", [])
                with st.expander(f"{label} ({len(projects)} 项目)", expanded=(report == reports[0])):
                    if projects:
                        rows = []
                        for p in projects:
                            rows.append(
                                {
                                    "Project": p.get("project_id", ""),
                                    "Approval Rate": f"{p.get('phase_approval_rate', 0):.0%}",
                                    "Avg Duration(s)": f"{p.get('avg_duration_seconds', 0):.1f}",
                                    "GAP Closure": f"{p.get('gap_closure_rate', 0):.0%}",
                                    "BLOCK": p.get("block_count", 0),
                                    "Finalized": p.get("finalized", 0),
                                }
                            )
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                    pe = report.get("prompt_effectiveness") or {}
                    if pe.get("token_distribution"):
                        st.caption("Token / 成本粗估（与 observe Markdown 一致）")
                        st.metric(
                            "窗口 Est. USD（合计）",
                            f"{pe.get('cost_total_usd', 0):.4f}",
                            help="基于 perf_tracker 定价常量的 llm_calls 聚合",
                        )
                        st.metric("Payload 采样命中调用数", int(pe.get("payload_sample_calls", 0) or 0))
                        td = pd.DataFrame(pe["token_distribution"])
                        st.dataframe(td, use_container_width=True, hide_index=True)

                    ts = report.get("trace_summary") or {}
                    if ts.get("span_paths"):
                        st.caption("Trace 分层（P2 span_path）")
                        st.dataframe(pd.DataFrame(ts["span_paths"]), use_container_width=True, hide_index=True)
                        st.caption(f"独立 trace_run 数: {ts.get('unique_trace_runs', 0)}")

                    an = report.get("metric_anomalies") or []
                    if an:
                        st.caption("指标异常（P3 Z-score / IQR）")
                        st.dataframe(pd.DataFrame(an), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Prompt 版本库（P2 · SQLite）")
        try:
            from qualix.store.prompt_versions import query_prompt_versions

            pv = query_prompt_versions(OUTPUT_DIR, prompt_hash=None, limit=30)
        except Exception:
            log.debug("prompt_versions query failed", exc_info=True)
            pv = []
        if not pv:
            st.caption(
                "暂无记录；需采样命中且 Agent 配置 output_dir（见 `QUALIX_TELEMETRY_PAYLOAD_*` / `QUALIX_PROMPT_VERSION_STORE`）。"
            )
        else:
            st.dataframe(pd.DataFrame(pv), use_container_width=True, hide_index=True)

    # --- 指标趋势 ---
    with tab_metrics:
        history = _load_metrics_history()
        if not history:
            st.info("暂无指标历史。运行 `qualix-run observe daily` 积累数据。")
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

    with tab_guard_llm:
        _render_guard_and_llm_tab()


def _load_metrics_history() -> list[dict]:
    """加载 observe 指标历史."""
    import contextlib
    import json

    path = OUTPUT_DIR.parent / "observability" / "metrics_history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            with contextlib.suppress(Exception):
                rows.append(json.loads(line))
    return rows
