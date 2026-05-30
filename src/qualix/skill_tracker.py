"""Skill 规则级质量追踪 + 自动修复闭环 + 案例相关性匹配 — Facade.

实际实现已拆分到 quality_tracker / bug_case_generator / case_selector。
本文件 re-export 所有公开 API，保持向后兼容。
"""

from __future__ import annotations

from qualix.quality.regression.quality_tracker import format_quality_report, track_rule_quality
from qualix.tracking.bug_case_generator import (
    auto_generate_bug_case,
    extract_judge_cases,
    suggest_prompt_fix,
)
from qualix.tracking.case_selector import render_relevant_cases_for_prompt

__all__ = [
    "auto_generate_bug_case",
    "extract_judge_cases",
    "format_quality_report",
    "render_relevant_cases_for_prompt",
    "suggest_prompt_fix",
    "track_rule_quality",
]
