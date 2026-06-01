"""Qualix 可视化看板 v2.

启动: streamlit run src/qualix/reporting/dashboard_app.py

页面: 总览 / 评分总览 / 流程 DAG / Token 消耗 / 执行瀑布图 / 质量评分
      / 事件追踪 / Bug 案例库 / 质量趋势 / Phase 评分趋势 / 可观测性 / 数据管理
      / 团队视图（飞书） / 多项目聚合 / Guard 精度 / SE 覆盖 / Judge 标注
性能: 查询结果缓存 60s，避免重复 SQLite I/O
"""

from __future__ import annotations

import streamlit as st

from .cache import _ensure_db
from .coverage import _page_coverage
from .data_mgmt import _page_dag, _page_data_management, _page_token, _page_waterfall
from .events import _page_bug_cases, _page_events
from .guard_dashboard import _page_guard_precision
from .judge_annotation import _page_judge_annotation
from .observability import _page_observability
from .overview import _page_overview
from .scores import _page_scores
from .scoring import _page_scoring_overview
from .team import _page_local_projects, _page_team
from .trend import _page_phase_score_trend, _page_quality_trend


def main():
    st.set_page_config(page_title="Qualix 质量看板", page_icon="🔍", layout="wide")
    st.title("Qualix 研发质量门禁看板")
    _ensure_db()

    st.sidebar.header("导航")
    page = st.sidebar.radio(
        "页面",
        [
            "总览",
            "多项目聚合",
            "团队视图（飞书）",
            "评分总览",
            "流程 DAG",
            "Token 消耗",
            "执行瀑布图",
            "质量评分",
            "SE 覆盖",
            "事件追踪",
            "Bug 案例库",
            "质量趋势",
            "Phase 评分趋势",
            "可观测性",
            "Guard 精度",
            "Judge 标注",
            "数据管理",
        ],
    )

    pages = {
        "总览": _page_overview,
        "多项目聚合": _page_local_projects,
        "团队视图（飞书）": _page_team,
        "评分总览": _page_scoring_overview,
        "流程 DAG": _page_dag,
        "Token 消耗": _page_token,
        "执行瀑布图": _page_waterfall,
        "质量评分": _page_scores,
        "SE 覆盖": _page_coverage,
        "事件追踪": _page_events,
        "Bug 案例库": _page_bug_cases,
        "质量趋势": _page_quality_trend,
        "Phase 评分趋势": _page_phase_score_trend,
        "可观测性": _page_observability,
        "Guard 精度": _page_guard_precision,
        "Judge 标注": _page_judge_annotation,
        "数据管理": _page_data_management,
    }
    pages[page]()


if __name__ == "__main__":
    main()
