"""Skill 规则级质量追踪 + 自动修复闭环 + 案例相关性匹配 — Facade.

实际实现已拆分到 quality_tracker / bug_case_generator / case_selector。
本文件 re-export 所有公开 API，保持向后兼容。
"""

from __future__ import annotations

# --- quality_tracker ---
from dqg.quality.quality_tracker import format_quality_report  # noqa: F401
from dqg.quality.quality_tracker import track_rule_quality  # noqa: F401

# --- bug_case_generator ---
from dqg.tracking.bug_case_generator import auto_generate_bug_case  # noqa: F401
from dqg.tracking.bug_case_generator import extract_judge_cases  # noqa: F401
from dqg.tracking.bug_case_generator import suggest_prompt_fix  # noqa: F401

# --- case_selector ---
from dqg.tracking.case_selector import render_relevant_cases_for_prompt  # noqa: F401
from dqg.tracking.case_selector import select_relevant_cases  # noqa: F401
