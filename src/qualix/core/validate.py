"""Phase 产物校验入口.

用法:
    qualix-validate <project_id> --phase A
    qualix-validate <project_id> --phase B
    qualix-validate <project_id> --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qualix.schemas import validate_phase_output


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Phase 产物是否符合数据契约")
    parser.add_argument("project_id", help="项目 ID")
    parser.add_argument("--phase", help="要校验的阶段 (A, A.5, A.6, B, C, D)")
    parser.add_argument("--all", action="store_true", help="校验所有已完成阶段")
    parser.add_argument("--base-dir", default=".", help="项目根目录")

    args = parser.parse_args()
    base_dir = Path(args.base_dir).resolve()
    output_dir = base_dir / "output"

    if not output_dir.exists():
        print(f"错误: output 目录不存在: {output_dir}", file=sys.stderr)
        return 1

    phases_to_check: list[str] = []
    if args.all:
        phases_to_check = ["Q01", "Q04", "Q03", "Q05", "Q05a", "Q05b", "Q06", "Q07"]
    elif args.phase:
        phases_to_check = [args.phase]
    else:
        print("错误: 请指定 --phase 或 --all", file=sys.stderr)
        return 1

    has_error = False
    for phase_id in phases_to_check:
        errors = validate_phase_output(output_dir, args.project_id, phase_id)
        if errors is None:
            print(f"  Phase {phase_id}: 未找到产物，跳过")
            continue
        if errors:
            has_error = True
            print(f"  Phase {phase_id}: FAIL")
            for err in errors:
                print(f"    - {err}")
        else:
            print(f"  Phase {phase_id}: PASS")

    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
