"""qualix-run <pid> skill-evolve — 从 failure-library 提炼 skill 改进建议.

三个 action：
  analyze   分析全部（或指定）phase 的 top 失败模式，按 lesson 去重输出
  suggest   调用 skill_factory 生成建议文件（写到 output/_skill_factory/）
  apply     预览或写入 SKILL.md（--no-dry-run 才真正写盘）

典型用法：
  qualix-run mrs skill-evolve analyze
  qualix-run mrs skill-evolve suggest --phase Q03
  qualix-run mrs skill-evolve apply --phase Q03
  qualix-run mrs skill-evolve apply --phase Q03 --no-dry-run
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
from qualix.log import get_logger

log = get_logger(__name__)

# severity 排序（数字越小越高）
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ── analyze ───────────────────────────────────────────────────────────────────


def _dedup_by_lesson(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按 (phase, lesson) 去重，相同 lesson 只保留 severity 最高的一条。

    返回 {phase: [representative_case, ...]}，每个 phase 内按频次降序排列。
    """
    # lesson -> best representative
    best: dict[tuple[str, str], dict[str, Any]] = {}
    freq: dict[tuple[str, str], int] = Counter()

    for c in cases:
        phase = c.get("phase", "?")
        lesson = c.get("lesson", "").strip()
        if not lesson:
            continue
        key = (phase, lesson)
        freq[key] += 1
        existing = best.get(key)
        if existing is None:
            best[key] = c
        else:
            # 保留 severity 更高的代表
            if _SEV_ORDER.get(c.get("severity", "low"), 9) < _SEV_ORDER.get(
                existing.get("severity", "low"), 9
            ):
                best[key] = c

    # 按 phase 分组，按频次排序
    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (phase, _lesson), rep in best.items():
        by_phase[phase].append({**rep, "_freq": freq[(phase, rep.get("lesson", "").strip())]})

    for phase in by_phase:
        by_phase[phase].sort(key=lambda x: (-x["_freq"], x.get("case_id", "")))

    return dict(by_phase)


def _analyze(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.tracking.bug_cases import load_cases, load_cases_by_phase

    phase_filter = getattr(args, "phase", None)
    top_n = getattr(args, "top", 10)

    cases = load_cases_by_phase(phase_filter, exclude_holdout=True) if phase_filter else load_cases(exclude_holdout=True)
    if not cases:
        if cli_json_mode(args):
            print_cli_json(cli_envelope(command="skill-evolve analyze", project_id="", success=False, exit_code=1, extra={"error": "no cases found"}))
        else:
            print("No cases found in failure-library.")
        return 1

    by_phase = _dedup_by_lesson(cases)

    # 统计无 lesson 的案例（主要是 AUTO STRUCTURED_SCHEMA）
    no_lesson_by_phase: dict[str, int] = Counter(
        c.get("phase", "?") for c in cases if not c.get("lesson", "").strip()
    )
    fix_target_by_phase: dict[str, str] = {}
    for phase, reps in by_phase.items():
        targets = [r.get("fix_target", "") for r in reps if r.get("fix_target", "")]
        if targets:
            fix_target_by_phase[phase] = Counter(targets).most_common(1)[0][0]

    if cli_json_mode(args):
        payload: dict[str, Any] = {
            "total_cases": len(cases),
            "phases": {},
        }
        for phase in sorted(by_phase.keys()):
            reps = by_phase[phase]
            payload["phases"][phase] = {
                "deduped_lesson_count": len(reps),
                "no_lesson_count": no_lesson_by_phase.get(phase, 0),
                "top_fix_target": fix_target_by_phase.get(phase, ""),
                "top_lessons": [
                    {"lesson": r.get("lesson", ""), "freq": r["_freq"], "severity": r.get("severity", "")}
                    for r in reps[:top_n]
                ],
            }
        print_cli_json(cli_envelope(command="skill-evolve analyze", project_id="", success=True, exit_code=0, extra=payload))
    else:
        print(f"\n[skill-evolve analyze]  总案例: {len(cases)} 条\n")
        for phase in sorted(by_phase.keys()):
            reps = by_phase[phase]
            no_lesson = no_lesson_by_phase.get(phase, 0)
            fix = fix_target_by_phase.get(phase, "—")
            print(f"  Phase {phase}  去重后: {len(reps)} 条  |  无lesson(自动生成): {no_lesson} 条  |  主要修复目标: {fix}")
            for i, r in enumerate(reps[:top_n], 1):
                sev = r.get("severity", "")
                freq = r["_freq"]
                lesson = r.get("lesson", "")[:100]
                print(f"    {i:2}. [{sev:8}] ×{freq:3}  {lesson}")
            print()

    return 0


# ── suggest ───────────────────────────────────────────────────────────────────


def _suggest(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.tracking.skill_factory import write_all_skill_suggestions, write_skill_suggestions

    project_id = getattr(args, "project_id", "")
    phase_filter = getattr(args, "phase", None)

    if phase_filter:
        path = write_skill_suggestions(output_dir, project_id, phase_filter)
        results = {phase_filter: str(path) if path else None}
    else:
        paths = write_all_skill_suggestions(output_dir, project_id)
        # write_all_skill_suggestions 返回 list[Path]，通过文件名反推 phase
        results = {}
        for p in paths:
            # 文件名格式：_skill_suggestions_{phase}.md
            stem = p.stem  # e.g. _skill_suggestions_Q03
            phase = stem.replace("_skill_suggestions_", "")
            results[phase] = str(p)

    written = {ph: fp for ph, fp in results.items() if fp}
    skipped = [ph for ph, fp in results.items() if not fp]

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="skill-evolve suggest",
                project_id=project_id,
                success=True,
                exit_code=0,
                extra={"written": written, "skipped_phases": skipped},
            )
        )
    else:
        if written:
            print("\n[skill-evolve suggest]  生成建议文件：")
            for phase, fp in sorted(written.items()):
                print(f"  {phase}  →  {fp}")
        if skipped:
            print(f"\n  以下 Phase 无足够案例生成建议：{', '.join(sorted(skipped))}")
        if not written:
            print("\n[skill-evolve suggest]  未生成任何建议文件（案例不足或无 lesson）。")

    return 0


