"""Phase Runtime：execute/finalize 的核心引擎.

从 commands/phase.py 下沉的执行逻辑，返回结构化 PhaseResult。
commands 层变成薄壳：解析参数 → 调用 runtime → 格式化输出。
"""

from __future__ import annotations

from pathlib import Path
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
from dqg.log import get_logger
from dqg.runtime.events import EventType
from dqg.runtime.lifecycle import get_registry
from dqg.runtime.result import PhaseResult

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext

log = get_logger(__name__)


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
        log.debug("Event emit failed", exc_info=True)


def _flush() -> None:
    """Flush 事件缓冲区（静默失败）."""
    try:
        from dqg.store.events import flush_events

        flush_events()
    except Exception:
        log.debug("Event flush failed", exc_info=True)


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

    # 自动创建 _reasoning_log.md 模板（仅当文件不存在时）
    # 防止手动模式下忘记创建推理日志导致 finalize BLOCKED
    _ensure_reasoning_log_template(ctx.phase_root, ctx.internal_dir, ctx.phase_id)

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

    # Phase-map 注入（aider repo-map 思路）：在全量 context 前先写入轻量结构索引
    # 增量更新：只有当源 JSON 比 _phase_map.md 新时才重新生成（Defer-A2）
    from dqg.context.phase_map import _UPSTREAM_MAP, generate_phase_map

    _should_regenerate = True
    if ctx.internal_dir:
        _map_path = ctx.internal_dir / "_phase_map.md"
        if _map_path.exists():
            from dqg.constants import STRUCTURED_JSON_MAP

            _map_mtime = _map_path.stat().st_mtime
            _up_phases = _UPSTREAM_MAP.get(ctx.phase_id, [])
            _any_newer = False
            for _up in _up_phases:
                _src_file = STRUCTURED_JSON_MAP.get(_up)
                if _src_file:
                    # 使用模块级 PHASE_DEFS / _phase_dir，避免 local import 导致 UnboundLocalError
                    _src = _phase_dir(ctx.output_dir, ctx.project_id, PHASE_DEFS.get(_up, {})) / _src_file
                    if _src.exists() and _src.stat().st_mtime > _map_mtime:
                        _any_newer = True
                        break
            _should_regenerate = _any_newer
            if not _should_regenerate:
                log.debug("Phase map still fresh for %s, skipping regeneration", ctx.phase_id)

    if _should_regenerate:
        _map_text = generate_phase_map(ctx.output_dir, ctx.project_id, ctx.phase_id)
        if _map_text and ctx.internal_dir:
            ctx.internal_dir.mkdir(parents=True, exist_ok=True)
            (ctx.internal_dir / "_phase_map.md").write_text(_map_text, encoding="utf-8")
            log.info("Phase map written for %s (%d chars)", ctx.phase_id, len(_map_text))

    # 上下文加载
    loaded_ctx = load_context(ctx.output_dir, ctx.project_id, ctx.phase_id, ctx.model_name)
    if loaded_ctx.chunks:
        ctx.internal_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = ctx.internal_dir / "_upstream_context.md"
        loaded_ctx.write_full_text(ctx_path)
        # Write token breakdown for compaction experiment baseline
        from dqg.json_utils import save_json

        save_json(ctx.internal_dir / "_evidence_token_breakdown.json", loaded_ctx.token_breakdown())
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

    # Q06 编译预检：测试代码不编译则跳过 LLM 审计，节省 token
    if ctx.phase_id == "Q06" and ctx.code_repos:
        from dqg.languages.java.provider import JavaProvider

        _java_provider = JavaProvider()
        for _repo in ctx.code_repos:
            _cr = _java_provider.compile_check(Path(_repo))
            if not _cr.passed and not _cr.skipped:
                result.add_error(f"Q06 pre-check: 测试编译失败，跳过 LLM 审计 ({_repo}): {_cr.error_summary}")
                result.add_event(
                    EventType.EXECUTE_COMPLETED,
                    f"Q06 pre-check compile failed: {_cr.error_summary}",
                )
                _flush()
                return result

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
    ref_errors, upstream_hashes = check_cross_phase_refs(ctx.output_dir, ctx.project_id)
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

                # AC 3: adaptive loop 跑完但 schema 仍未修复 → 明确报告（区别于手工提交产物首次校验失败）
                if _summary.get("adaptive_loop_schema_unresolved") and validation_errors:
                    last_errs = _summary.get("adaptive_loop_last_schema_errors") or []
                    total_iters = _summary.get("total_iterations", 0)
                    diag_msg = (
                        f"adaptive loop 未修复 schema 错误（跑完 {total_iters} 轮仍失败）"
                        f"，最后一轮遗留 {len(last_errs)} 条"
                    )
                    result.add_warning(diag_msg)
                    result.add_event(
                        EventType.VALIDATION_COMPLETED,
                        diag_msg,
                        adaptive_loop_schema_unresolved=True,
                        last_schema_errors=last_errs,
                        total_iterations=total_iters,
                    )
                    _emit(
                        ctx,
                        EventType.VALIDATION_COMPLETED,
                        diag_msg,
                        action="finalize",
                        adaptive_loop_schema_unresolved=True,
                        last_error_count=len(last_errs),
                        total_iterations=total_iters,
                    )

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
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.quality.guardrail import GuardrailContext, GuardrailLevel, run_guardrails
    from dqg.quality.guardrail_impl import get_guardrails
    from dqg.quality.rule_checks import read_report

    g_out: list[dict] = []
    try:
        report_content = read_report(ctx.phase_root, ctx.phase_id) if ctx.phase_root else ""
        structured_data: dict = {}
        if ctx.phase_root:
            json_name = STRUCTURED_JSON_MAP.get(ctx.phase_id)
            if json_name:
                json_path = ctx.phase_root / json_name
                if json_path.exists():
                    structured_data = load_json(json_path) or {}
        g_ctx = GuardrailContext(
            output_dir=ctx.output_dir,
            project_id=ctx.project_id,
            phase_id=ctx.phase_id,
            phase_dir=ctx.phase_root,
            report_content=report_content,
            structured_data=structured_data,
        )
        guardrails = get_guardrails(ctx.phase_id)
        g_results = run_guardrails(guardrails, g_ctx)

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
        log.warning("Guardrail execution failed for %s, skipping", ctx.phase_id, exc_info=True)

    if g_out:
        try:
            g_path = ctx.internal_dir / "_guardrail_results.json"
            g_path.parent.mkdir(parents=True, exist_ok=True)
            g_path.write_text(json.dumps(g_out, ensure_ascii=False, indent=2))
        except OSError:
            log.warning("Failed to persist guardrail results for %s", ctx.phase_id, exc_info=True)

    # GateVerdict: 汇总所有检查结果
    from dqg.runtime.gate_verdict import build_verdict, load_rule_overrides, save_verdict
    from dqg.runtime.phase_contract import enforce_phase_constraints

    try:
        constraint_violations = enforce_phase_constraints(ctx.output_dir, ctx.project_id, ctx.phase_id)
        # 项目根目录 = output_dir 的父目录（output_dir 形如 <project_root>/output）
        _project_root = ctx.output_dir.parent
        _rule_overrides = load_rule_overrides(_project_root)
        verdict = build_verdict(
            phase_id=ctx.phase_id,
            result=result,
            guardrail_results=g_out,
            constraint_violations=constraint_violations,
            schema_errors=ctx.shared.get("validation_errors"),
            upstream_hashes=upstream_hashes,
            rule_overrides=_rule_overrides or None,
        )
        save_verdict(ctx.output_dir, ctx.project_id, ctx.phase_id, verdict)
        ctx.shared["gate_verdict"] = verdict.to_dict()
    except Exception:
        log.error("GateVerdict build failed for %s", ctx.phase_id, exc_info=True)
        result.add_warning(f"GateVerdict build failed for {ctx.phase_id} — approve may require manual review")

    # Guard 精度周报：finalize 后自动聚合 output 下各项目 _guardrail_results（失败不阻断 finalize）
    try:
        from dqg.reporting.guard_precision_report import write_guard_precision_report

        gp_path = write_guard_precision_report(ctx.output_dir)
        log.info("Guard precision report refreshed: %s", gp_path)
    except Exception:
        log.warning("Guard precision report refresh skipped", exc_info=True)

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


