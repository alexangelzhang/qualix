#!/usr/bin/env python3
"""Harness regression guard — pre-commit hook.

当 harness 核心文件（检查逻辑 / SKILL.md / phase 注册）变更时，
自动运行 regression/cases/ 下所有案例，若发现回归则阻塞提交。

pre-commit 模式：pass_filenames: true，接收变更文件列表。
手动模式：不带参数运行，扫描所有变更文件（通过 git diff）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 触发回归检查的 harness 文件模式（相对于 repo 根目录）
HARNESS_PATTERNS: tuple[str, ...] = (
    # 检查逻辑
    "src/qualix/quality/checks/auto_checks.py",
    "src/qualix/quality/checks/q05_structure_checks.py",
    "src/qualix/quality/checks/finalize_checks.py",
    "src/qualix/quality/guardrail/",
    "src/qualix/quality/rules/",
    # Phase 注册（pass_threshold / judge_required 等）
    "src/qualix/core/phase_registry.py",
    # SKILL.md（rubric 和检查规则定义）
    "skills/",
    # Judge runner 本身（rubric 解析 / sentinel 逻辑）
    "src/qualix/quality/judge/",
)


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in (here.parent, here.parent.parent):
        if (p / "src" / "qualix").is_dir():
            return p
    return here.parent


def _is_harness_file(path_str: str) -> bool:
    """判断文件是否命中 HARNESS_PATTERNS."""
    # 归一化：去掉 qualix/ 前缀，兼容 pre-commit 传入的相对路径
    rel = path_str
    for prefix in ("qualix/", "./qualix/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
            break
    return any(rel.startswith(pattern) or rel == pattern.rstrip("/") for pattern in HARNESS_PATTERNS)


def _run_regression() -> tuple[int, list[dict]]:
    """运行所有 curated regression cases，返回 (exit_code, results)."""
    try:
        from qualix.tracking.regression import compute_exit_code, discover_cases, run_case
    except ImportError:
        print("  [harness-regression] qualix 未安装，跳过检查", file=sys.stderr)
        return 0, []

    cases = [c for c in discover_cases() if c.get("actual_dir")]  # 只跑有 actual_dir 的 curated 案例
    if not cases:
        return 0, []

    results = [run_case(Path(c["case_dir"])) for c in cases]
    return compute_exit_code(results), results


def main() -> int:
    # 从 sys.argv 获取变更文件（pre-commit pass_filenames: true）
    changed_files = sys.argv[1:] if len(sys.argv) > 1 else []

    # 手动模式：从 git diff --cached 获取变更文件
    if not changed_files:
        try:
            out = subprocess.check_output(
                ["git", "diff", "--cached", "--name-only"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            changed_files = [f.strip() for f in out.splitlines() if f.strip()]
        except subprocess.CalledProcessError:
            pass

    harness_changed = [f for f in changed_files if _is_harness_file(f)]
    if not harness_changed:
        return 0

    print(f"\n  [harness-regression] 检测到 {len(harness_changed)} 个 harness 文件变更，运行回归套件...")
    for f in harness_changed[:5]:
        print(f"    • {f}")
    if len(harness_changed) > 5:
        print(f"    ... 及 {len(harness_changed) - 5} 个更多")

    ec, results = _run_regression()

    regressions = [r for r in results if not r.get("passed", True)]

    if ec == 0:
        print(f"  ✅ 回归套件通过（{len(results)} 个案例）")
    else:
        print(f"  🚨 发现 {len(regressions)} 个回归：", file=sys.stderr)
        for r in regressions:
            diffs = [d for d in r.get("diffs", []) if d["status"] in ("回归", "偏移")]
            print(f"    [{r['case_id']}] {len(diffs)} 个文件异常", file=sys.stderr)
        print("\n  修复回归后再提交，或用 --no-verify 临时跳过（需在 PR 描述中说明原因）", file=sys.stderr)

    return ec


if __name__ == "__main__":
    raise SystemExit(main())
