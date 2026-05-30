"""Q05 → Q05a 数据层迁移脚本.

迁移内容：
1. failure-library/cases/Q05/ (225 cases) → Q05a/
2. failure-library/cases/phaseB/ (74 cases) → Q05a/
3. regression/cases/prompt-eval/Q05-basic/ → Q05a-basic/
4. SQLite: UPDATE metrics SET phase_id="Q05a" WHERE phase_id="Q05"
5. SQLite: UPDATE coverage_snapshots SET phase_id="Q05a" WHERE phase_id="Q05"

所有操作均先 dry-run 打印计划，加 --execute 才真正执行。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent.parent
FAILURE_LIB = BASE / "regression" / "failure-library" / "cases"
PROMPT_DIR = BASE / "regression" / "cases" / "prompt-eval"
DB_PATH = BASE / "output" / ".qualix" / "store.db"


def _patch_case_json(path: Path, new_phase: str, new_id: str | None = None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["phase"] = new_phase
    if new_id:
        data["case_id"] = new_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate_q05(execute: bool) -> None:
    src = FAILURE_LIB / "Q05"
    dst = FAILURE_LIB / "Q05a"
    if not src.exists():
        print("[SKIP] Q05 dir missing")
        return
    cases = [d for d in sorted(src.iterdir()) if d.is_dir()]
    print(f"\n[Q05→Q05a] {len(cases)} cases")
    if execute:
        dst.mkdir(parents=True, exist_ok=True)
    for d in cases:
        new_name = d.name.replace("AUTO-Q05-", "AUTO-Q05a-")
        dst_d = dst / new_name
        cj = d / "case.json"
        if cj.exists():
            old = json.loads(cj.read_text())
            new_id = old.get("case_id", "").replace("AUTO-Q05-", "AUTO-Q05a-")
            if execute:
                _patch_case_json(cj, "Q05a", new_id)
                shutil.move(str(d), str(dst_d))
            else:
                print(f"  {d.name} → {new_name}  phase:{old.get('phase')}→Q05a")
    if execute:
        print(f"  [DONE] {len(cases)} cases moved")


def _migrate_phaseb(execute: bool) -> None:
    src = FAILURE_LIB / "phaseB"
    dst = FAILURE_LIB / "Q05a"
    if not src.exists():
        print("[SKIP] phaseB dir missing")
        return
    cases = [d for d in sorted(src.iterdir()) if d.is_dir()]
    print(f"\n[phaseB→Q05a] {len(cases)} cases")
    if execute:
        dst.mkdir(parents=True, exist_ok=True)
    for d in cases:
        cj = d / "case.json"
        if cj.exists() and execute:
            _patch_case_json(cj, "Q05a")
            shutil.move(str(d), str(dst / d.name))
        elif cj.exists():
            old = json.loads(cj.read_text())
            print(f"  {d.name}: phase:{old.get('phase')}→Q05a")
    if execute:
        print(f"  [DONE] {len(cases)} cases moved")


def _migrate_pe(execute: bool) -> None:
    src = PROMPT_DIR / "Q05-basic"
    dst = PROMPT_DIR / "Q05a-basic"
    if not src.exists():
        print("[SKIP] Q05-basic missing")
        return
    print("\n[prompt-eval] Q05-basic → Q05a-basic")
    if execute:
        if dst.exists():
            print("  [WARN] Q05a-basic already exists, skip")
            return
        shutil.copytree(str(src), str(dst))
        cj = dst / "case.json"
        if cj.exists():
            d = json.loads(cj.read_text())
            d["case_id"] = "Q05a-basic"
            d["phase"] = "Q05a"
            d["description"] = "Q05a EUT matrix design prompt regression baseline"
            cj.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        print("  [DONE] Q05a-basic created")
    else:
        print("  [PLAN] copy Q05-basic → Q05a-basic, phase=Q05a")


def _migrate_sqlite(execute: bool) -> None:
    if not DB_PATH.exists():
        print(f"\n[SKIP] DB not found: {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    print(f"\n[SQLite] {DB_PATH}")
    for tbl in ("metrics", "coverage_snapshots"):
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE phase_id='Q05'")
        n = cur.fetchone()[0]
        print(f"  {tbl}: {n} rows with phase_id=Q05")
        if execute and n:
            cur.execute(f"UPDATE {tbl} SET phase_id='Q05a' WHERE phase_id='Q05'")
            print(f"    → updated {n} rows Q05→Q05a")
    for tbl in ("events", "task_runs"):
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE phase_id='Q05'")
        print(f"  {tbl}: {cur.fetchone()[0]} rows (preserved as history)")
    if execute:
        conn.commit()
        print("  [DONE] committed")
    conn.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--steps", nargs="+", choices=["q05", "phaseb", "pe", "sqlite", "all"], default=["all"])
    args = p.parse_args()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== Q05 data migration [{mode}] ===")

    def run(s: str) -> bool:
        return "all" in args.steps or s in args.steps

    if run("q05"):
        _migrate_q05(args.execute)
    if run("phaseb"):
        _migrate_phaseb(args.execute)
    if run("pe"):
        _migrate_pe(args.execute)
    if run("sqlite"):
        _migrate_sqlite(args.execute)
    print("\n=== done ===" + ("" if args.execute else "\nRun with --execute to apply"))


if __name__ == "__main__":
    main()
