#!/usr/bin/env python3
"""T12: Q05 生产 bug 回归实验 — 清单模板与 JSON manifest 校验（无第三方依赖）."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TEMPLATE = """{
  "schema_version": 1,
  "runs": [
    {
      "project_id": "EXAMPLE_SERVICE",
      "bug_id": "BUG-001",
      "repo_url": "https://example.com/org/repo",
      "bad_commit": "abc1234",
      "fix_commit": "def5678",
      "repro_command": "pytest tests/test_foo.py -k case_bar",
      "notes": "生产场景简述"
    }
  ]
}
"""


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in (here.parent, here.parent.parent):
        if (p / "src" / "qualix").is_dir():
            return p
    return here.parent


def _validate_manifest(data: object) -> list[str]:
    errs: list[str] = []
    if isinstance(data, list):
        runs = data
    elif isinstance(data, dict) and "runs" in data:
        runs = data["runs"]
        if not isinstance(runs, list):
            return ["runs must be a list"]
    else:
        return ["manifest must be a JSON array or an object with key runs"]

    required = ("project_id", "bug_id", "bad_commit", "fix_commit", "repro_command")
    for i, run in enumerate(runs):
        if not isinstance(run, dict):
            errs.append(f"runs[{i}] must be an object")
            continue
        for k in required:
            if not str(run.get(k, "")).strip():
                errs.append(f"runs[{i}] missing or empty {k!r}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Q05 production bug replay experiment helper")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--template", action="store_true", help="打印 experiment-manifest 模板 JSON")
    g.add_argument("--manifest", type=Path, help="校验 manifest JSON 并打印条目数")
    args = ap.parse_args()

    if args.template:
        print(TEMPLATE.strip())
        return 0

    path = args.manifest
    if not path.is_file():
        print(f"manifest not found: {path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"invalid manifest: {e}", file=sys.stderr)
        return 2

    errs = _validate_manifest(data)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1

    runs = data if isinstance(data, list) else data["runs"]
    print(f"manifest OK: {len(runs)} run(s)")
    _ = _repo_root()
    print("Next: fill bad_commit/fix_commit, run Q05 three-step flow per bug, record pass/fail in a spreadsheet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
