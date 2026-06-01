#!/usr/bin/env python3.11
"""Custom eval for Q05a iron-law bypass detection."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pathlib import Path

sys.path.insert(0, "src")

from qualix.constants import DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL
from qualix.quality.judge.judge_rubrics import compose_rubric
from qualix.quality.judge.judge_runner import JudgeRunner

CASES = [
    # FN: must FAIL
    ("AUTO-FN-1", "regression/failure-library/cases/Q05a/AUTO-Q05a-20260520031542-32/input.md", "FAIL"),
    ("AUTO-FN-2", "regression/failure-library/cases/Q05a/AUTO-Q05a-20260428204748-143/input.md", "FAIL"),
    ("SYNTH-SE-based", "regression/failure-library/cases/Q05a/SYNTH-Q05a-se-based-violation-01/input.md", "FAIL"),
    ("SYNTH-vague-then", "regression/failure-library/cases/Q05a/SYNTH-Q05a-vague-then-01/input.md", "FAIL"),
    ("SYNTH-mixed", "regression/failure-library/cases/Q05a/SYNTH-Q05a-mixed-pattern-01/input.md", "FAIL"),
    # PASS: must PASS — add a synthetic Q05a pass case here once available
    # ("PASS-example", "regression/pass-library/cases/Q05a/PASS-Q05a-example/input.md", "PASS"),
]

rubric = compose_rubric("Q05a")
runner = JudgeRunner()
results = []
with tempfile.TemporaryDirectory() as tmp:
    for name, path, expected in CASES:
        r = runner.run(
            phase="Q05a",
            report_path=path,
            output_dir=tmp,
            model=DEFAULT_JUDGE_MODEL,
            fallback=DEFAULT_FALLBACK_MODEL,
            rubric=rubric,
        )
        normalized = "PASS" if "PASS" in r.verdict else "FAIL"
        correct = normalized == expected
        results.append(correct)
        if "--verbose" in sys.argv:
            icon = "✅" if correct else "❌"
            print(f"  {icon} {name}: {r.verdict} (expected {expected})", file=sys.stderr)

accuracy = sum(results) / len(results) * 100
if "--verbose" in sys.argv:
    print(f"准确率: {accuracy:.1f}% ({sum(results)}/{len(results)})", file=sys.stderr)
print(f"{accuracy:.1f}")
