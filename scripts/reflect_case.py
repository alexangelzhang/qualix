#!/usr/bin/env python3
"""T10: 对已有 failure-library case 执行 Failure→Reflector 回流（lesson / case_category）。

调用 `dqg.tracking.case_reflect.apply_reflect_metadata`。默认 dry-run；`--apply` 写回。

用法:
  python scripts/reflect_case.py --dry-run
  python scripts/reflect_case.py --apply
  python scripts/reflect_case.py --apply --only-empty-lesson
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in (here.parent, here.parent.parent):
        if (p / "src" / "dqg").is_dir() and (p / "regression" / "failure-library").is_dir():
            return p
    return here.parent


def main() -> int:
    root = _repo_root()
    sys.path.insert(0, str(root / "src"))

    from dqg.constants import CASES_DIR
    from dqg.tracking.case_reflect import apply_reflect_metadata

    ap = argparse.ArgumentParser(description="Reflect lesson + case_category onto bug cases")
    ap.add_argument("--dry-run", action="store_true", help="只列出将变更的文件，不写盘")
    ap.add_argument("--apply", action="store_true", help="写回 case.json")
    ap.add_argument(
        "--only-empty-lesson",
        action="store_true",
        help="仅处理 lesson 为空的 case",
    )
    ap.add_argument("--limit", type=int, default=0, help="最多扫描 N 个 case.json（0=不限）")
    args = ap.parse_args()

    cases_root = root / CASES_DIR
    if not cases_root.is_dir():
        print(f"cases root not found: {cases_root}", file=sys.stderr)
        return 2

    changed = 0
    scanned = 0
    for path in sorted(cases_root.rglob("case.json")):
        if args.limit and scanned >= args.limit:
            break
        scanned += 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        if not isinstance(raw, dict):
            continue

        if args.only_empty_lesson and str(raw.get("lesson", "")).strip():
            continue

        merged = apply_reflect_metadata(raw)
        same = merged.get("lesson") == raw.get("lesson") and merged.get("case_category") == raw.get("case_category")
        if same:
            continue

        changed += 1
        rel = path.relative_to(root)
        if not args.apply or args.dry_run:
            print(f"would update {rel}")
        else:
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"updated {rel}")

    print(f"scanned={scanned} pending_changes={changed} apply={bool(args.apply)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
