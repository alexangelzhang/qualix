#!/usr/bin/env python3.11
"""
eval_judge.py — 用 regression/failure-library 中的 GT case 评估 judge rubric 质量

用法：
  python3 scripts/eval_judge.py --phase Q06
  python3 scripts/eval_judge.py --phase Q05a --limit 50 --verbose
  python3 scripts/eval_judge.py --phase Q03 --error-types FN --limit 30

输出（标准模式）：
  单行数字（0-100），供 /autoresearch Verify 命令读取

输出（--verbose 模式）：
  详细的每条 case 判断结果，按 FN/FP 分类统计

参数：
  --phase       Phase ID（必填），如 Q03/Q05/Q05a/Q05b/Q06/Q07
  --limit       最多评估多少条 case（默认 30，-1 = 全量）
  --error-types 只评估指定类型，逗号分隔（默认 FN,FP）
  --verbose     输出详细每条结果
  --model       judge 使用的模型（默认读 DEFAULT_JUDGE_MODEL）
  --seed        随机采样固定种子（默认 42，保证可复现）
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

# ── 项目根目录注入 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from qualix.constants import DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL
from qualix.quality.judge.judge_rubrics import compose_rubric
from qualix.quality.judge.judge_runner import JudgeRunner

FAILURE_CASES_ROOT = PROJECT_ROOT / "regression" / "failure-library" / "cases"
PASS_CASES_ROOT = PROJECT_ROOT / "regression" / "pass-library" / "cases"
CASES_ROOT = FAILURE_CASES_ROOT  # 默认，main() 中按 --library 覆盖

# FN case：judge 漏判了真实缺陷 → 正确应为 FAIL
# FP case：judge 误判了正确产出 → 正确应为 PASS（failure-library 中手动标注）
# PASS case：已验证的良好产出 → 正确应为 PASS（pass-library 中来自 output/）
EXPECTED_VERDICT: dict[str, str] = {
    "FN": "FAIL",
    "FP": "PASS",
    "PASS": "PASS",
}


def load_cases(phase: str, error_types: list[str], limit: int, seed: int, cases_root: Path | None = None) -> list[dict]:
    """加载指定 Phase 的 GT case，过滤 error_type，采样到 limit 条。"""
    root = cases_root or CASES_ROOT
    phase_dir = root / phase
    if not phase_dir.exists():
        candidates = [d for d in root.iterdir() if d.name.upper() == phase.upper()]
        if not candidates:
            print(f"❌ 未找到 Phase 目录: {phase_dir}", file=sys.stderr)
            print(f"   可用 Phase: {sorted(d.name for d in root.iterdir() if d.is_dir())}", file=sys.stderr)
            sys.exit(1)
        phase_dir = candidates[0]

    cases = []
    for case_dir in sorted(phase_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        case_file = case_dir / "case.json"
        input_file = case_dir / "input.md"
        if not case_file.exists() or not input_file.exists():
            continue
        meta = json.loads(case_file.read_text(encoding="utf-8"))
        if meta.get("error_type") not in error_types:
            continue
        cases.append(
            {
                "case_id": meta["case_id"],
                "phase": meta.get("phase", phase),
                "error_type": meta["error_type"],
                "severity": meta.get("severity", "medium"),
                "root_cause": meta.get("root_cause", ""),
                "lesson": meta.get("lesson", ""),
                "input_path": str(input_file),
                "expected_verdict": EXPECTED_VERDICT[meta["error_type"]],
            }
        )

    if not cases:
        print(f"⚠️  {phase_dir} 中无符合条件的 case（error_type={error_types}）", file=sys.stderr)
        print("0.0")
        sys.exit(0)

    if limit > 0 and len(cases) > limit:
        random.seed(seed)
        cases = random.sample(cases, limit)

    return cases


def run_single(case: dict, rubric: str, model: str, fallback: str, tmp_dir: str) -> dict:
    """对单条 case 跑一次 judge，返回结果字典。"""
    runner = JudgeRunner()
    try:
        result = runner.run(
            phase=case["phase"],
            report_path=case["input_path"],
            output_dir=tmp_dir,
            model=model,
            fallback=fallback,
            rubric=rubric,
        )
        actual_verdict = result.verdict
        health = result.health
    except Exception as e:
        actual_verdict = "INFRA_FAILURE"
        health = "INFRA_FAILURE"
        if __debug__:
            print(f"   ⚠️  {case['case_id']} runner error: {e}", file=sys.stderr)

    expected = case["expected_verdict"]
    # 把 PASS_WITH_CONCERNS 算作 PASS
    normalized = "PASS" if "PASS" in actual_verdict else "FAIL"
    correct = normalized == expected

    return {
        "case_id": case["case_id"],
        "error_type": case["error_type"],
        "expected": expected,
        "actual": actual_verdict,
        "correct": correct,
        "health": health,
        "root_cause": case["root_cause"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge rubric 质量评估工具")
    parser.add_argument("--phase", required=True, help="Phase ID，如 Q06/Q05a/Q03")
    parser.add_argument("--limit", type=int, default=30, help="最多评估条数（-1=全量）")
    parser.add_argument("--error-types", default="FN,FP", help="评估的 error_type，逗号分隔")
    parser.add_argument(
        "--library",
        choices=["failure", "pass", "both"],
        default="failure",
        help="使用哪个 case 库（failure/pass/both，默认 failure）",
    )
    parser.add_argument("--verbose", action="store_true", help="输出每条 case 详情")
    parser.add_argument("--model", default=DEFAULT_JUDGE_MODEL, help="judge 模型")
    parser.add_argument("--fallback", default=DEFAULT_FALLBACK_MODEL, help="fallback 模型")
    parser.add_argument("--seed", type=int, default=42, help="随机采样种子")
    args = parser.parse_args()

    # 根据 library 参数决定 error_types 和 cases_root
    if args.library == "pass":
        error_types = ["PASS"]
        cases_root = PASS_CASES_ROOT
    elif args.library == "both":
        error_types = [e.strip().upper() for e in args.error_types.split(",")]
        error_types = list(set(error_types) | {"PASS"})
        cases_root = None  # load from both (handled below)
    else:
        error_types = [e.strip().upper() for e in args.error_types.split(",")]
        cases_root = FAILURE_CASES_ROOT

    unknown = set(error_types) - set(EXPECTED_VERDICT)
    if unknown:
        print(f"❌ 未知 error_type: {unknown}，支持: {list(EXPECTED_VERDICT)}", file=sys.stderr)
        sys.exit(1)

    if args.library == "both":
        # 合并两个库的 case
        fail_cases = load_cases(
            args.phase, [e for e in error_types if e != "PASS"], args.limit // 2, args.seed, FAILURE_CASES_ROOT
        )
        pass_cases = load_cases(args.phase, ["PASS"], args.limit // 2, args.seed, PASS_CASES_ROOT)
        cases = fail_cases + pass_cases
    else:
        cases = load_cases(args.phase, error_types, args.limit, args.seed, cases_root)

    rubric = compose_rubric(args.phase)

    if args.verbose:
        print(f"Phase={args.phase} | cases={len(cases)} | model={args.model}")
        print(f"rubric dimensions: {len(rubric.split('###')) - 1}")
        print()

    results = []
    with tempfile.TemporaryDirectory(prefix="qualix_eval_") as tmp_dir:
        for i, case in enumerate(cases, 1):
            if args.verbose:
                print(f"  [{i:2d}/{len(cases)}] {case['case_id']} ({case['error_type']}) ... ", end="", flush=True)
            r = run_single(case, rubric, args.model, args.fallback, tmp_dir)
            results.append(r)
            if args.verbose:
                icon = "✅" if r["correct"] else "❌"
                print(f"{icon} {r['actual']} (expected {r['expected']})")

    # 汇总统计
    infra_failures = [r for r in results if r["health"] == "INFRA_FAILURE"]
    valid = [r for r in results if r["health"] != "INFRA_FAILURE"]
    correct = [r for r in valid if r["correct"]]
    accuracy = len(correct) / len(valid) * 100 if valid else 0.0

    if args.verbose:
        fn_results = [r for r in valid if r["error_type"] == "FN"]
        fp_results = [r for r in valid if r["error_type"] == "FP"]
        fn_correct = [r for r in fn_results if r["correct"]]
        fp_correct = [r for r in fp_results if r["correct"]]

        print(f"\n{'=' * 50}")
        print(f"准确率: {accuracy:.1f}% ({len(correct)}/{len(valid)} correct)")
        if fn_results:
            print(f"  FN 检出率: {len(fn_correct) / len(fn_results) * 100:.1f}% ({len(fn_correct)}/{len(fn_results)})")
        if fp_results:
            print(f"  FP 精确率: {len(fp_correct) / len(fp_results) * 100:.1f}% ({len(fp_correct)}/{len(fp_results)})")
        if infra_failures:
            print(f"  基础设施失败: {len(infra_failures)} 条（已排除）")

        # 失败 case 的 root_cause 分布
        wrong = [r for r in valid if not r["correct"]]
        if wrong:
            print("\n未正确判断的 case root_cause：")
            from collections import Counter

            for rc, cnt in Counter(r["root_cause"] for r in wrong).most_common():
                print(f"  {cnt:2d}x  {rc}")

    # 标准输出：单行数字（供 /autoresearch Verify 读取）
    print(f"{accuracy:.1f}")


if __name__ == "__main__":
    main()
