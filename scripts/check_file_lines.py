#!/usr/bin/env python3
"""文件行数门禁：src/qualix/ 下 .py 文件不超过 400 行。

用法:
    python scripts/check_file_lines.py          # 检查所有文件
    python scripts/check_file_lines.py --strict  # 白名单文件也报错（用于最终清零）

退出码:
    0 — 全部通过
    1 — 有新文件超标（非白名单）

白名单文件超标只输出 WARNING，不影响退出码（除非 --strict）。
白名单会随拆分逐步缩减，目标是清空。
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 400

# 历史遗留超标文件白名单（2026-04-20 基线）
# 拆分后从此列表移除，目标：清空
LEGACY_ALLOWLIST: set[str] = {
    "src/qualix/agents/agent.py",
    "src/qualix/agents/adaptive_loop.py",
    "src/qualix/agents/agent_orchestrator.py",
    "src/qualix/agents/dag_scheduler.py",
    "src/qualix/agents/llm_backends.py",
    "src/qualix/commands/agents.py",
    "src/qualix/commands/phase.py",
    "src/qualix/constants.py",
    "src/qualix/context/chunking/chunk_processor.py",
    "src/qualix/context/analysis/code_skeleton.py",
    "src/qualix/context/loading/context_loader.py",
    "src/qualix/context/analysis/java_ast_analyzer.py",
    "src/qualix/context/analysis/weak_assert_context.py",
    "src/qualix/core/cli.py",
    "src/qualix/core/profiles.py",
    "src/qualix/core/runner.py",
    "src/qualix/ingest/feishu/crawler.py",
    "src/qualix/languages/typescript/provider.py",
    "src/qualix/media/parse_images.py",
    "src/qualix/quality/checks/_auto_checks_q01.py",
    "src/qualix/reporting/perf_tracker.py",
    "src/qualix/memory/knowledge_network.py",
    "src/qualix/quality/checks/blast_radius.py",
    "src/qualix/quality/checks/coverage_gate.py",
    "src/qualix/quality/checks/finalize_checks.py",
    "src/qualix/quality/checks/static_branch_coverage.py",
    "src/qualix/quality/guardrail/semantic_guardrail.py",
    "src/qualix/quality/judge/critique.py",
    "src/qualix/quality/judge/_rubric_data.py",
    "src/qualix/quality/eval/eval_baseline.py",
    "src/qualix/quality/eval/evaluation_protocols.py",
    "src/qualix/quality/judge/judge.py",
    "src/qualix/quality/rules/rule_checks_bc.py",
    "src/qualix/reporting/observability.py",
    "src/qualix/runtime/gate_verdict.py",
    "src/qualix/runtime/handlers/handlers_detection.py",
    "src/qualix/runtime/handlers/handlers_execute.py",
    "src/qualix/runtime/handlers/handlers_finalize.py",
    "src/qualix/runtime/phase_contract.py",
    "src/qualix/runtime/phase_runtime.py",
    "src/qualix/schemas/rsm.py",
    "src/qualix/store/core.py",
    "src/qualix/tracking/regression.py",
    "src/qualix/tracking/skill_reflector.py",
}


def check(strict: bool = False) -> int:
    root = Path("src/qualix")
    if not root.exists():
        print(f"ERROR: {root} not found, run from project root")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        lines = len(py_file.read_text(encoding="utf-8").splitlines())
        if lines <= MAX_LINES:
            continue

        rel = str(py_file)
        if rel in LEGACY_ALLOWLIST and not strict:
            warnings.append(f"  WARNING: {rel} ({lines} lines, legacy allowlist)")
        else:
            errors.append(f"  FAIL: {rel} ({lines} lines > {MAX_LINES})")

    if warnings:
        print(f"\n⚠️  {len(warnings)} legacy files still over {MAX_LINES} lines:")
        for w in warnings:
            print(w)

    if errors:
        print(f"\n🔴 {len(errors)} files exceed {MAX_LINES} line limit:")
        for e in errors:
            print(e)
        print(f"\nFix: split into smaller modules (≤{MAX_LINES} lines each)")
        return 1

    if not warnings:
        print(f"✅ All files under {MAX_LINES} lines")

    return 0


if __name__ == "__main__":
    strict = "--strict" in sys.argv
    sys.exit(check(strict=strict))
