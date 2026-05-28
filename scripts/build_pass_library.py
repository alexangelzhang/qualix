#!/usr/bin/env python3.11
"""
build_pass_library.py — 从 output/ 目录的已完成项目构建 PASS case 库

PASS case 库的结构与 failure-library 对称：
  regression/pass-library/cases/{phase}/{case_id}/
    case.json   — error_type: "PASS", expected_verdict: "PASS"
    input.md    — 对应的 _judge_prompt.md

用法：
  python3 scripts/build_pass_library.py              # 构建所有 PASS case
  python3 scripts/build_pass_library.py --phase Q06  # 只构建 Q06
  python3 scripts/build_pass_library.py --dry-run    # 只打印不写
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
PASS_LIBRARY = PROJECT_ROOT / "regression" / "pass-library" / "cases"


def scan_pass_outputs(phase_filter: str | None) -> list[dict]:
    """扫描 output/ 中 gate_checklist 全通过的 judge 产出"""
    results = []
    for judge_prompt in sorted(OUTPUT_DIR.rglob("_judge_prompt.md")):
        if "_archive" in str(judge_prompt):
            continue
        phase_dir = judge_prompt.parent
        phase = phase_dir.name
        if phase_filter and phase != phase_filter:
            continue

        judge_result_path = phase_dir / "_judge_result.json"
        if not judge_result_path.exists():
            continue

        try:
            result = json.loads(judge_result_path.read_text())
        except Exception:
            continue

        checklist = result.get("gate_checklist", [])
        if not checklist:
            continue
        all_passed = all(item.get("passed", False) for item in checklist)
        if not all_passed:
            continue

        project = phase_dir.parent.name
        results.append(
            {
                "project_id": project,
                "phase": phase,
                "prompt_path": judge_prompt,
                "result_path": judge_result_path,
                "judged_at": result.get("judged_at", ""),
            }
        )
    return results


def build_case_id(project: str, phase: str, index: int) -> str:
    date = datetime.now().strftime("%Y%m%d")
    return f"PASS-{phase}-{project}-{date}-{index:02d}"


def build_pass_library(phase_filter: str | None, dry_run: bool) -> None:
    outputs = scan_pass_outputs(phase_filter)
    if not outputs:
        print("未找到符合条件的 PASS 产出")
        return

    print(f"找到 {len(outputs)} 个 PASS 产出\n")

    created = 0
    skipped = 0

    for i, out in enumerate(outputs):
        phase = out["phase"]
        project = out["project_id"]
        case_id = build_case_id(project, phase, i)

        dest_dir = PASS_LIBRARY / phase / case_id
        if dest_dir.exists():
            print(f"  ⏭  {case_id} 已存在，跳过")
            skipped += 1
            continue

        case_json = {
            "case_id": case_id,
            "phase": phase,
            "error_type": "PASS",
            "project_id": project,
            "source": "output_verified",
            "judged_at": out["judged_at"],
            "created_at": datetime.now().isoformat(),
            "status": "open",
            "expected_verdict": "PASS",
            "tags": ["pass-library", f"project:{project}"],
        }

        if dry_run:
            print(f"  [DRY] 会创建 {dest_dir.relative_to(PROJECT_ROOT)}")
            print(f"        input: {out['prompt_path'].relative_to(PROJECT_ROOT)}")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "case.json").write_text(
                json.dumps(case_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            shutil.copy(out["prompt_path"], dest_dir / "input.md")
            print(f"  ✅ 创建 {dest_dir.relative_to(PROJECT_ROOT)}")

        created += 1

    print(f"\n完成: 创建 {created} 个, 跳过 {skipped} 个")

    # 按 phase 汇总
    if not dry_run:
        print("\n当前 PASS library 统计:")
        for phase_dir in sorted(PASS_LIBRARY.iterdir()):
            if phase_dir.is_dir():
                count = sum(1 for d in phase_dir.iterdir() if d.is_dir())
                print(f"  {phase_dir.name}: {count} cases")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 PASS case 库")
    parser.add_argument("--phase", help="只构建指定 phase（如 Q06）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    build_pass_library(args.phase, args.dry_run)


if __name__ == "__main__":
    main()