# ── apply ─────────────────────────────────────────────────────────────────────


def _apply(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.tracking.skill_auto_merge import apply_to_skill_file
    from qualix.tracking.skill_evolution import generate_skill_diff

    phase_filter = getattr(args, "phase", None)
    dry_run: bool = getattr(args, "dry_run", True)
    project_id = getattr(args, "project_id", "")

    from qualix.constants import SKILL_FILE_MAP

    phases = [phase_filter] if phase_filter else list(SKILL_FILE_MAP.keys())

    results: list[dict[str, Any]] = []
    for phase in phases:
        diff_result = generate_skill_diff(phase)
        if not diff_result:
            results.append({"phase": phase, "status": "no_diff", "applied": 0, "skipped": 0})
            continue

        auto_diffs = [d for d in diff_result.get("diffs", []) if d.get("auto_merge_suggested")]
        if not auto_diffs:
            results.append(
                {
                    "phase": phase,
                    "status": "no_high_confidence",
                    "total_diffs": diff_result.get("total_diffs", 0),
                    "applied": 0,
                    "skipped": 0,
                }
            )
            continue

        skill_path = diff_result.get("skill_file", "")
        changes = [d["content"] for d in auto_diffs]
        apply_result = apply_to_skill_file(skill_path, changes, dry_run=dry_run)

        results.append(
            {
                "phase": phase,
                "status": "dry_run" if dry_run else "applied",
                "skill_file": skill_path,
                "applied": len(apply_result.inserted_entries),
                "skipped_duplicates": len(apply_result.skipped_duplicates),
                "rendered_diff": apply_result.rendered_diff if dry_run else "",
            }
        )

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="skill-evolve apply",
                project_id=project_id,
                success=True,
                exit_code=0,
                extra={"dry_run": dry_run, "phases": results},
            )
        )
    else:
        mode_label = "[DRY-RUN]" if dry_run else "[APPLY]"
        print(f"\n[skill-evolve apply]  {mode_label}\n")
        for r in results:
            phase = r["phase"]
            status = r["status"]
            if status == "no_diff":
                print(f"  {phase}  — 无新增 diff（建议已在 SKILL.md 中或无案例）")
            elif status == "no_high_confidence":
                total = r.get("total_diffs", 0)
                print(f"  {phase}  — {total} 条 diff 但置信度不足（需 support_count >= 3）")
            else:
                applied = r.get("applied", 0)
                skipped = r.get("skipped_duplicates", 0)
                skill_file = r.get("skill_file", "")
                print(f"  {phase}  → {skill_file}")
                print(f"         新增: {applied} 条  |  已存在跳过: {skipped} 条")
                if dry_run and r.get("rendered_diff"):
                    print()
                    for line in r["rendered_diff"].splitlines():
                        print(f"    {line}")
                    print()
        if dry_run:
            print("\n  提示：加 --no-dry-run 真正写入 SKILL.md\n")

    return 0


# ── 入口 ──────────────────────────────────────────────────────────────────────


def cmd_skill_evolve(args: argparse.Namespace, output_dir: Path) -> int:
    action = getattr(args, "skill_action", "analyze")
    try:
        if action == "analyze":
            return _analyze(args, output_dir)
        if action == "suggest":
            return _suggest(args, output_dir)
        if action == "apply":
            return _apply(args, output_dir)
        print(f"Unknown action: {action}")
        return 1
    except Exception as e:
        if cli_json_mode(args):
            print_cli_json(
                cli_envelope(
                    command=f"skill-evolve {action}",
                    project_id=getattr(args, "project_id", ""),
                    success=False,
                    exit_code=1,
                    extra={"error": str(e)},
                )
            )
        else:
            log.error("skill-evolve %s failed: %s", action, e)
        return 1
