"""Finalize 阶段的 lifecycle handler：从 cmd_finalize 下沉的 sidecar 逻辑."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.runtime.events import EventType
from dqg.runtime.handler_utils import async_write_json as _async_write_json
from dqg.runtime.handler_utils import emit_handler_event as _emit_handler
from dqg.runtime.lifecycle import register_handler

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


def handle_perf_metrics(ctx: ExecutionContext, result: PhaseResult) -> None:
    """收集并持久化性能指标."""
    from dqg.json_utils import save_json
    from dqg.reporting.perf_tracker import collect_phase_metrics, persist_phase_metrics

    duration = ctx.shared.get("duration_seconds")
    metrics = collect_phase_metrics(ctx.output_dir, ctx.project_id, ctx.phase_id, duration)
    if not metrics:
        return

    persist_phase_metrics(ctx.output_dir, metrics)
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    save_json(ctx.internal_dir / "_perf_metrics.json", metrics)
    result.add_artifact("perf_metrics", str(ctx.internal_dir / "_perf_metrics.json"))
    ctx.shared["perf_metrics"] = metrics
    _emit_handler(
        ctx,
        EventType.PERF_COLLECTED,
        "Perf metrics collected",
        total_tokens=metrics.get("total_tokens", 0),
        cost_usd=metrics.get("cost_estimate_usd", 0),
    )


def handle_quality_tracking(ctx: ExecutionContext, result: PhaseResult) -> None:
    """规则质量追踪 + 自动 bug case 生成."""
    from dqg.skill_tracker import auto_generate_bug_case, suggest_prompt_fix, track_rule_quality

    validation_errors = ctx.shared.get("validation_errors", [])
    auto_cases = []
    if validation_errors:
        auto_cases = auto_generate_bug_case(ctx.project_id, ctx.phase_id, validation_errors)
        if auto_cases:
            ctx.shared["auto_bug_cases"] = auto_cases
            fixes = suggest_prompt_fix(auto_cases)
            ctx.shared["prompt_fixes"] = fixes
            _async_write_json(ctx.internal_dir / "_auto_bug_cases.json", auto_cases)
            _async_write_json(ctx.internal_dir / "_prompt_fixes.json", fixes)

    quality_report = track_rule_quality(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if quality_report.get("matched_signals") or quality_report.get("potential_new_issues"):
        ctx.shared["quality_report"] = quality_report
        result.add_event(EventType.QUALITY_REPORT_READY, "Quality tracking completed")
        _async_write_json(ctx.internal_dir / "_quality_report.json", quality_report)

    if auto_cases:
        _emit_handler(
            ctx, EventType.BUG_CASES_GENERATED, f"{len(auto_cases)} bug cases generated", count=len(auto_cases)
        )


def handle_memory_index(ctx: ExecutionContext, result: PhaseResult) -> None:
    """结构化事实索引 + 版本追踪."""
    from dqg.memory.memory_layer import MemoryLayer

    memory = MemoryLayer(ctx.output_dir)
    index_result = memory.index_phase(ctx.project_id, ctx.phase_id)
    ctx.shared["index_result"] = index_result
    if index_result.get("facts"):
        result.add_event(
            EventType.MEMORY_INDEXED,
            f"Indexed {index_result['facts']} facts",
            facts=index_result["facts"],
        )
        _async_write_json(ctx.internal_dir / "_memory_index.json", index_result)


def handle_golden_sample(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Golden Sample 标杆对比."""
    from dqg.quality.golden_sample import compare_with_golden

    base_dir = ctx.output_dir.parent
    golden_diff = compare_with_golden(ctx.output_dir, ctx.project_id, ctx.phase_id, base_dir)
    ctx.shared["golden_diff"] = golden_diff
    if golden_diff:
        _async_write_json(ctx.internal_dir / "_golden_diff.json", golden_diff)


