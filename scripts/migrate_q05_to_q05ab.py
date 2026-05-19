#!/usr/bin/env python3
"""将已有 Q05 approved 项目迁移到 Q05a + Q05b 结构.

Q05 拆分后的新 workflow: Q01 → Q05a → Q05b → Q06
本脚本处理已有 Q05 approved 的旧项目，避免重跑 9 小时的 Q05。

迁移逻辑：
1. Q05 设计产物 → Q05a 目录，Q05a 标记 APPROVED（继承 Q05 的时间戳）
2. 扫描业务仓库里的 @Test 文件，检查哪些 EUT 已有对应实现
3. 生成 Q05b/phase_b_code_status.json（passes:true/false）
4. 全部覆盖 → Q05b APPROVED；部分覆盖 → Q05b in_progress

用法:
  python3 scripts/migrate_q05_to_q05ab.py --project <project_id> [--output ./output] [--dry-run]
  python3 scripts/migrate_q05_to_q05ab.py --project home-replace-renewal --output .
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_output_dir(base: Path) -> Path:
    """找到 output 目录（兼容 DQG repo 内和 repo 外两种布局）."""
    if (base / "output").is_dir():
        return base / "output"
    return base


def load_state(output_dir: Path) -> dict:
    state_file = output_dir / "state.json"
    if not state_file.exists():
        print(f"ERROR: state.json not found at {state_file}", file=sys.stderr)
        sys.exit(1)
    return json.loads(state_file.read_text())


def save_state(output_dir: Path, state: dict, dry_run: bool) -> None:
    if dry_run:
        print("  [DRY-RUN] would write state.json")
        return
    (output_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))


def collect_eut_ids_from_code(test_files: list[Path]) -> set[str]:
    """扫描测试文件，收集所有 @Test 方法里出现的 EUT-xxx 引用."""
    EUT_REF = re.compile(r"\bEUT-(\d+)\b")
    covered: set[str] = set()
    for tf in test_files:
        try:
            src = tf.read_text(encoding="utf-8", errors="replace")
            for m in EUT_REF.finditer(src):
                covered.add(f"EUT-{int(m.group(1)):03d}")
        except OSError:
            continue
    return covered


def collect_test_files(code_repos: list[str]) -> list[Path]:
    """从业务仓库收集 git diff 新增/修改的测试文件."""
    test_files: list[Path] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        # git diff 新增 + 未提交
        for cmd in [
            ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
            ["git", "status", "--porcelain"],
        ]:
            try:
                r = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=10)
                for line in r.stdout.splitlines():
                    path_str = line[3:].strip() if cmd[0] == "git" and cmd[1] == "status" else line.strip()
                    if not path_str:
                        continue
                    p = repo / path_str
                    if p.is_file() and p.suffix == ".java" and "src/test/" in str(p):
                        test_files.append(p)
            except (subprocess.TimeoutExpired, OSError):
                continue
    return list(set(test_files))


def migrate_project(output_dir: Path, project_id: str, dry_run: bool) -> None:
    project_dir = output_dir / project_id
    q05_dir = project_dir / "Q05"
    q05a_dir = project_dir / "Q05a"
    q05b_dir = project_dir / "Q05b"

    if not q05_dir.exists():
        print(f"ERROR: Q05 目录不存在：{q05_dir}", file=sys.stderr)
        sys.exit(1)

    state = load_state(project_dir)
    phases = state.get("phases", {})
    q05_state = phases.get("Q05", {})

    if q05_state.get("status") != "approved":
        print(f"SKIP: Q05 状态为 {q05_state.get('status')}（非 approved），无需迁移")
        return

    if phases.get("Q05a", {}).get("status") == "approved":
        print("SKIP: Q05a 已经是 approved 状态，迁移可能已完成")
        # 仍然继续检查 Q05b

    approved_at = q05_state.get("approved_at") or datetime.now().isoformat()
    print(f"\n=== 迁移项目: {project_id} ===")
    print(f"  Q05 approved_at: {approved_at}")

    # ── Step 1: 创建 Q05a 目录，复制设计产物 ────────────────────────────────
    print("\n[Step 1] 创建 Q05a 目录并复制设计产物")
    DESIGN_FILES = [
        "phase_b_structured.json",
        "eut_matrix.md",
        "_reasoning_log.md",
    ]
    DESIGN_INTERNAL_FILES = [
        "_q05_target_modules.json",
        "_upstream_context.md",
        "_bootstrap_context.md",
        "_profile_context.md",
        "_inputs.json",
        "_profile.json",
        "_phase_contract.json",
    ]

    if not dry_run:
        q05a_dir.mkdir(parents=True, exist_ok=True)
        (q05a_dir / "_internal").mkdir(exist_ok=True)

    for fname in DESIGN_FILES:
        src = q05_dir / fname
        dst = q05a_dir / fname
        if src.exists():
            print(f"  COPY {src.name} → Q05a/")
            if not dry_run:
                shutil.copy2(src, dst)
        else:
            print(f"  SKIP {fname} (not found in Q05)")

    for fname in DESIGN_INTERNAL_FILES:
        src = q05_dir / "_internal" / fname
        dst = q05a_dir / "_internal" / fname
        if src.exists():
            print(f"  COPY _internal/{src.name} → Q05a/_internal/")
            if not dry_run:
                shutil.copy2(src, dst)

    # ── Step 2: Q05a 标记 APPROVED ────────────────────────────────────────
    print("\n[Step 2] 将 Q05a 标记为 APPROVED (时间戳继承自 Q05)")
    if "Q05a" not in phases:
        phases["Q05a"] = {}
    phases["Q05a"].update(
        {
            # 与 PhaseState.model_dump() 完全对齐，确保格式兼容
            "status": "approved",
            "run_status": None,
            "started_at": q05_state.get("started_at"),
            "finished_at": q05_state.get("finished_at"),
            "approved_at": approved_at,
            "duration_seconds": q05_state.get("duration_seconds"),
            "comment": "migrated from Q05",
            "validation_errors": [],
            "judge_score": q05_state.get("judge_score"),
            "judge_dimensions": q05_state.get("judge_dimensions") or {},
            "judge_passed": q05_state.get("judge_passed"),
            "judged_at": q05_state.get("judged_at"),
        }
    )

    # ── Step 3: 扫描测试代码，初始化 Q05b 进度 ─────────────────────────────
    print("\n[Step 3] 扫描测试代码，初始化 Q05b phase_b_code_status.json")

    phase_b_path = q05_dir / "phase_b_structured.json"
    if not phase_b_path.exists():
        phase_b_path = q05a_dir / "phase_b_structured.json"

    eut_items = []
    if phase_b_path.exists():
        try:
            data = json.loads(phase_b_path.read_text())
            eut_items = data.get("eut_items", [])
        except Exception as e:
            print(f"  WARN: 无法读取 phase_b_structured.json: {e}")

    # 读取 code_repos
    inputs_path = q05_dir / "_internal" / "_inputs.json"
    code_repos: list[str] = []
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text())
            code_repos = inputs.get("code_repos") or ([inputs["code_repo"]] if inputs.get("code_repo") else [])
        except Exception:
            pass

    # 扫描测试文件
    test_files = collect_test_files(code_repos)
    print(f"  发现测试文件: {len(test_files)} 个")
    covered_euts = collect_eut_ids_from_code(test_files)
    print(f"  代码中有 EUT-xxx 追溯注释的 EUT: {len(covered_euts)} 条")

    # 构建 phase_b_code_status.json
    tasks = []
    for e in eut_items:
        eut_id = e.get("eut_id", "?")
        when = str(e.get("when", "") or "")
        CLS = re.compile(r"\b([A-Z][a-zA-Z0-9]{3,})\.[a-z]")
        classes = CLS.findall(when)
        passes = eut_id.upper() in {x.upper() for x in covered_euts}
        tasks.append(
            {
                "eut_id": eut_id,
                "class": classes[0] if classes else "",
                "passes": passes,
                "test_file": None,
                "test_method": None,
                "failure_reason": None if passes else "migrated: no EUT-xxx annotation found in test code",
            }
        )

    total = len(tasks)
    done = sum(1 for t in tasks if t["passes"])
    missing = [t["eut_id"] for t in tasks if not t["passes"]]

    code_status = {
        "total": total,
        "done": done,
        "tasks": tasks,
        "migrated_from": "Q05",
        "migration_date": datetime.now().isoformat(),
    }

    print(f"  EUT 进度: {done}/{total} passes:true")
    if missing[:5]:
        print(f"  passes:false 示例: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")

    # 创建 Q05b 目录
    if not dry_run:
        q05b_dir.mkdir(parents=True, exist_ok=True)
        (q05b_dir / "_internal").mkdir(exist_ok=True)
        (q05b_dir / "phase_b_code_status.json").write_text(json.dumps(code_status, ensure_ascii=False, indent=2))
        # 复制 inputs 供 Q05b 使用
        if inputs_path.exists():
            shutil.copy2(inputs_path, q05b_dir / "_internal" / "_inputs.json")

    print(f"  {'[DRY-RUN] would write' if dry_run else 'wrote'} Q05b/phase_b_code_status.json")

    # ── Step 4: Q05b 状态 ─────────────────────────────────────────────────
    q05b_status = "approved" if done == total else "in_progress"
    print(f"\n[Step 4] Q05b 状态 → {q05b_status} ({done}/{total} EUT passes:true)")

    if "Q05b" not in phases:
        phases["Q05b"] = {}
    phases["Q05b"].update(
        {
            # 与 PhaseState.model_dump() 完全对齐，确保格式兼容
            "status": q05b_status,
            "run_status": None,
            "started_at": approved_at,
            "finished_at": approved_at if q05b_status == "approved" else None,
            "approved_at": approved_at if q05b_status == "approved" else None,
            "duration_seconds": None,
            "comment": f"migrated from Q05: {done}/{total} EUT covered",
            "validation_errors": [],
            "judge_score": None,
            "judge_dimensions": {},
            "judge_passed": None,
            "judged_at": None,
        }
    )

    # ── 保存 state ────────────────────────────────────────────────────────
    state["phases"] = phases
    save_state(project_dir, state, dry_run)

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}迁移完成:")
    print("  Q05a → approved ✓")
    print(f"  Q05b → {q05b_status} ({done}/{total} EUT)")
    if q05b_status == "in_progress":
        print(f"  ⚠️  {total - done} 条 EUT 需要补充 @Test 方法后才能 finalize Q05b")
        print(f"  建议: 按 Q05b SKILL 的 Ralph Loop 补充剩余 {total - done} 条 EUT 的测试代码")


def main() -> None:
    parser = argparse.ArgumentParser(description="将 Q05 approved 项目迁移到 Q05a + Q05b 结构")
    parser.add_argument("--project", required=True, help="项目 ID（如 home-replace-renewal）")
    parser.add_argument("--output", default="./output", help="output 目录路径（默认 ./output）")
    parser.add_argument("--dry-run", action="store_true", help="只打印操作，不实际执行")
    args = parser.parse_args()

    base = Path(args.output).expanduser().resolve()
    # 支持直接传项目根目录（output/ 会自动加）
    if (base / "output").is_dir():
        output_dir = base / "output"
    elif (base / args.project).is_dir():
        output_dir = base
    else:
        output_dir = base

    migrate_project(output_dir, args.project, args.dry_run)


if __name__ == "__main__":
    main()
