"""评审命令：judge / critique / preference / golden."""

from __future__ import annotations

import sys
from pathlib import Path

from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir


def _judge_replay(output_dir: Path, project_id: str, phase_id: str, model: str | None) -> dict:
    """重跑 Judge 并与历史 _judge_iter*.json 对比，返回 drift 报告."""
    from dqg.constants import DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL, REPORT_MAP
    from dqg.json_utils import load_json
    from dqg.quality.judge import build_judge_prompt
    from dqg.quality.judge.judge_runner import JudgeRunner

    phase_def = PHASE_DEFS.get(phase_id, {})
    pd = _phase_dir(output_dir, project_id, phase_def)

    # 读所有历史迭代日志，取最高 N 轮作为"历史基准"
    iter_files = sorted(pd.glob("_judge_iter*.json"), key=lambda p: p.name)
    if not iter_files:
        return {"error": f"No _judge_iter*.json found in {pd}", "drift_status": "NO_HISTORY"}

    historical = load_json(iter_files[-1]) or {}
    hist_consensus = historical.get("consensus", "UNKNOWN")
    hist_avg_score = float(historical.get("avg_score", 0.0))
    hist_iter = historical.get("iteration", len(iter_files))

    report_file = REPORT_MAP.get(phase_id)
    if not report_file:
        return {"error": f"No REPORT_MAP entry for {phase_id}", "drift_status": "NO_HISTORY"}
    report_path = pd / report_file
    if not report_path.exists():
        return {"error": f"Report not found: {report_path}", "drift_status": "NO_HISTORY"}

    judge_build = build_judge_prompt(output_dir, project_id, phase_id)
    rubric = judge_build.prompt if judge_build else ""

    runner = JudgeRunner()
    result = runner.run(
        phase=phase_id,
        report_path=str(report_path),
        output_dir=str(output_dir),
        model=model or DEFAULT_JUDGE_MODEL,
        fallback=DEFAULT_FALLBACK_MODEL,
        rubric=rubric,
    )

    new_verdict = result.verdict
    new_score = result.overall_score
    was_pass = hist_consensus in ("PASS", "PASS_WITH_CONCERNS")
    is_pass = new_verdict in ("PASS", "PASS_WITH_CONCERNS")
    score_drift = abs(new_score - hist_avg_score)

    if was_pass and not is_pass:
        drift_status = "REGRESSION"
    elif not was_pass and is_pass:
        drift_status = "IMPROVEMENT"
    elif score_drift >= 0.5:
        drift_status = "DRIFT"
    else:
        drift_status = "MATCH"

    return {
        "phase": phase_id,
        "historical": {"iteration": hist_iter, "consensus": hist_consensus, "avg_score": round(hist_avg_score, 2)},
        "current": {"verdict": new_verdict, "score": round(new_score, 2), "model": result.model},
        "score_drift": round(score_drift, 2),
        "drift_status": drift_status,
    }


def cmd_judge(args, output_dir: Path) -> int:
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.quality.judge import format_judge_summary, load_judge_result, write_judge_prompt

    # --replay 模式：重跑 Judge，检测 rubric/harness 漂移
    if getattr(args, "replay", False):
        model = getattr(args, "model", None)
        replay_result = _judge_replay(output_dir, args.project_id, args.phase, model)
        drift_status = replay_result.get("drift_status", "UNKNOWN")
        exit_code = 1 if drift_status == "REGRESSION" else 0
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="judge",
                    project_id=args.project_id,
                    success=exit_code == 0,
                    exit_code=exit_code,
                    phase_id=args.phase,
                    extra={"replay": replay_result},
                )
            )
        else:
            ds = replay_result.get("drift_status", "UNKNOWN")
            hist = replay_result.get("historical", {})
            curr = replay_result.get("current", {})
            icon = {"MATCH": "✅", "DRIFT": "⚠️", "REGRESSION": "🚨", "IMPROVEMENT": "📈"}.get(ds, "❓")
            print(f"\n  {icon} Judge Replay — {args.phase}: {ds}")
            if "error" in replay_result:
                print(f"  {replay_result['error']}")
            else:
                print(f"  历史: iter{hist.get('iteration')} {hist.get('consensus')} {hist.get('avg_score')}/5")
                print(f"  当前: {curr.get('verdict')} {curr.get('score')}/5 ({curr.get('model')})")
                print(f"  分数漂移: {replay_result.get('score_drift')}")
        return exit_code

    result = load_judge_result(output_dir, args.project_id, args.phase)
    if result:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="judge",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    phase_id=args.phase,
                    extra={"judge_result": result},
                )
            )
        else:
            print(f"\n  {format_judge_summary(result)}")
        return 0
    judge_path = write_judge_prompt(output_dir, args.project_id, args.phase)
    if not judge_path:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="judge",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unsupported_phase"},
                )
            )
        else:
            print(f"  Phase {args.phase} 不支持 Judge 评审", file=sys.stderr)
        return 1
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="judge",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                phase_id=args.phase,
                extra={"prompt_generated": True, "judge_prompt_path": str(judge_path)},
            )
        )
    else:
        print(f"\n  Judge 评审 prompt 已生成: {judge_path}")
        print("  请用 AI IDE 读取该文件执行评审")
    return 0


