"""Phase 核心命令：execute / finalize / approve / skip / reset / auto."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from dqg.core.state_machine import (
    PHASE_DEFS,
    approve_phase,
    get_available_phases,
    get_parallel_groups,
    load_state,
    record_judge_score,
    save_state,
    skip_phase,
)
from dqg.services.phase_service import profile_context_warnings as _profile_context_warnings


# Re-export sub-command implementations (lazy to break phase ↔ phase_auto/phase_reset cycle)
def __getattr__(name: str):
    _reexports = {
        "cmd_reset": "dqg.commands.phase_reset",
        "cmd_auto": "dqg.commands.phase_auto",
        "collect_inputs": "dqg.commands.phase_auto",
        "prompt_approve": "dqg.commands.phase_auto",
    }
    if name in _reexports:
        import importlib

        mod = importlib.import_module(_reexports[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _telemetry():
    """延迟导入 telemetry，避免模块级拉入 pydantic 链."""
    from dqg.reporting.telemetry import PhaseRunRecord, append_record, print_run_summary

    return PhaseRunRecord, append_record, print_run_summary


def _emit_cmd(output_dir: Path, project_id: str, phase_id: str, event_type: str, message: str = "", **data) -> None:
    """命令层事件埋点（静默失败）."""
    try:
        from dqg.store.events import insert_event

        insert_event(output_dir, project_id, phase_id, event_type, message=message, **data)
    except Exception:
        from dqg.log import get_logger

        get_logger(__name__).debug("事件埋点失败", exc_info=True)


def _flush_events() -> None:
    """Flush 事件缓冲区（静默失败）."""
    try:
        from dqg.store.events import flush_events

        flush_events()
    except Exception:
        from dqg.log import get_logger

        get_logger(__name__).debug("事件 flush 失败", exc_info=True)


def profile_context_warnings(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """向后兼容：保留 commands.phase 的旧导出。"""
    return _profile_context_warnings(output_dir, project_id, phase_id)


def cmd_execute(args, output_dir: Path) -> int:
    import dqg.runtime  # noqa: F401 — 触发 handler 注册
    from dqg.core.profiles import get_profile
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.phase_runtime import runtime_execute

    profile_id = get_profile(getattr(args, "profile", None)).profile_id
    ctx = ExecutionContext(
        output_dir=output_dir,
        project_id=args.project_id,
        phase_id=args.phase,
        profile_id=profile_id,
        model_name=getattr(args, "model", None),
        code_repo=getattr(args, "code_repo", None),
        base_branch=getattr(args, "base_branch", "master"),
        feature_branch=getattr(args, "feature_branch", "HEAD"),
    )

    result = runtime_execute(ctx)

    for event in result.events:
        if event.event_type.value == "error":
            print(f"  ERROR: {event.message}", file=sys.stderr)
        elif event.event_type.value == "warning":
            print(f"  WARNING: {event.message}", file=sys.stderr)
        elif event.event_type.value == "phase_started":
            print(f"\n  Phase {args.phase}({event.data.get('skill', '')}) 已启动")
            print(f"  Profile: {event.data.get('profile', '')}")
            from dqg.constants import MODEL_TIER
            from dqg.core.phase_registry import PHASE_DEFS

            phase_def = PHASE_DEFS.get(args.phase, {})
            tier = phase_def.get("recommended_model", "strong")
            model = MODEL_TIER.get(tier, "claude-opus-4-6")
            print(f"  推荐模型: {model} ({tier})")
        elif event.event_type.value == "context_loaded":
            print(f"\n  上下文已加载: {event.message}")
            if event.data.get("truncated"):
                print("  注意: 上下文已截断")
        elif event.event_type.value == "sidecar_completed":
            handler_name = event.data.get("handler", "")
            if handler_name not in ("", "diff_context", "weak_assert"):
                print(f"  Sidecar: {event.message}")

    for name, path in result.artifacts.items():
        if name in ("upstream_context", "doc_summary"):
            print(f"  {name}: {path}")

    if result.success:
        print(f"\n  执行完成后运行: dqg-run {args.project_id} finalize {args.phase}")

    return result.exit_code


def cmd_finalize(args, output_dir: Path) -> int:
    import dqg.runtime  # noqa: F401 — 触发 handler 注册
    from dqg.memory.version_tracker import format_version_diff
    from dqg.quality.golden_sample import format_golden_diff
    from dqg.quality.rule_compliance import format_compliance_report
    from dqg.reporting.perf_tracker import format_metrics_report
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.phase_runtime import runtime_finalize
    from dqg.skill_tracker import format_quality_report

    ctx = ExecutionContext(
        output_dir=output_dir,
        project_id=args.project_id,
        phase_id=args.phase,
    )

    result = runtime_finalize(ctx)

    for event in result.events:
        if event.event_type.value == "error":
            print(f"  {event.message}", file=sys.stderr)
        elif event.event_type.value == "warning":
            print(f"  WARNING: {event.message}", file=sys.stderr)
        elif event.event_type.value == "finalize_blocked":
            pass
        elif event.event_type.value == "validation_completed":
            ve = event.data.get("validation_errors", [])
            if ve:
                print(f"  Schema 校验发现 {len(ve)} 个问题:")
                for v in ve[:5]:
                    print(f"    - {v}")
        elif event.event_type.value == "memory_indexed":
            print(f"\n  结构化事实索引: {event.data.get('facts', 0)} 条已存入 FTS5")
        elif event.event_type.value == "review_chain_ready":
            print("\n  评审链 prompt 已生成")
            print("  请用 AI IDE 读取该文件，一次性完成 Judge + Critique + Preference")

    if not result.success:
        return result.exit_code

    print(f"\n  Phase {args.phase} 已完成，等待 review")

    shared = ctx.shared
    if shared.get("auto_bug_cases"):
        cases = shared["auto_bug_cases"]
        print(f"  自动生成 {len(cases)} 条 bug case")
        for fix in shared.get("prompt_fixes", []):
            print(f"    建议修改: {fix['file']} ({fix['case_count']} 条)")

    # --- 成功静默：详细报告写文件，stdout 只输出失败/警告 + 摘要行 ---
    verbose_lines: list[str] = []

    quality_report = shared.get("quality_report")
    if quality_report:
        verbose_lines.append(format_quality_report(quality_report))

    perf_metrics = shared.get("perf_metrics")
    if perf_metrics:
        verbose_lines.append(format_metrics_report(perf_metrics))

    index_result = shared.get("index_result", {})
    version_diff = index_result.get("version_diff")
    if version_diff:
        verbose_lines.append(format_version_diff(version_diff))

    golden_diff = shared.get("golden_diff")
    if golden_diff:
        verbose_lines.append(format_golden_diff(golden_diff))

    compliance = shared.get("compliance")
    compliance_text = ""
    if compliance:
        compliance_text = format_compliance_report(compliance)
        verbose_lines.append(compliance_text)

    # 写入详细报告文件（供人类查看）
    if verbose_lines:
        from dqg.core.state_machine import PHASE_DEFS
        from dqg.core.state_machine import phase_dir as _pd

        phase_def = PHASE_DEFS.get(args.phase)
        if phase_def:
            internal = _pd(output_dir, args.project_id, phase_def) / "_internal"
            internal.mkdir(parents=True, exist_ok=True)
            (internal / "_finalize_report.txt").write_text(
                "\n\n".join(verbose_lines),
                encoding="utf-8",
            )

    # stdout 只输出：规则未达标项 + 耗时 + approve 命令
    if compliance:
        failed_rules = [r for r in compliance.get("rules", []) if r and not r.get("ok")]
        if failed_rules:
            total = len(compliance.get("rules", []))
            passed = total - len(failed_rules)
            print(f"\n    规则执行率 — Phase {args.phase}")
            print(f"  达标: {passed}/{total} ({passed / total:.0%})" if total else "")
            print(f"  未达标 ({len(failed_rules)} 项):")
            for r in failed_rules:
                print(f"    [{r.get('category', '?')}] {r.get('name', '?')}: {r.get('detail', '')}")
        else:
            total = len([r for r in compliance.get("rules", []) if r])
            print(f"\n    规则执行率 — Phase {args.phase}")
            print(f"  达标: {total}/{total} (100%)")

    duration = shared.get("duration_seconds")
    if duration:
        print(f"  耗时: {duration:.0f}s")

    print(f"\n  确认通过: dqg-run {args.project_id} approve {args.phase}")
    print("\n  Context 管理: 本 Phase 消耗了大量 context，建议运行 /compact")

    # 触发 observe 指标更新，保持 dashboard 数据实时
    try:
        from datetime import date as _date

        from dqg.reporting.observability import generate_report

        generate_report(
            output_dir,
            period_name="daily",
            anchor=_date.today(),
            project_filter=args.project_id,
        )
    except Exception:
        pass  # observe 是增强，不阻断主流程

    _flush_events()
    return 0


def cmd_approve(args, output_dir: Path) -> int:
    from dqg.quality.judge import load_judge_result
    from dqg.skill_tracker import extract_judge_cases

    state = load_state(output_dir, args.project_id)
    comment = args.comment or ""

    judge_result = load_judge_result(output_dir, args.project_id, args.phase)
    if not judge_result:
        print(
            f"\n  ❌ 未找到 Phase {args.phase} 的 Judge 评审结果。\n"
            f"  请先执行 finalize 生成评审结果后再 approve。\n"
            f"  命令: dqg-run {args.project_id} finalize {args.phase}",
            file=sys.stderr,
        )
        return 1

    if judge_result.get("verdict") == "HARD_BLOCK" or judge_result.get("hard_blocked"):
        print(
            f"\n  🚫 Judge 评审被 Anti-Rationalization Guard 硬拦截。\n"
            f"  原因: {judge_result.get('block_reason', '放水行为确认')}\n"
            f"  检测到的放水内容:\n"
            + "\n".join(f"    - {r}" for r in judge_result.get("confirmed_rationalizations", []))
            + "\n\n  请重新执行 finalize 触发 Judge 重新评审。",
            file=sys.stderr,
        )
        return 1

    dim_scores = {
        d["id"]: d["score"] / d.get("max_score", 5) * 5
        for d in judge_result.get("dimensions", [])
        if "id" in d and "score" in d
    }
    record_judge_score(
        state,
        args.phase,
        overall_score=judge_result.get("overall_score", 0.0),
        dimension_scores=dim_scores,
        judged_at=judge_result.get("judged_at"),
    )

    ps_pre = state.phases.get(args.phase)
    force = getattr(args, "force", False)
    if ps_pre and ps_pre.judge_score is not None and not ps_pre.judge_passed and not force:
        print(f"\n  ⚠️  Judge 评分 {ps_pre.judge_score:.1f}/5 未达标（阈值 3.5）", file=sys.stderr)
        top_issues = judge_result.get("top_issues", []) if judge_result else []
        for issue in top_issues[:3]:
            print(f"    - {issue}", file=sys.stderr)
        print(f"\n  使用 --force 强制通过: dqg-run {args.project_id} approve {args.phase} --force", file=sys.stderr)
        return 1

    from dqg.runtime.phase_contract import enforce_phase_constraints

    violations = enforce_phase_constraints(output_dir, args.project_id, args.phase)
    blocking = [v for v in violations if v.get("block_if_fail")]
    if blocking:
        print("\n  🚫 Phase Contract 约束未满足，approve 被阻断：", file=sys.stderr)
        for v in blocking:
            actual_str = "N/A" if v.get("actual") is None else str(v["actual"])
            reason = f" ({v['reason']})" if v.get("reason") else ""
            print(f"    ✗ {v['label']}: 实际值 {actual_str} {v['op']} {v['threshold']} 不满足{reason}", file=sys.stderr)
        print("\n  Phase Contract 是硬约束，--force 无法绕过。请修复问题后重新 finalize。", file=sys.stderr)
        return 1

    errors = approve_phase(state, args.phase, comment)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    save_state(output_dir, state)
    _, append_record, _ = _telemetry()
    from dqg.reporting.telemetry import PhaseRunRecord

    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=PHASE_DEFS[args.phase]["name"],
            action="approve",
            status="approved",
            comment=comment,
        ),
    )

    print(f"\n  Phase {args.phase} 已 approved")
    _emit_cmd(
        output_dir,
        args.project_id,
        args.phase,
        "phase_approved",
        f"Phase {args.phase} approved",
        action="approve",
        comment=comment,
    )
    if judge_result:
        ps = state.phases[args.phase]
        passed_str = "✅ PASS" if ps.judge_passed else "⚠️  FAIL (--force)"
        print(f"  Judge 评分: {ps.judge_score:.1f}/5 {passed_str}")
        new_cases = extract_judge_cases(args.project_id, args.phase, judge_result)
        if new_cases:
            print(f"  飞轮: 已提取 {len(new_cases)} 条 judge issue → failure-library")

    available = get_available_phases(state)
    if available:
        groups = get_parallel_groups(state)
        print("\n  下一步可执行:")
        for group in groups:
            if len(group) > 1:
                cmds = " & ".join(f"dqg-run {args.project_id} execute {pid}" for pid in group)
                print(f"    [并行] {cmds}")
            else:
                print(f"    dqg-run {args.project_id} execute {group[0]}")
    _flush_events()
    return 0


def cmd_skip(args, output_dir: Path) -> int:
    state = load_state(output_dir, args.project_id)
    comment = args.comment or "skipped"
    errors = skip_phase(state, args.phase, comment)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1
    save_state(output_dir, state)
    _, append_record, _ = _telemetry()
    from dqg.reporting.telemetry import PhaseRunRecord

    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=PHASE_DEFS[args.phase]["name"],
            action="skip",
            status="skipped",
            comment=comment,
        ),
    )
    print(f"\n  Phase {args.phase} 已跳过")
    _emit_cmd(
        output_dir,
        args.project_id,
        args.phase,
        "phase_skipped",
        f"Phase {args.phase} skipped",
        action="skip",
        comment=comment,
    )
    return 0