def handle_rule_compliance(ctx: ExecutionContext, result: PhaseResult) -> None:
    """规则执行率追踪."""
    from dqg.quality.rule_compliance import compute_rule_compliance, persist_compliance

    compliance = compute_rule_compliance(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if compliance:
        persist_compliance(ctx.output_dir, compliance)
        ctx.shared["compliance"] = compliance
        _emit_handler(
            ctx,
            EventType.RULE_CHECK_COMPLETED,
            "Rule compliance checked",
            pass_rate=compliance.get("pass_rate", 0),
            passed=compliance.get("passed", 0),
            total=compliance.get("total", 0),
        )


def handle_review_chain(ctx: ExecutionContext, result: PhaseResult) -> None:
    """生成评审链 prompt（Judge + Critique）."""
    from dqg.quality.critique import write_critique_prompt
    from dqg.quality.judge import write_judge_prompt
    from dqg.quality.review_chain import build_review_chain_payload, write_review_chain_prompt

    review_payload = build_review_chain_payload(ctx.output_dir, ctx.project_id, ctx.phase_id)
    chain_path = write_review_chain_prompt(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
        prompt=review_payload["review_chain_prompt"] if review_payload else None,
    )
    if chain_path:
        result.add_artifact("review_chain_prompt", str(chain_path))
        result.add_event(EventType.REVIEW_CHAIN_READY, "Review chain prompt generated")

    judge_path = write_judge_prompt(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
        prompt=review_payload["judge_prompt"] if review_payload else None,
    )
    critique_path = write_critique_prompt(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
        prompt=review_payload["critique_prompt"] if review_payload else None,
    )

    # M2 fix: critique prompt 未生成时标记 BLOCKED，防止依赖链无声断裂
    # 仅当 review_payload 包含 critique prompt（即该 Phase 支持 critique）时才检查
    if not critique_path and judge_path and review_payload and review_payload.get("critique_prompt"):
        result.add_error("BLOCKED: Judge prompt 已生成但 Critique prompt 写入失败 — RLAIF 反馈循环将断裂")


def handle_profile_context_check(ctx: ExecutionContext, result: PhaseResult) -> None:
    """检查报告是否包含 PROFILE_CONTEXT."""
    from dqg.path_utils import resolve_internal_file
    from dqg.text_utils import REPORT_MAP

    report_file = REPORT_MAP.get(ctx.phase_id)
    if not report_file:
        return

    profile_ctx_path = resolve_internal_file(ctx.phase_root, "_profile_context.md")
    if not profile_ctx_path.exists():
        result.add_warning(f"Missing profile context: {profile_ctx_path}")

    report_path = ctx.phase_root / report_file
    if report_path.exists() and "## PROFILE_CONTEXT" not in report_path.read_text(encoding="utf-8"):
        result.add_warning("Report missing PROFILE_CONTEXT section")


def handle_progress_file(ctx: ExecutionContext, result: PhaseResult) -> None:
    """生成跨 session 进度文件 _progress.json."""
    from dqg.runtime.progress import write_phase_progress, write_project_progress

    phase_path = write_phase_progress(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if phase_path:
        result.add_artifact("phase_progress", str(phase_path))

    project_path = write_project_progress(ctx.output_dir, ctx.project_id)
    result.add_artifact("project_progress", str(project_path))


def handle_skill_factory(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Skill Factory：基于 bug case 自动生成 skill 规则补充建议."""
    from dqg.tracking.skill_factory import write_skill_suggestions

    path = write_skill_suggestions(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("skill_suggestions", str(path))

    # Skill Evolution：生成具体 diff + 记录谱系
    from dqg.tracking.skill_evolution import generate_evolution_report

    evo_path = generate_evolution_report(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if evo_path:
        result.add_artifact("skill_evolution", str(evo_path))
        _emit_handler(ctx, EventType.SKILL_EVOLVED, "Skill evolution report generated")


def handle_auto_judge(ctx: ExecutionContext, result: PhaseResult) -> None:
    """自动合成 Judge 结果：从 structured JSON 生成 _judge_result.json.

    解决 finalize 只生成 judge prompt 但无人执行导致 approve 被阻断的问题。
    如果 _judge_result.json 已存在（AI 手动执行了 judge prompt）则跳过。
    """
    from dqg.quality.judge import synthesize_judge_result

    judge_result = synthesize_judge_result(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
    )
    if judge_result:
        ctx.shared["judge_result"] = judge_result
        if judge_result.get("auto_synthesized"):
            result.add_event(EventType.REVIEW_CHAIN_READY, "Judge result auto-synthesized from structured JSON")
        result.add_artifact("judge_result", str(ctx.phase_root / "_judge_result.json"))


def handle_score_calibration(ctx: ExecutionContext, result: PhaseResult) -> None:
    """DeepEval 评分校准：Judge 一致性检测 + 趋势监控."""
    from dqg.quality.score_calibration import check_score_consistency, check_score_trend

    # 一致性检测（需要 Judge 结果存在）
    calibration = check_score_consistency(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if calibration:
        result.add_artifact("score_calibration", str(ctx.internal_dir / "_score_calibration.json"))
        if not calibration["consistent"]:
            result.add_warning(
                f"Score drift: DQG={calibration['dqg_score']:.1f} vs DeepEval={calibration['deepeval_score']:.1f} "
                f"(drift={calibration['drift']:.1f})"
            )

    # 趋势监控
    trend = check_score_trend(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if trend.get("trend") in ("inflation", "deflation"):
        result.add_warning(
            f"Score {trend['trend']}: Phase {ctx.phase_id} avg {trend['avg_previous']:.1f} → {trend['avg_recent']:.1f}"
        )


def handle_eval_baseline(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Eval-Driven：计算评估指标并对比历史基线."""
    from dqg.quality.eval_baseline import write_eval_metrics

    path = write_eval_metrics(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("eval_metrics", str(path))


def handle_facts_export(ctx: ExecutionContext, result: PhaseResult) -> None:
    """将结构化事实导出为 Markdown，纳入 git 追踪."""
    from dqg.cache.fact_cache import export_facts_to_markdown

    path = export_facts_to_markdown(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("facts_export", str(path))


def handle_verification_bundle(ctx: ExecutionContext, result: PhaseResult) -> None:
    """收集所有验证结果到统一 bundle."""
    from dqg.quality.verification_bundle import write_verification_bundle

    path = write_verification_bundle(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("verification_bundle", str(path))


def handle_requirement_graph(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q01: 需求层级图 GAP 检测."""
    from dqg.quality.requirement_graph import write_requirement_graph_analysis

    path = write_requirement_graph_analysis(ctx.output_dir, ctx.project_id)
    if path:
        result.add_artifact("requirement_graph", str(path))


def handle_report_quality_checks(ctx: ExecutionContext, result: PhaseResult) -> None:
    """报告产物质量确定性检测（正则驱动，零 LLM）."""
    from dqg.quality.report_quality_checks import run_report_quality_checks

    checks = run_report_quality_checks(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if not checks or checks["total"] == 0:
        return

    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    _async_write_json(ctx.internal_dir / "_report_quality_checks.json", checks)
    ctx.shared["report_quality_checks"] = checks

    # 按类型汇总 WARNING
    for check_name, count in checks.get("by_check", {}).items():
        result.add_warning(f"报告质量检测: {check_name} 发现 {count} 个问题")

    _emit_handler(
        ctx,
        EventType.QUALITY_REPORT_READY,
        f"Report quality: {checks['total']} issues found",
        total=checks["total"],
        by_check=checks.get("by_check", {}),
    )


def register_finalize_handlers() -> None:
    """注册所有 finalize 阶段的 handler."""
    # Group 1: 无依赖，可并行
    for name, fn, order in [
        ("perf_metrics", handle_perf_metrics, 10),
        ("quality_tracking", handle_quality_tracking, 20),
        ("memory_index", handle_memory_index, 30),
        ("golden_sample", handle_golden_sample, 40),
        ("rule_compliance", handle_rule_compliance, 50),
        ("report_quality_checks", handle_report_quality_checks, 55),
    ]:
        register_handler(name, fn, stage="finalize", order=order)

    # 异构检测层（从 handlers_detection 导入）
    from dqg.runtime.handlers_detection import (
        handle_ai_origin_detection,
        handle_mock_coincidence_check,
        handle_weak_assert_gate,
    )

    register_handler("weak_assert_gate", handle_weak_assert_gate, stage="finalize", phases={"Q06"}, order=56)
    register_handler(
        "mock_coincidence_check", handle_mock_coincidence_check, stage="finalize", phases={"Q06"}, order=57
    )
    register_handler("ai_origin_detection", handle_ai_origin_detection, stage="finalize", order=58)
    register_handler("profile_context_check", handle_profile_context_check, stage="finalize", order=60)
    register_handler(
        "requirement_graph",
        handle_requirement_graph,
        stage="finalize",
        phases={"Q01"},
        order=63,
        depends_on=["memory_index"],
    )
    register_handler("verification_bundle", handle_verification_bundle, stage="finalize", order=65)
    register_handler("facts_export", handle_facts_export, stage="finalize", order=66)
    # Group 2: 依赖 memory_index
    register_handler(
        "review_chain", handle_review_chain, stage="finalize", order=70, depends_on=["memory_index"], required=True
    )
    register_handler("progress_file", handle_progress_file, stage="finalize", order=80)
    register_handler("skill_factory", handle_skill_factory, stage="finalize", order=90)
    # Group 2.5: 依赖 review_chain
    register_handler("auto_judge", handle_auto_judge, stage="finalize", order=75, depends_on=["review_chain"])
    # Group 3: 依赖 quality_tracking
    register_handler(
        "score_calibration", handle_score_calibration, stage="finalize", order=95, depends_on=["quality_tracking"]
    )
    register_handler("eval_baseline", handle_eval_baseline, stage="finalize", order=98)
