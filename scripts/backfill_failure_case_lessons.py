#!/usr/bin/env python3
"""T4: 为 regression/failure-library 下 case.json 批量补齐 lesson 与 case_category.

用法:
  python scripts/backfill_failure_case_lessons.py --dry-run          # 仅统计
  python scripts/backfill_failure_case_lessons.py --apply            # 写回文件
  python scripts/backfill_failure_case_lessons.py --apply --limit 100

默认仓库根目录为包含 qualix/ 的 cwd；若在 qualix 子目录内运行会自动上探。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here.parent, here.parent.parent]:
        if (p / "src" / "qualix").is_dir() and (p / "regression" / "failure-library").is_dir():
            return p
    return here.parent


def main() -> int:
    root = _repo_root()
    sys.path.insert(0, str(root / "src"))

    from qualix.tracking.case_category import CASE_CATEGORIES, infer_case_category
    from qualix.tracking.lesson_inference import infer_lesson_with_fallback

    ap = argparse.ArgumentParser(description="Backfill failure-library case.json lesson + case_category")
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    ap.add_argument("--apply", action="store_true", help="写回 case.json")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 个目录（0=不限制）")
    args = ap.parse_args()

    cases_root = root / "regression" / "failure-library" / "cases"
    if not cases_root.is_dir():
        print(f"ERROR: cases root not found: {cases_root}", file=sys.stderr)
        return 2

    stats = {
        "scanned": 0,
        "updated_lesson": 0,
        "updated_category": 0,
        "skipped_has_both": 0,
    }
    n = 0

    for phase_dir in sorted(cases_root.iterdir()):
        if not phase_dir.is_dir():
            continue
        for case_dir in sorted(phase_dir.iterdir()):
            if args.limit and n >= args.limit:
                break
            path = case_dir / "case.json"
            if not path.is_file():
                continue
            stats["scanned"] += 1
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARN skip {path}: {e}", file=sys.stderr)
                continue

            changed = False
            lesson = (data.get("lesson") or "").strip()
            if not lesson:
                data["lesson"] = infer_lesson_with_fallback(data)
                stats["updated_lesson"] += 1
                changed = True

            cat = (data.get("case_category") or "").strip()
            if cat not in CASE_CATEGORIES:
                data["case_category"] = infer_case_category(data)
                stats["updated_category"] += 1
                changed = True

            if not changed:
                stats["skipped_has_both"] += 1
            elif args.apply:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            n += 1
        if args.limit and n >= args.limit:
            break

    print(json.dumps({**stats, "apply": bool(args.apply)}, ensure_ascii=False, indent=2))
    if args.dry_run or not args.apply:
        print("(使用 --apply 写回文件；未指定 --dry-run 且未 --apply 时仅统计)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
