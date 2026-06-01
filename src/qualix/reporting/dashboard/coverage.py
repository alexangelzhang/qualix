"""SE Coverage Heatmap and Phase Score Trend pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from qualix.constants import PHASE_DIR_MAP
from qualix.json_utils import load_json
from qualix.log import get_logger

from .cache import _cached_projects
from .constants import OUTPUT_DIR
from .trend import _load_phase_score_history

log = get_logger(__name__)

_STATUS_COLOR = {
    "COVERED": "background-color: #d4edda; color: #155724",
    "PARTIAL": "background-color: #fff3cd; color: #856404",
    "MISSING": "background-color: #f8d7da; color: #721c24",
}


def _load_q06_audit_items(output_dir: Path, project_id: str) -> list[dict[str, Any]]:
    phase_suffix = PHASE_DIR_MAP.get("Q06", "Q06")
    path = output_dir / project_id / phase_suffix / "phase_c_structured.json"
    if not path.exists():
        return []
    try:
        data = load_json(path)
        return data.get("audit_items", []) if data else []
    except Exception:
        log.debug("Failed to load Q06 audit items for %s", project_id, exc_info=True)
        return []


def _page_coverage() -> None:
    st.header("SE Coverage")
    st.caption(
        "Semantic expectation coverage from Q06 audit results. "
        "COVERED = assertion proves the SE; PARTIAL = indirect only; MISSING = no test."
    )

    projects = _cached_projects()
    if not projects:
        st.info("No project data found. Run some phases to populate the dashboard.")
        return

    pid = st.selectbox("Project", projects, key="coverage_pid")
    if not pid:
        return

    items = _load_q06_audit_items(OUTPUT_DIR, pid)
    if not items:
        st.info(f"No Q06 audit data for project '{pid}'. Run Q06 first.")
    else:
        # Build SE × EUT matrix
        import pandas as pd

        rows = []
        for item in items:
            rows.append(
                {
                    "SE": item.get("se_id", "—"),
                    "EUT": item.get("eut_id", "—"),
                    "Status": item.get("status", "—"),
                    "Description": item.get("description", "")[:80],
                }
            )
        df = pd.DataFrame(rows)

        # Summary metrics
        total = len(df)
        covered = (df["Status"] == "COVERED").sum()
        partial = (df["Status"] == "PARTIAL").sum()
        missing = (df["Status"] == "MISSING").sum()
        sem_rate = covered / max(total, 1)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total EUT", total)
        c2.metric("Covered", covered, delta=f"{sem_rate:.0%}")
        c3.metric("Partial", partial)
        c4.metric("Missing", missing)

        # Color-coded table
        st.subheader("Coverage Detail")

        def _row_style(row):
            color = _STATUS_COLOR.get(row["Status"], "")
            return [color] * len(row)

        styled = df.style.apply(_row_style, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # Phase score trend (multi-project)
    st.divider()
    st.subheader("Phase Score Trend")
    compare_pids = st.multiselect("Compare projects", projects, default=[pid], key="coverage_compare")

    if compare_pids:
        import pandas as pd

        all_records = []
        for p in compare_pids:
            for rec in _load_phase_score_history(OUTPUT_DIR, p):
                rec["project"] = p
                all_records.append(rec)

        if all_records:
            df_trend = pd.DataFrame(all_records)
            df_trend = df_trend[df_trend["score"].notna()]
            df_trend["label"] = df_trend["project"] + "/" + df_trend["phase"]
            df_trend["judged_at"] = pd.to_datetime(df_trend["judged_at"], errors="coerce")
            df_trend = df_trend.sort_values("judged_at")

            pivot = df_trend.pivot_table(index="judged_at", columns="label", values="score", aggfunc="mean")
            if not pivot.empty:
                st.line_chart(pivot)
            else:
                st.info("Not enough timestamped data to draw a trend.")
        else:
            st.info("No judge score history found for selected projects.")
