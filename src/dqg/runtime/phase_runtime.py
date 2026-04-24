"""Phase Runtime：execute/finalize 的核心引擎.

从 commands/phase.py 下沉的执行逻辑，返回结构化 PhaseResult。
commands 层变成薄壳：解析参数 → 调用 runtime → 格式化输出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dqg.core.state_machine import (
    PHASE_DEFS,
    execute_phase,
    finalize_phase,
    load_state,
    save_state,
)
from dqg.core.state_machine import (
    internal_dir as _internal_dir,
)
from dqg.core.state_machine import (
    phase_dir as _phase_dir,
)
from dqg.json_utils import load_json
from dqg.runtime.events import EventType
from dqg.runtime.lifecycle import get_registry
from dqg.runtime.result import PhaseResult

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext


def _emit(ctx: ExecutionContext, event_type: EventType, message: str = "", **data: Any) -> None:
    """持久化事件到 SQLite（缓冲写入，静默失败不阻断主流程）."""
    try:
        from dqg.store.events import insert_event

        insert_event(
            ctx.output_dir,
            project_id=ctx.project_id,
            phase_id=ctx.phase_id,
            event_type=event_type.value,
            action=data.pop("action", ""),
            message=message,
            data=data if data else None,
            duration_ms=int(data.pop("duration_ms", 0)) if "duration_ms" in data else 0,
        )
    except Exception:
        pass


def _flush() -> None:
    """Flush 事件缓冲区（静默失败）."""
    try:
        from dqg.store.events import flush_events

        flush_events()
    except Exception:
        pass


def runtime_execute(ctx: ExecutionContext) -> PhaseResult:
    """执行 Phase：状态流转 + 上下文加载 + handler 执行.

    Returns:
        PhaseResult 结构化结果
    """
    from dqg.context.context_loader import load_context
    from dqg.context.doc_summary import generate_summary_file
    from dqg.core.profiles import get_profile
    from dqg.reporting.telemetry import PhaseRunRecord, append_record
    from dqg.services.phase_service import write_phase_profile_manifest

    result = PhaseResult(phase_id=ctx.phase_id, action="execute")

    # 状态流转
    state = load_state(ctx.output_dir, ctx.project_id)
    if ctx.profile_id:
        state.profile_id = ctx.profile_id
    else:
        state.profile_id = get_profile(None).profile_id
        ctx.profile_id = state.profile_id

    errors = execute_phase(state, ctx.phase_id)
    if errors:
        for e in errors:
            result.add_error(e)
        return result

    save_state(ctx.output_dir, state)

    phase_def = PHASE_DEFS[ctx.phase_id]
    ctx.phase_def = phase_def
    ctx.phase_root = _phase_dir(ctx.output_dir, ctx.project_id, phase_def)
    ctx.internal_dir = _internal_dir(ctx.output_dir, ctx.project_id, phase_def)

    append_record(
        ctx.output_dir,
        PhaseRunRecord(
            project_id=ctx.project_id,
            phase_id=ctx.phase_id,
            phase_name=phase_def["name"],
            action="execute",
            status="in_progress",
            started_at=state.phases[ctx.phase_id].started_at,
        ),
    )

    result.add_event(
        EventType.PHASE_STARTED,
        f"Phase {ctx.phase_id}({phase_def['name']}) started",
        skill=phase_def["skill"],
        profile=state.profile_id,
    )
    _emit(
        ctx,
        EventType.PHASE_STARTED,
        f"Phase {ctx.phase_id} started",
        action="execute",
        skill=phase_def["skill"],
        profile=state.profile_id,
    )

    # 上下文加载
    loaded_ctx = load_context(ctx.output_dir, ctx.project_id, ctx.phase_id, ctx.model_name)
    if loaded_ctx.chunks:
        ctx.internal_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = ctx.internal_dir / "_upstream_context.md"
        loaded_ctx.write_full_text(ctx_path)
        ctx.relevance_text = loaded_ctx.relevance_seed
        result.add_event(
            EventType.CONTEXT_LOADED,
            loaded_ctx.summary,
            path=str(ctx_path),
            truncated=loaded_ctx.truncated,
        )
        _emit(
            ctx,
            EventType.CONTEXT_LOADED,
            loaded_ctx.summary,
            action="execute",
            token_count=loaded_ctx.total_tokens if hasattr(loaded_ctx, "total_tokens") else 0,
            truncated=loaded_ctx.truncated,
        )
        result.add_artifact("upstream_context", str(ctx_path))

    # 文档摘要
    summary_path = generate_summary_file(ctx.phase_root)
    if summary_path:
        result.add_artifact("doc_summary", str(summary_path))

    # Profile manifest + bug cases + cross-project insights
    write_phase_profile_manifest(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
        state.profile_id,
        relevance_text=ctx.relevance_text,
    )
    result.add_event(EventType.PROFILE_WRITTEN, "Profile manifest written")
    _emit(ctx, EventType.PROFILE_WRITTEN, "Profile manifest written", action="execute")

    # 执行所有注册的 execute handler
    get_registry().run_handlers("execute", ctx, result)

    result.add_event(EventType.EXECUTE_COMPLETED, f"Phase {ctx.phase_id} execute completed")
    _emit(ctx, EventType.EXECUTE_COMPLETED, f"Phase {ctx.phase_id} execute completed", action="execute")
    _flush()
    return result


def runtime_finalize(ctx: ExecutionContext) -> PhaseResult:
    """Finalize Phase：校验 + 质量评审 + handler 执行.

    Returns:
        PhaseResult 结构化结果
    """
    import json

    from dqg.quality.cross_phase_check import check_cross_phase_refs
    from dqg.quality.finalize_checks import run_finalize_checks
    from dqg.reporting.telemetry import PhaseRunRecord, append_record
    from dqg.schemas import validate_phase_output

    result = PhaseResult(phase_id=ctx.phase_id, action="finalize")

    state = load_state(ctx.output_dir, ctx.project_id)
    phase_def = ctx.phase_def or PHASE_DEFS.get(ctx.phase_id)
    if not phase_def:
        result.add_error(f"Unknown phase: {ctx.phase_id}")
        return result

    ctx.phase_def = phase_def
    if not ctx.phase_root:
        ctx.phase_root = _phase_dir(ctx.output_dir, ctx.project_id, phase_def)
    if not ctx.internal_dir:
        ctx.internal_dir = _internal_dir(ctx.output_dir, ctx.project_id, phase_def)

    # 缓存 state 到 shared，handler 不需要再 load_state
    ctx.shared["state"] = state

    # Schema 校验
    validation_errors = validate_phase_output(ctx.output_dir, ctx.project_id, ctx.phase_id) or []
    ref_errors = check_cross_phase_refs(ctx.output_dir, ctx.project_id)
    if ref_errors:
        validation_errors.extend(ref_errors)

    # 硬性校验
    hard_errors = run_finalize_checks(ctx.output_dir, ctx.project_id, ctx.phase_id)
    blocked = [e for e in hard_errors if e.startswith("BLOCKED")]
    if blocked:
        for e in hard_errors:
            result.add_error(e)
        result.add_event(EventType.FINALIZE_BLOCKED, f"{len(blocked)} blocking errors")
        return result

    regression_warnings = [e for e in hard_errors if e.startswith("REGRESSION")]
    for w in regression_warnings:
        result.add_warning(w)
    validation_errors.extend(regression_warnings)

    result.add_event(
        EventType.VALIDATION_COMPLETED,
        f"Validation: {len(validation_errors)} issues",
        validation_errors=validation_errors,
    )
    _emit(
        ctx,
        EventType.VALIDATION_COMPLETED,
        f"Validation: {len(validation_errors)} issues",
        action="finalize",
        error_count=len(validation_errors),
        blocked_count=len(blocked) if "blocked" in dir() else 0,
    )

    # 状态流转
    errors = finalize_phase(state, ctx.phase_id, validation_errors)
    if errors:
        for e in errors:
            result.add_error(e)
        return result

    save_state(ctx.output_dir, state)
    ps = state.phases[ctx.phase_id]

    # Load LLM call telemetry from adaptive summary if available
    llm_calls: list[dict] = []
    if ctx.phase_root:
        _summary_path = ctx.phase_root / "_adaptive_summary.json"
        if _summary_path.exists():
            _summary = load_json(_summary_path)
            if _summary:
                llm_calls = _summary.get("llm_calls", [])

    append_record(
        ctx.output_dir,
        PhaseRunRecord(
            project_id=ctx.project_id,
            phase_id=ctx.phase_id,
            phase_name=phase_def["name"],
            action="finalize",
            status="pending_review",
            started_at=ps.started_at,
            finished_at=ps.finished_at,
            duration_seconds=ps.duration_seconds,
            validation_errors=validation_errors,
            llm_calls=llm_calls,
        ),
    )

    # 把 validation_errors 和 duration 放入 shared 供 handler 使用
    ctx.shared["validation_errors"] = validation_errors
    ctx.shared["duration_seconds"] = ps.duration_seconds
    ctx.shared["phase_state"] = ps

    # 执行所有注册的 finalize handler
    get_registry().run_handlers("finalize", ctx, result)

    # 统一 Guardrail 门控（并发执行，结果持久化）
    g_out: list[dict] = []
    try:
        from dqg.quality.guardrail import GuardrailContext, GuardrailLevel, run_guardrails
        from dqg.quality.guardrail_impl import get_guardrails
        from dqg.quality.rule_checks import read_report

        report_content = read_report(ctx.phase_root, ctx.phase_id) if ctx.phase_root else ""
        g_ctx = GuardrailContext(
            output_dir=ctx.output_dir,
            project_id=ctx.project_id,
            phase_id=ctx.phase_id,
            phase_dir=ctx.phase_root,
            report_content=report_content,
        )
        guardrails = get_guardrails(ctx.phase_id)
        g_results = run_guardrails(guardrails, g_ctx)

        # 持久化结果
        g_out = [
            {
                "guardrail": r.guardrail_name,
                "passed": r.passed,
                "level": r.level.value,
                "message": r.message,
                "details": r.details,
            }
            for r in g_results
        ]
        g_path = ctx.internal_dir / "_guardrail_results.json"
        g_path.parent.mkdir(parents=True, exist_ok=True)
        g_path.write_text(json.dumps(g_out, ensure_ascii=False, indent=2))

        # 汇总到 result
        g_blocked = [r for r in g_results if r.level == GuardrailLevel.BLOCKED and not r.passed]
        g_warnings = [r for r in g_results if r.level == GuardrailLevel.WARNING and not r.passed]
        if g_blocked or g_warnings:
            summary_parts = []
            if g_blocked:
                summary_parts.append(f"{len(g_blocked)} blocked")
            if g_warnings:
                summary_parts.append(f"{len(g_warnings)} warnings")
            result.add_event(
                EventType.VALIDATION_COMPLETED,
                f"Guardrail: {', '.join(summary_parts)}",
                guardrail_blocked=len(g_blocked),
                guardrail_warnings=len(g_warnings),
            )
    except Exception:
        pass  # guardrail 不阻断主流程

    # GateVerdict: 汇总所有检查结果
    try:
        from dqg.runtime.gate_verdict import build_verdict, save_verdict
        from dqg.runtime.phase_contract import enforce_phase_constraints

        constraint_violations = enforce_phase_constraints(ctx.output_dir, ctx.project_id, ctx.phase_id)
        verdict = build_verdict(
            phase_id=ctx.phase_id,
            result=result,
            guardrail_results=g_out,
            constraint_violations=constraint_violations,
        )
        save_verdict(ctx.output_dir, ctx.project_id, ctx.phase_id, verdict)
        ctx.shared["gate_verdict"] = verdict.to_dict()
    except Exception:
        pass  # verdict 构建失败不阻断 finalize

    result.add_event(
        EventType.FINALIZE_COMPLETED,
        f"Phase {ctx.phase_id} finalized",
        duration=ps.duration_seconds,
    )
    _emit(
        ctx,
        EventType.FINALIZE_COMPLETED,
        f"Phase {ctx.phase_id} finalized",
        action="finalize",
        duration_seconds=ps.duration_seconds,
    )
    _flush()
    return result
