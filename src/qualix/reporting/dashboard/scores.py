"""Dashboard 质量评分页."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from qualix.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from qualix.json_utils import load_json

from .cache import _cached_projects
from .constants import (
    DIM_NAMES,
    OUTPUT_DIR,
    SEV_ZH,
    UT_STATUS_ZH,
)

# ---------------------------------------------------------------------------
# 质量评分页
# ---------------------------------------------------------------------------


def _page_scores():
    projects = _cached_projects()
    if not projects:
        st.info("暂无项目数据")
        return

    pid = st.selectbox("选择项目", projects)
    if not pid:
        return

    st.subheader("Phase 质量指标")

    # Q03 技术方案质量评审
    q03_path = OUTPUT_DIR / pid / PHASE_DIR_MAP["Q03"] / STRUCTURED_JSON_MAP["Q03"]
    if q03_path.exists():
        q03 = load_json(q03_path)
        issues = q03.get("issues", [])
        if issues:
            st.markdown("#### Q03 技术方案质量评审")
            severity_counts = {}
            for issue in issues:
                sev = issue.get("severity", "UNKNOWN")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            col1, col2, col3, col4 = st.columns(4)
            for col, key in zip([col1, col2, col3, col4], ["CRITICAL", "HIGH", "MEDIUM", "LOW"], strict=False):
                with col:
                    cnt = severity_counts.get(key, 0)
                    st.metric(
                        f"{SEV_ZH.get(key, key)}({key})",
                        cnt,
                        delta=f"{'⚠️ 需处理' if key in ('CRITICAL', 'HIGH') and cnt > 0 else ''}",
                    )

            dim_counts = {}
            for issue in issues:
                iid = issue.get("issue_id", "")
                dim = iid.split("-")[0] if "-" in iid else "OTHER"
                dim_counts[dim] = dim_counts.get(dim, 0) + 1
            if dim_counts:
                dim_df = pd.DataFrame([{"维度": k, "数量": v} for k, v in sorted(dim_counts.items())])
                st.bar_chart(dim_df, x="维度", y="数量")

            # 展开 CRITICAL/HIGH 问题明细
            critical_high = [i for i in issues if i.get("severity") in ("CRITICAL", "HIGH", "BLOCKER")]
            if critical_high:
                with st.expander(f"⚠️ 严重/高危问题明细（{len(critical_high)} 条）", expanded=True):
                    for issue in critical_high:
                        sev = issue.get("severity", "")
                        sev_zh = SEV_ZH.get(sev, sev)
                        iid = issue.get("issue_id", "—")
                        title = issue.get("title", "")
                        desc = issue.get("description", issue.get("detail", "—"))
                        suggestion = issue.get("suggestion", issue.get("fix", ""))
                        evidence = issue.get("evidence", "")
                        related_req = issue.get("related_req", [])
                        color = "#dc3545" if sev in ("CRITICAL", "BLOCKER") else "#fd7e14"
                        label = f"**`{iid}`** [{sev_zh}]" + (f" — {title}" if title else "")
                        st.markdown(
                            f"<span style='color:{color}'>{label}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"问题：{desc}")
                        if evidence:
                            st.caption(f"证据：{evidence}")
                        if related_req:
                            st.caption(f"关联需求：{', '.join(related_req)}")
                        if suggestion:
                            st.caption(f"建议：{suggestion}")
                        st.divider()

        fms = q03.get("failure_modes", [])
        if fms:
            risk_counts = {}
            for fm in fms:
                risk = fm.get("risk", fm.get("status", "UNKNOWN"))
                risk_counts[risk] = risk_counts.get(risk, 0) + 1
            st.markdown("**Failure Mode 风险分布**")
            risk_zh = {"HIGH": "高风险", "MEDIUM": "中风险", "LOW": "低风险", "CRITICAL": "严重"}
            fm_df = pd.DataFrame([{"风险等级": risk_zh.get(k, k), "数量": v} for k, v in sorted(risk_counts.items())])
            st.dataframe(fm_df, hide_index=True, width="stretch")

    # Q04 覆盖度
    q04_path = OUTPUT_DIR / pid / PHASE_DIR_MAP["Q04"] / STRUCTURED_JSON_MAP["Q04"]
    if q04_path.exists():
        q04 = load_json(q04_path)
        summary = q04.get("coverage_summary", [])
        if summary:
            st.markdown("#### Q04 技术方案覆盖度")
            cov_df = pd.DataFrame(summary)
            display_cols = [
                c
                for c in ["dimension", "total", "covered", "partial", "missing", "coverage_rate"]
                if c in cov_df.columns
            ]
            cov_df = cov_df[display_cols].copy()
            col_rename = {
                "dimension": "维度",
                "total": "总数",
                "covered": "已覆盖",
                "partial": "部分覆盖",
                "missing": "未覆盖",
                "coverage_rate": "覆盖率",
            }
            cov_df.rename(columns=col_rename, inplace=True)
            if "维度" in cov_df.columns:
                cov_df["维度"] = cov_df["维度"].apply(lambda x: f"{DIM_NAMES.get(x, x)}({x})")
            st.dataframe(cov_df, hide_index=True, width="stretch")

    # Q06 单测审计
    q06_path = OUTPUT_DIR / pid / PHASE_DIR_MAP["Q06"] / STRUCTURED_JSON_MAP["Q06"]
    if q06_path.exists():
        q06 = load_json(q06_path)
        items = q06.get("audit_items", [])
        if items:
            st.markdown("#### Q06 单测覆盖审计")
            status_counts = {}
            for item in items:
                s = item.get("status", "UNKNOWN")
                status_counts[s] = status_counts.get(s, 0) + 1
            total = len(items)
            covered = status_counts.get("COVERED", 0)
            rate = covered / total if total else 0
            st.metric(
                "SE 覆盖率",
                f"{rate:.0%}",
                delta=f"{covered}/{total} 已覆盖",
                delta_color="normal" if rate >= 0.8 else "inverse",
            )
            cols = st.columns(len(status_counts))
            for i, (s, c) in enumerate(sorted(status_counts.items())):
                with cols[i]:
                    st.metric(UT_STATUS_ZH.get(s, s), c)

    # Q07 代码评审
    q07_path = OUTPUT_DIR / pid / PHASE_DIR_MAP["Q07"] / STRUCTURED_JSON_MAP["Q07"]
    if q07_path.exists():
        q07 = load_json(q07_path)
        findings = q07.get("findings", [])
        if findings:
            st.markdown("#### Q07 代码评审发现")
            sev_counts = {}
            for f in findings:
                sev = f.get("severity", "UNKNOWN")
                sev_counts[sev] = sev_counts.get(sev, 0) + 1
            cols = st.columns(len(sev_counts))
            for i, (s, c) in enumerate(sorted(sev_counts.items())):
                with cols[i]:
                    st.metric(f"{SEV_ZH.get(s, s)}({s})", c)
