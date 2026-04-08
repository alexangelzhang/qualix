"""Phase 核心命令：execute / finalize / approve / skip / auto."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dqg.core.state_machine import (
    PHASE_DEFS,
    PhaseStatus,
    approve_phase,
    execute_phase,
    finalize_phase,
    get_available_phases,
    get_parallel_groups,
    load_state,
    record_judge_score,
    save_state,
    skip_phase,
)
from dqg.core.state_machine import (
    internal_dir as _internal_dir,
)
from dqg.core.state_machine import (
    phase_dir as _phase_dir,
)
from dqg.reporting.telemetry import PhaseRunRecord, append_record, print_run_summary
from dqg.services.phase_service import (
    profile_context_warnings as _profile_context_warnings,
)
from dqg.services.phase_service import (
    write_phase_profile_manifest,
)


def profile_context_warnings(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """向后兼容：保留 commands.phase 的旧导出。"""
    return _profile_context_warnings(output_dir, project_id, phase_id)


def cmd_execute(args, output_dir: Path) -> int:
    from dqg.context.context_loader import load_context
    from dqg.context.diff_context import collect_diff_context, write_diff_context
    from dqg.context.doc_summary import generate_summary_file
    from dqg.context.weak_assert_context import collect_weak_assert_context, write_weak_assert_context
    from dqg.core.profiles import get_profile

    state = load_state(output_dir, args.project_id)
    state.profile_id = get_profile(getattr(args, "profile", None)).profile_id
    errors = execute_phase(state, args.phase)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    save_state(output_dir, state)
    phase_def = PHASE_DEFS[args.phase]
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=phase_def["name"],
            action="execute",
            status="in_progress",
            started_at=state.phases[args.phase].started_at,
        ),
    )

    print(f"\n  Phase {args.phase}({phase_def['name']}) 已启动")
    print(f"  Skill: {phase_def['skill']}")
    print(f"  Profile: {state.profile_id}")

    model_name = getattr(args, "model", None)
    ctx = load_context(output_dir, args.project_id, args.phase, model_name)
    ctx_text: str | None = None
    if ctx.chunks:
        print(f"\n  上下文已加载: {ctx.summary}")
        int_dir = _internal_dir(output_dir, args.project_id, phase_def)
        int_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = int_dir / "_upstream_context.md"
        ctx.write_full_text(ctx_path)
        ctx_text = ctx.relevance_seed
        print(f"  上下文文件: {ctx_path}")
        if ctx.truncated:
            print(f"  注意: 上下文已截断（超出 {ctx.model.name} 的 budget）")

    code_repo = getattr(args, "code_repo", None)
    if code_repo and args.phase in ("C", "D"):
        base_branch = getattr(args, "base_branch", "master")
        feature_branch = getattr(args, "feature_branch", "HEAD")
        diff_ctx = collect_diff_context(code_repo, base_branch, feature_branch)
        if diff_ctx.has_changes:
            diff_path = write_diff_context(output_dir, args.project_id, phase_def["dir_suffix"], diff_ctx)
            if diff_path:
                print(f"\n  增量分析: {diff_ctx.summary}")
                print(f"  Diff 上下文: {diff_path}")
        elif diff_ctx.error:
            print(f"\n  增量分析失败: {diff_ctx.error}")

        if args.phase == "C":
            weak_assert_payload = collect_weak_assert_context(code_repo, diff_ctx)
            weak_json_path, weak_md_path = write_weak_assert_context(
                output_dir,
                args.project_id,
                phase_def["dir_suffix"],
                weak_assert_payload,
            )
            print(f"  Weak assert sidecar: {weak_md_path} (json: {weak_json_path})")

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    summary_path = generate_summary_file(pd)
    if summary_path:
        print(f"\n  文档摘要已生成: {summary_path}")

    write_phase_profile_manifest(
        output_dir,
        args.project_id,
        args.phase,
        state.profile_id,
        relevance_text=ctx_text,
    )

    print(f"\n  执行完成后运行: dqg-run {args.project_id} finalize {args.phase}")
    return 0


def cmd_finalize(args, output_dir: Path) -> int:
    from dqg.memory.memory_layer import MemoryLayer
    from dqg.memory.version_tracker import format_version_diff
    from dqg.path_utils import resolve_internal_file
    from dqg.quality.critique import write_critique_prompt
    from dqg.quality.cross_phase_check import check_cross_phase_refs
    from dqg.quality.finalize_checks import run_finalize_checks
    from dqg.quality.golden_sample import compare_with_golden, format_golden_diff
    from dqg.quality.judge import write_judge_prompt
    from dqg.quality.review_chain import build_review_chain_payload, write_review_chain_prompt
    from dqg.quality.rule_compliance import compute_rule_compliance, format_compliance_report, persist_compliance
    from dqg.reporting.perf_tracker import collect_phase_metrics, format_metrics_report, persist_phase_metrics
    from dqg.schemas import validate_phase_output
    from dqg.skill_tracker import auto_generate_bug_case, format_quality_report, suggest_prompt_fix, track_rule_quality
    from dqg.text_utils import REPORT_MAP

    state = load_state(output_dir, args.project_id)

    validation_errors = validate_phase_output(output_dir, args.project_id, args.phase) or []
    ref_errors = check_cross_phase_refs(output_dir, args.project_id)
    if ref_errors:
        validation_errors.extend(ref_errors)

    hard_errors = run_finalize_checks(output_dir, args.project_id, args.phase)
    blocked = [e for e in hard_errors if e.startswith("BLOCKED")]
    if blocked:
        for e in hard_errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    regression_warnings = [e for e in hard_errors if e.startswith("REGRESSION")]
    if regression_warnings:
        for w in regression_warnings:
            print(f"  WARNING: {w}", file=sys.stderr)
        validation_errors.extend(regression_warnings)

    errors = finalize_phase(state, args.phase, validation_errors)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    save_state(output_dir, state)
    ps = state.phases[args.phase]
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=PHASE_DEFS[args.phase]["name"],
            action="finalize",
            status="pending_review",
            started_at=ps.started_at,
            finished_at=ps.finished_at,
            duration_seconds=ps.duration_seconds,
            validation_errors=validation_errors,
        ),
    )

    phase_def = PHASE_DEFS[args.phase]
    perf_metrics = collect_phase_metrics(output_dir, args.project_id, args.phase, ps.duration_seconds)
    if perf_metrics:
        persist_phase_metrics(output_dir, perf_metrics)
        int_dir = _internal_dir(output_dir, args.project_id, phase_def)
        int_dir.mkdir(parents=True, exist_ok=True)
        (int_dir / "_perf_metrics.json").write_text(
            json.dumps(perf_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"\n  Phase {args.phase} 已完成，等待 review")
    if validation_errors:
        print(f"  Schema 校验发现 {len(validation_errors)} 个问题:")
        for ve in validation_errors[:5]:
            print(f"    - {ve}")
        auto_cases = auto_generate_bug_case(args.project_id, args.phase, validation_errors)
        if auto_cases:
            print(f"  自动生成 {len(auto_cases)} 条 bug case")
            fixes = suggest_prompt_fix(auto_cases)
            for fix in fixes:
                print(f"    建议修改: {fix['file']} ({fix['case_count']} 条)")

    quality_report = track_rule_quality(output_dir, args.project_id, args.phase)
    if quality_report["matched_signals"] or quality_report["potential_new_issues"]:
        print(f"\n  {format_quality_report(quality_report)}")

    if perf_metrics:
        print(f"\n  {format_metrics_report(perf_metrics)}")

    memory = MemoryLayer(output_dir)
    index_result = memory.index_phase(args.project_id, args.phase)
    if index_result.get("skipped"):
        print("\n  结构化索引: 输入未变化，跳过重建")
    elif index_result.get("facts"):
        print(f"\n  结构化事实索引: {index_result['facts']} 条已存入 FTS5")

    version_diff = index_result.get("version_diff")
    if version_diff:
        print(f"\n  {format_version_diff(version_diff)}")

    base_dir = Path(args.base_dir).resolve() if hasattr(args, "base_dir") else output_dir.parent
    golden_diff = compare_with_golden(output_dir, args.project_id, args.phase, base_dir)
    print(f"\n  {format_golden_diff(golden_diff)}")

    compliance = compute_rule_compliance(output_dir, args.project_id, args.phase)
    if compliance:
        persist_compliance(output_dir, compliance)
        print(f"\n  {format_compliance_report(compliance)}")

    # Profile 上下文警告
    report_file = REPORT_MAP.get(args.phase)
    if report_file:
        pd = _phase_dir(output_dir, args.project_id, phase_def)
        profile_ctx_path = resolve_internal_file(pd, "_profile_context.md")
        if not profile_ctx_path.exists():
            print(f"  Profile 上下文提醒: 缺少 {profile_ctx_path}")
        report_path = pd / report_file
        if report_path.exists() and "## PROFILE_CONTEXT" not in report_path.read_text(encoding="utf-8"):
            print("  Profile 上下文提醒: 报告未包含 PROFILE_CONTEXT")

    if ps.duration_seconds:
        print(f"  耗时: {ps.duration_seconds:.0f}s")

    review_payload = build_review_chain_payload(output_dir, args.project_id, args.phase)
    chain_path = write_review_chain_prompt(
        output_dir,
        args.project_id,
        args.phase,
        prompt=review_payload["review_chain_prompt"] if review_payload else None,
    )
    if chain_path:
        print(f"\n  评审链 prompt 已生成: {chain_path}")
        print("  请用 AI IDE 读取该文件，一次性完成 Judge + Critique + Preference")

    write_judge_prompt(
        output_dir,
        args.project_id,
        args.phase,
        prompt=review_payload["judge_prompt"] if review_payload else None,
    )
    write_critique_prompt(
        output_dir,
        args.project_id,
        args.phase,
        prompt=review_payload["critique_prompt"] if review_payload else None,
    )

    print(f"\n  确认通过: dqg-run {args.project_id} approve {args.phase}")
    return 0


def cmd_approve(args, output_dir: Path) -> int:
    from dqg.quality.judge import load_judge_result
    from dqg.skill_tracker import extract_judge_cases

    state = load_state(output_dir, args.project_id)
    comment = args.comment or ""

    judge_result = load_judge_result(output_dir, args.project_id, args.phase)
    if judge_result:
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

    errors = approve_phase(state, args.phase, comment)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    save_state(output_dir, state)
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
    return 0


def collect_inputs(project_id: str, phase_id: str, output_dir: Path) -> dict[str, str] | None:
    """交互式收集 Phase 所需的输入材料."""
    phase_def = PHASE_DEFS[phase_id]
    required = phase_def.get("required_inputs", [])
    optional = phase_def.get("optional_inputs", [])
    if not required and not optional:
        return {}

    print(f"\n  Phase {phase_id}({phase_def['name']}) 需要以下输入:")
    inputs: dict[str, str] = {}

    for inp in required:
        is_required = inp.get("required", True)
        print(f"  [{inp['label']}]{' *' if is_required else ''}")
        while True:
            try:
                value = input(f"    {inp['prompt']}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if value:
                inputs[inp["key"]] = value
                break
            if not is_required:
                break
            print("    (必填，请输入)")

    for inp in optional:
        print(f"  [{inp['label']}] (可选)")
        try:
            value = input(f"    {inp['prompt']}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if value:
            inputs[inp["key"]] = value

    if inputs:
        phase_dir = _phase_dir(output_dir, project_id, phase_def)
        phase_dir.mkdir(parents=True, exist_ok=True)
        int_dir = _internal_dir(output_dir, project_id, phase_def)
        int_dir.mkdir(parents=True, exist_ok=True)
        (int_dir / "_inputs.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8")
    return inputs


def prompt_approve(project_id: str, phase_id: str, phase_name: str) -> tuple[bool, str]:
    """交互式等待人工 approve."""
    phase_def = PHASE_DEFS[phase_id]
    print(f"\n  Phase {phase_id}({phase_name}) 等待 review")
    for d in phase_def.get("deliverables", []):
        print(f"    - {d}")
    for item in phase_def.get("approve_checklist", []):
        print(f"    [ ] {item}")
    print("\n  [a] approve  [s] skip  [q] 退出 auto 模式")
    while True:
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False, "interrupted"
        if choice in ("a", "approve", ""):
            comment = input("  备注 (回车跳过): ").strip()
            return True, comment
        if choice in ("s", "skip"):
            reason = input("  跳过原因: ").strip()
            return False, reason or "skipped in auto mode"
        if choice in ("q", "quit", "exit"):
            return False, "__quit__"
        print("  请输入 a/s/q")


def cmd_auto(args, output_dir: Path) -> int:
    """全自动推进 pipeline."""
    from dqg.commands.query import print_status
    from dqg.context.context_loader import load_context
    from dqg.core.profiles import get_profile
    from dqg.quality.cross_phase_check import check_cross_phase_refs
    from dqg.schemas import validate_phase_output

    state = load_state(output_dir, args.project_id)
    state.profile_id = get_profile(getattr(args, "profile", None)).profile_id
    save_state(output_dir, state)
    model_name = getattr(args, "model", None)
    skip_phases = set(args.skip) if hasattr(args, "skip") and args.skip else set()

    print()
    print("=" * 60)
    print(f"  Auto Pipeline — {args.project_id}")
    print("=" * 60)

    for skip_id in skip_phases:
        if state.phases.get(skip_id) and state.phases[skip_id].status == PhaseStatus.NOT_STARTED:
            skip_phase(state, skip_id, "skipped via auto --skip")
            save_state(output_dir, state)
            print(f"  Phase {skip_id} 已跳过")

    iteration = 0
    max_iterations = 20

    while iteration < max_iterations:
        iteration += 1
        groups = get_parallel_groups(state)
        if not groups:
            break

        for group in groups:
            if len(group) > 1:
                names = " + ".join(f"{pid}({PHASE_DEFS[pid]['name']})" for pid in group)
                print(f"\n  [并行执行] {names}")
            else:
                print(f"\n  [执行] Phase {group[0]}({PHASE_DEFS[group[0]]['name']})")

            for pid in group:
                inputs = collect_inputs(args.project_id, pid, output_dir)
                if inputs is None:
                    print("\n  Auto 模式中断")
                    return 1
                errors = execute_phase(state, pid)
                if errors:
                    print(f"  ERROR executing {pid}: {'; '.join(errors)}", file=sys.stderr)
                    continue
                save_state(output_dir, state)
                phase_def = PHASE_DEFS[pid]
                append_record(
                    output_dir,
                    PhaseRunRecord(
                        project_id=args.project_id,
                        phase_id=pid,
                        phase_name=phase_def["name"],
                        action="execute",
                        status="in_progress",
                        started_at=state.phases[pid].started_at,
                    ),
                )
                ctx = load_context(output_dir, args.project_id, pid, model_name)
                ctx_text: str | None = None
                if ctx.chunks:
                    int_dir = _internal_dir(output_dir, args.project_id, phase_def)
                    int_dir.mkdir(parents=True, exist_ok=True)
                    ctx_path = int_dir / "_upstream_context.md"
                    ctx.write_full_text(ctx_path)
                    ctx_text = ctx.relevance_seed
                    print(f"    上下文: {ctx.summary}")
                write_phase_profile_manifest(
                    output_dir,
                    args.project_id,
                    pid,
                    state.profile_id,
                    relevance_text=ctx_text,
                )
                print(f"    Skill: {phase_def['skill']}")
                print(f"    请执行 Phase {pid} 的 skill，完成后按回车继续...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Auto 模式中断")
                    return 1

            for pid in group:
                if state.phases[pid].status != PhaseStatus.IN_PROGRESS:
                    continue
                validation_errors = validate_phase_output(output_dir, args.project_id, pid) or []
                ref_errors = check_cross_phase_refs(output_dir, args.project_id)
                if ref_errors:
                    validation_errors.extend(ref_errors)
                finalize_phase(state, pid, validation_errors)
                save_state(output_dir, state)
                ps = state.phases[pid]
                append_record(
                    output_dir,
                    PhaseRunRecord(
                        project_id=args.project_id,
                        phase_id=pid,
                        phase_name=PHASE_DEFS[pid]["name"],
                        action="finalize",
                        status="pending_review",
                        started_at=ps.started_at,
                        finished_at=ps.finished_at,
                        duration_seconds=ps.duration_seconds,
                        validation_errors=validation_errors,
                    ),
                )
                if validation_errors:
                    print(f"    Schema 校验: {len(validation_errors)} 个问题")
                if ps.duration_seconds:
                    print(f"    耗时: {ps.duration_seconds:.0f}s")

            for pid in group:
                if state.phases[pid].status != PhaseStatus.PENDING_REVIEW:
                    continue
                approved, comment = prompt_approve(args.project_id, pid, PHASE_DEFS[pid]["name"])
                if comment == "__quit__":
                    print("\n  Auto 模式退出")
                    print_status(state, output_dir)
                    return 0
                if approved:
                    approve_phase(state, pid, comment)
                    save_state(output_dir, state)
                    append_record(
                        output_dir,
                        PhaseRunRecord(
                            project_id=args.project_id,
                            phase_id=pid,
                            phase_name=PHASE_DEFS[pid]["name"],
                            action="approve",
                            status="approved",
                            comment=comment,
                        ),
                    )
                    print(f"    Phase {pid} ✅ approved")
                else:
                    skip_phase(state, pid, comment)
                    save_state(output_dir, state)
                    append_record(
                        output_dir,
                        PhaseRunRecord(
                            project_id=args.project_id,
                            phase_id=pid,
                            phase_name=PHASE_DEFS[pid]["name"],
                            action="skip",
                            status="skipped",
                            comment=comment,
                        ),
                    )
                    print(f"    Phase {pid} ⏭ skipped")

    print()
    print_status(state, output_dir)
    print_run_summary(output_dir, args.project_id)
    return 0
