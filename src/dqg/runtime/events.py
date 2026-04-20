"""Runtime 事件类型：Phase 生命周期中的所有事件."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Phase 生命周期事件类型."""

    # execute 阶段
    PHASE_STARTED = "phase_started"
    CONTEXT_LOADED = "context_loaded"
    PROFILE_WRITTEN = "profile_written"
    SIDECAR_COMPLETED = "sidecar_completed"
    EXECUTE_COMPLETED = "execute_completed"

    # finalize 阶段
    VALIDATION_COMPLETED = "validation_completed"
    FINALIZE_BLOCKED = "finalize_blocked"
    FINALIZE_COMPLETED = "finalize_completed"
    QUALITY_REPORT_READY = "quality_report_ready"
    MEMORY_INDEXED = "memory_indexed"
    REVIEW_CHAIN_READY = "review_chain_ready"

    # approve 阶段
    PHASE_APPROVED = "phase_approved"
    PHASE_SKIPPED = "phase_skipped"

    # AI 产出阶段
    AI_OUTPUT_RECEIVED = "ai_output_received"
    JUDGE_COMPLETED = "judge_completed"
    RULE_CHECK_COMPLETED = "rule_check_completed"

    # 自动化 sidecar
    BUG_CASES_GENERATED = "bug_cases_generated"
    PERF_COLLECTED = "perf_collected"
    SKILL_EVOLVED = "skill_evolved"

    # 用户交互
    USER_INPUT_WAITING = "user_input_waiting"
    USER_INPUT_RECEIVED = "user_input_received"

    # 通用
    WARNING = "warning"
    ERROR = "error"
