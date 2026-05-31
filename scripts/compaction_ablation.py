"""Evidence Pack compaction ablation experiment.

Runs 4 configurations on a fixed report, compares Judge scores and token usage.
Configurations:
  1. baseline: original rubric + L0 profile
  2. rubric-compact: compact rubric (3-level) + L0 profile
  3. profile-l1: original rubric + L1 profile
  4. both-compact: compact rubric + L1 profile
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qualix.agents.llm_backends import create_backend
from qualix.core.model_registry import estimate_tokens
from qualix.core.profiles import get_profile, load_profile_context_l0, load_profile_context_l1
from qualix.quality.judge_rubrics import compose_rubric, compose_rubric_compact


def _run_judge(rubric: str, report: str, model: str, api_key: str) -> dict:
    """Run a single Judge call and return score + token usage."""
    backend = create_backend(model, api_key)
    schema = {
        "verdict": "PASS | FAIL | PASS_WITH_CONCERNS",
        "overall": "1-5 float",
        "scores": {"dimension_id": "score (int 1-5)"},
        "issues": [{"severity": "high|medium|low", "description": "string"}],
    }
    messages = [
        {"role": "user", "content": f"## Evaluation Rubric\n{rubric}", "cache_control": True},
        {"role": "user", "content": f"## Report\n{report}"},
    ]
    start = time.time()
    result = backend.chat_structured(messages, schema, max_tokens=2000)
    duration = time.time() - start
    usage = result.provider_meta.get("usage", {})
    parsed = result.parsed or {}
    return {
        "verdict": parsed.get("verdict", "UNKNOWN"),
        "overall": parsed.get("overall", 0),
        "scores": parsed.get("scores", {}),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "duration": round(duration, 2),
    }


def main():
    # Config
    phase_id = sys.argv[1] if len(sys.argv) > 1 else "Q03"
    model = os.environ.get("JUDGE_MODEL", "deepseek-chat")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    # Load report from latest output
    output_dir = Path(__file__).resolve().parents[1] / "output" / "expense-approval-demo"
    phase_dirs = {"Q03": "Q03", "Q04": "Q04", "Q07": "Q07"}
    report_names = {
        "Q03": "tech_design_quality_review.md",
        "Q04": "tech_design_coverage_review.md",
        "Q07": "code_review.md",
    }
    report_path = output_dir / phase_dirs[phase_id] / report_names[phase_id]
    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}")
        sys.exit(1)
    report = report_path.read_text(encoding="utf-8")
    if len(report) > 15000:
        report = report[:15000] + "\n...(truncated)"

    profile = get_profile("java-ddd-tmf")

    # Build 4 configurations
    configs = {
        "baseline": {
            "rubric": compose_rubric(phase_id),
            "profile": load_profile_context_l0(profile),
        },
        "rubric-compact": {
            "rubric": compose_rubric_compact(phase_id),
            "profile": load_profile_context_l0(profile),
        },
        "profile-l1": {
            "rubric": compose_rubric(phase_id),
            "profile": load_profile_context_l1(profile, phase_id),
        },
        "both-compact": {
            "rubric": compose_rubric_compact(phase_id),
            "profile": load_profile_context_l1(profile, phase_id),
        },
    }

    print(f"=== Compaction Ablation: {phase_id} ===")
    print(f"Model: {model}")
    print(f"Report: {report_path.name} ({estimate_tokens(report)}t)")
    print()

    # Token estimates
    print("--- Token Estimates (rubric + profile) ---")
    for name, cfg in configs.items():
        rt = estimate_tokens(cfg["rubric"])
        pt = estimate_tokens(cfg["profile"])
        print(f"  {name:20s}: rubric={rt:4d}t  profile={pt:4d}t  total={rt + pt:4d}t")
    print()

    # Run experiments (2 runs each for stability)
    results = {}
    for name, cfg in configs.items():
        rubric_with_profile = cfg["rubric"] + "\n\n## Profile Context\n" + cfg["profile"]
        runs = []
        for run_idx in range(2):
            print(f"  Running {name} (run {run_idx + 1}/2)...", end=" ", flush=True)
            try:
                r = _run_judge(rubric_with_profile, report, model, api_key)
                runs.append(r)
                print(f"verdict={r['verdict']} overall={r['overall']} in={r['input_tokens']} ({r['duration']}s)")
            except Exception as e:
                print(f"FAILED: {e}")
                runs.append({"verdict": "ERROR", "overall": 0, "input_tokens": 0, "output_tokens": 0, "duration": 0})
        results[name] = runs

    # Summary
    print("\n=== Summary ===")
    print(f"{'Config':20s} {'Avg Score':>10s} {'Avg Input':>10s} {'Verdicts':>20s}")
    baseline_score = 0
    for name, runs in results.items():
        valid = [r for r in runs if r["verdict"] != "ERROR"]
        if not valid:
            print(f"{name:20s} {'ERROR':>10s}")
            continue
        avg_score = sum(r["overall"] for r in valid) / len(valid)
        avg_input = sum(r["input_tokens"] for r in valid) / len(valid)
        verdicts = ", ".join(r["verdict"] for r in runs)
        if name == "baseline":
            baseline_score = avg_score
        delta = f" ({avg_score - baseline_score:+.1f})" if baseline_score and name != "baseline" else ""
        print(f"{name:20s} {avg_score:>9.1f}{delta} {avg_input:>10.0f} {verdicts:>20s}")

    # Save results
    out_path = output_dir / phase_dirs[phase_id] / "_internal" / "_compaction_ablation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(results, out_path.open("w"), ensure_ascii=False, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
