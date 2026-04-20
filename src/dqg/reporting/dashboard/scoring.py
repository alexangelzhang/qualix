"""Dashboard 评分总览页."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dqg.constants import PHASE_DIR_MAP as PHASE_DIR
from dqg.json_utils import load_json

from dqg.constants import LEGACY_PHASE_ID_MAP

from .constants import (
    OUTPUT_DIR,
    EVAL_METRIC_ZH,
    EVAL_STATUS_COLOR,
    EVAL_STATUS_ZH,
    PHASE_NAMES,
    STATUS_LABEL,
    _load_phase_scoring,
)
from .cache import _cached_projects


# ---------------------------------------------------------------------------
# 评分总览页（A：统一评分体系）
# ---------------------------------------------------------------------------

def _page_scoring_overview():
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
    # 兼容旧格式 key（A/A.3/A.5/A.6/B/C/D → Q01-Q07）
    phases = {
        LEGACY_PHASE_ID_MAP.get(k, k): v
        for k, v in raw_phases.items()
    }

    st.subheader("各 Phase 评分总览")
    st.caption("Judge 评分 = Rubric 维度加权分（1-5）｜Contract = 硬检查通过率｜Eval = 指标对比基线状态｜质量 = 严重/高危问题数")

    dag_order = ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"]
    rows = []
    for qid in dag_order:
        ps = phases.get(qid, {})
        status = ps.get("status", "not_started")
        if status == "not_started":
            continue

        scoring = _load_phase_scoring(OUTPUT_DIR, pid, qid)

        # Judge 评分
        judge = scoring.get("judge", {})
        judge_score = judge.get("overall_score")
        judge_verdict = judge.get("verdict", "")
        judge_dims = judge.get("dimensions", [])
        judge_str = f"{judge_score:.1f}/5 ({judge_verdict})" if judge_score is not None else "—"

        # Contract 硬检查
        bundle = scoring.get("bundle", {})
        b_summary = bundle.get("summary", {})
        b_total = b_summary.get("total", 0)
        b_pass = b_summary.get("pass", 0)
        b_fail = b_summary.get("fail", 0)
        b_warn = b_summary.get("warning", 0)
        contract_str = f"{b_pass}/{b_total} 通过" if b_total else "—"
        contract_ok = b_fail == 0 and b_total > 0

        # Eval 指标
        eval_data = scoring.get("eval", {})
        comparisons = eval_data.get("comparisons", [])
        regressions = [c for c in comparisons if c.get("status") == "REGRESSION"]
        eval_str = f"⚠️ {len(regressions)} 项退化" if regressions else ("✅ 正常" if comparisons else "—")

        # 质量问题（Q03/Q07）
        quality_str = "—"
        if qid == "Q03":
            q03_path = OUTPUT_DIR / pid / "phaseA6" / "phase_a6_structured.json"
            if q03_path.exists():
                q03 = load_json(q03_path)
                issues = q03.get("issues", [])
                critical = sum(1 for i in issues if i.get("severity") in ("CRITICAL", "BLOCKER"))
                high = sum(1 for i in issues if i.get("severity") == "HIGH")
                quality_str = f"严重:{critical} 高:{high}" if issues else "无问题"
        elif qid == "Q07":
            q07_path = OUTPUT_DIR / pid / "phaseD" / "phase_d_structured.json"
            if q07_path.exists():
                q07 = load_json(q07_path)
                findings = q07.get("findings", [])
                blocker = sum(1 for f in findings if f.get("severity") in ("BLOCKER", "CRITICAL"))
                quality_str = f"阻断:{blocker}" if findings else "无发现"

        rows.append({
            "Phase": qid,
            "名称": PHASE_NAMES.get(qid, qid),
            "状态": STATUS_LABEL.get(status, status),
            "Judge 评分": judge_str,
            "Contract": contract_str,
            "Eval 基线": eval_str,
            "质量问题": quality_str,
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("暂无已执行的 Phase")
        return

    # Judge Rubric 维度展开
    st.divider()
    st.subheader("Judge Rubric 维度明细")
    for qid in dag_order:
        ps = phases.get(qid, {})
        if ps.get("status", "not_started") == "not_started":
            continue
        scoring = _load_phase_scoring(OUTPUT_DIR, pid, qid)
        judge = scoring.get("judge", {})
        dims = judge.get("dimensions", [])
        if not dims:
            continue
        with st.expander(f"{qid} {PHASE_NAMES.get(qid, '')} — Judge 维度分（总分 {judge.get('overall_score', '?')}/5）"):
            dim_rows = []
            for d in dims:
                dim_rows.append({
                    "维度": f"{d.get('id', '')} {d.get('name', '')}",
                    "得分": f"{d.get('score', '?')}/{d.get('max_score', 5)}",
                    "权重": f"{d.get('weight', 0):.0%}" if isinstance(d.get('weight'), (int, float)) else "—",
                    "问题数": len(d.get("issues", [])),
                })
            st.dataframe(pd.DataFrame(dim_rows), hide_index=True, use_container_width=True)

            # Rubric 快照（如果有）
            rubric_path = OUTPUT_DIR / pid / PHASE_DIR.get(qid, "") / "_internal" / "_judge_rubric.json"
            if rubric_path.exists():
                rubric = load_json(rubric_path)
                st.caption(f"Rubric 版本: {rubric.get('name', '—')} | 维度数: {len(rubric.get('dimensions', []))}")

    # Eval 退化明细
    st.divider()
    st.subheader("Eval 指标对比基线")
    for qid in dag_order:
        ps = phases.get(qid, {})
        if ps.get("status", "not_started") == "not_started":
            continue
        scoring = _load_phase_scoring(OUTPUT_DIR, pid, qid)
        eval_data = scoring.get("eval", {})
        comparisons = eval_data.get("comparisons", [])
        if not comparisons:
            continue
        with st.expander(f"{qid} {PHASE_NAMES.get(qid, '')} — Eval 指标（{len(comparisons)} 项）"):
            eval_rows = []
            for c in comparisons:
                status = c.get("status", "NEW")
                color = EVAL_STATUS_COLOR.get(status, "#6c757d")
                eval_rows.append({
                    "指标": EVAL_METRIC_ZH.get(c.get("metric", ""), c.get("metric", "")),
                    "当前值": c.get("current", "—"),
                    "基线值": c.get("baseline", "—"),
                    "变化": c.get("delta", "—"),
                    "状态": EVAL_STATUS_ZH.get(status, status),
                })
            st.dataframe(pd.DataFrame(eval_rows), hide_index=True, use_container_width=True)