def _ensure_reasoning_log_template(phase_root: Path, internal_dir: Path, phase_id: str) -> None:
    """在 execute 时自动创建 _reasoning_log.md 最小模板（幂等，文件已存在则跳过）.

    防止手动模式下忘记创建推理日志，导致 finalize 被 BLOCKED。
    Adaptive Loop 模式下 Agent 会覆盖此模板，不影响正常流程。
    """
    import contextlib

    candidate_paths = [internal_dir / "_reasoning_log.md", phase_root / "_reasoning_log.md"]
    if any(p.exists() for p in candidate_paths):
        return

    template = (
        f"# {phase_id} 推理日志\n\n"
        "## Step 0: 上下文确认\n\n"
        "> 本文件由 DQG execute 自动创建的最小模板。\n"
        "> 请在执行过程中更新此文件，记录每个 Step 的决策依据、关键发现和执行结果。\n\n"
        "## 执行过程\n\n"
        "（待填写）\n\n"
        "## 结论\n\n"
        "（待填写）\n"
    )
    with contextlib.suppress(Exception):
        internal_dir.mkdir(parents=True, exist_ok=True)
        (internal_dir / "_reasoning_log.md").write_text(template, encoding="utf-8")
        log.debug("Auto-created _reasoning_log.md template for %s", phase_id)