def cmd_critique(args, output_dir: Path) -> int:
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.quality.critique import write_critique_prompt, write_preference_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="critique",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unknown_phase"},
                )
            )
        else:
            print(f"  未知的 Phase: {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    critique_result = pd / "_critique.json"

    if critique_result.exists():
        pref_path = None
        if any(pd.glob("*_v2.*")):
            pref_path = write_preference_prompt(output_dir, args.project_id, args.phase)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="critique",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    phase_id=args.phase,
                    extra={
                        "critique_result_path": str(critique_result),
                        "has_v2": any(pd.glob("*_v2.*")),
                        "preference_prompt_path": str(pref_path) if pref_path else None,
                    },
                )
            )
        else:
            print(f"\n  Self-Critique 结果已存在: {critique_result}")
            if pref_path:
                print(f"  v2 修正版本已生成，Preference 比较 prompt: {pref_path}")
            else:
                print("  未发现 v2 修正版本，请先按 _critique_prompt.md 执行修正")
        return 0

    critique_path = write_critique_prompt(output_dir, args.project_id, args.phase)
    if not critique_path:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="critique",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unsupported_phase"},
                )
            )
        else:
            print(f"  Phase {args.phase} 不支持 Self-Critique", file=sys.stderr)
        return 1
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="critique",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                phase_id=args.phase,
                extra={"critique_prompt_path": str(critique_path)},
            )
        )
    else:
        print(f"\n  Self-Critique prompt 已生成: {critique_path}")
    return 0


def cmd_preference(args, output_dir: Path) -> int:
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.quality.critique import persist_preference, write_preference_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="preference",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unknown_phase"},
                )
            )
        else:
            print(f"  未知的 Phase: {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    if (pd / "_preference.json").exists():
        result = persist_preference(output_dir, args.project_id, args.phase)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="preference",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    phase_id=args.phase,
                    extra={"persist_result": result},
                )
            )
        elif result:
            print(f"\n  偏好判定: {result['preferred']} (confidence: {result['confidence']})")
            if result.get("persisted_cases"):
                print(f"  已沉淀 {len(result['persisted_cases'])} 条有效 critique 为 bug case")
        return 0

    pref_path = write_preference_prompt(output_dir, args.project_id, args.phase)
    if not pref_path:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="preference",
                    project_id=args.project_id,
                    success=False,
                    exit_code=1,
                    phase_id=args.phase,
                    extra={"error": "unsupported_phase"},
                )
            )
        else:
            print(f"  Phase {args.phase} 不支持 Preference 比较", file=sys.stderr)
        return 1
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="preference",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                phase_id=args.phase,
                extra={"preference_prompt_path": str(pref_path)},
            )
        )
    else:
        print(f"\n  Preference 比较 prompt 已生成: {pref_path}")
    return 0


def cmd_golden(args, output_dir: Path) -> int:
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.quality.golden_sample import compare_with_golden, format_golden_diff, save_golden

    base_dir = Path(args.base_dir).resolve()
    if getattr(args, "save", False):
        path = save_golden(output_dir, args.project_id, args.phase, base_dir)
        if path:
            if cli_json_mode(args):
                print_cli_json(
                    cli_envelope(
                        command="golden",
                        project_id=args.project_id,
                        success=True,
                        exit_code=0,
                        phase_id=args.phase,
                        extra={"action": "save", "golden_path": str(path)},
                    )
                )
            else:
                print(f"  Golden sample 已保存: {path}")
        else:
            if cli_json_mode(args):
                print_cli_json(
                    cli_envelope(
                        command="golden",
                        project_id=args.project_id,
                        success=False,
                        exit_code=1,
                        phase_id=args.phase,
                        extra={"action": "save", "error": "no_artifacts"},
                    )
                )
            else:
                print(f"  保存失败：Phase {args.phase} 无产物", file=sys.stderr)
            return 1
    else:
        diff = compare_with_golden(output_dir, args.project_id, args.phase, base_dir)
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command="golden",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    phase_id=args.phase,
                    extra={"action": "compare", "diff": diff},
                )
            )
        else:
            print(format_golden_diff(diff))
    return 0
