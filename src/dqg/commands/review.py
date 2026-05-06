"""评审命令：judge / critique / preference / golden."""

from __future__ import annotations

import sys
from pathlib import Path

from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir


def cmd_judge(args, output_dir: Path) -> int:
    from dqg.quality.judge import format_judge_summary, load_judge_result, write_judge_prompt

    result = load_judge_result(output_dir, args.project_id, args.phase)
    if result:
        print(f"\n  {format_judge_summary(result)}")
        return 0
    judge_path = write_judge_prompt(output_dir, args.project_id, args.phase)
    if not judge_path:
        print(f"  Phase {args.phase} 不支持 Judge 评审", file=sys.stderr)
        return 1
    print(f"\n  Judge 评审 prompt 已生成: {judge_path}")
    print("  请用 AI IDE 读取该文件执行评审")
    return 0


def cmd_critique(args, output_dir: Path) -> int:
    from dqg.quality.critique import write_critique_prompt, write_preference_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  未知的 Phase: {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    critique_result = pd / "_critique.json"

    if critique_result.exists():
        print(f"\n  Self-Critique 结果已存在: {critique_result}")
        if any(pd.glob("*_v2.*")):
            pref_path = write_preference_prompt(output_dir, args.project_id, args.phase)
            if pref_path:
                print(f"  v2 修正版本已生成，Preference 比较 prompt: {pref_path}")
        else:
            print("  未发现 v2 修正版本，请先按 _critique_prompt.md 执行修正")
        return 0

    critique_path = write_critique_prompt(output_dir, args.project_id, args.phase)
    if not critique_path:
        print(f"  Phase {args.phase} 不支持 Self-Critique", file=sys.stderr)
        return 1
    print(f"\n  Self-Critique prompt 已生成: {critique_path}")
    return 0


def cmd_preference(args, output_dir: Path) -> int:
    from dqg.quality.critique import persist_preference, write_preference_prompt

    phase_def = PHASE_DEFS.get(args.phase)
    if not phase_def:
        print(f"  未知的 Phase: {args.phase}", file=sys.stderr)
        return 1

    pd = _phase_dir(output_dir, args.project_id, phase_def)
    if (pd / "_preference.json").exists():
        result = persist_preference(output_dir, args.project_id, args.phase)
        if result:
            print(f"\n  偏好判定: {result['preferred']} (confidence: {result['confidence']})")
            if result["persisted_cases"]:
                print(f"  已沉淀 {len(result['persisted_cases'])} 条有效 critique 为 bug case")
        return 0

    pref_path = write_preference_prompt(output_dir, args.project_id, args.phase)
    if not pref_path:
        print(f"  Phase {args.phase} 不支持 Preference 比较", file=sys.stderr)
        return 1
    print(f"\n  Preference 比较 prompt 已生成: {pref_path}")
    return 0


def cmd_golden(args, output_dir: Path) -> int:
    from dqg.quality.golden_sample import compare_with_golden, format_golden_diff, save_golden

    base_dir = Path(args.base_dir).resolve()
    if getattr(args, "save", False):
        path = save_golden(output_dir, args.project_id, args.phase, base_dir)
        if path:
            print(f"  Golden sample 已保存: {path}")
        else:
            print(f"  保存失败：Phase {args.phase} 无产物", file=sys.stderr)
            return 1
    else:
        diff = compare_with_golden(output_dir, args.project_id, args.phase, base_dir)
        print(format_golden_diff(diff))
    return 0
