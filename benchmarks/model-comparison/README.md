# Model Comparison Benchmark

Compare how different LLMs perform on Qualix's Q06 audit task — auditing whether a test suite covers the semantic expectations (SE) of a requirement.

## What This Benchmark Measures

Q06 is the phase where Qualix asks: "Given a PRD, source code, and test suite, which semantic expectations are NOT covered by the tests, even when the tests pass?"

This is a non-trivial reasoning task. Line coverage is not enough — a test suite can hit every branch and still miss boundary values, idempotency, audit schema completeness, etc. Different LLMs vary in how reliably they catch these gaps.

The benchmark feeds the same inputs (PRD + source + tests + SE list) to different models and compares the structured findings each one produces against a golden answer.

## The Golden Standard

The expense-approval case has 4 expected findings, defined in `expense-approval/golden/findings.json`. They correspond directly to the four findings in `examples/expense-approval/expected/q06-audit.md`:

| Finding | Severity | Maps to SE |
| --- | --- | --- |
| Missing boundary test for exactly 500.00 USD | High | SE-003 |
| Idempotency not tested | High | SE-002 |
| Audit log schema incomplete (missing timestamp) | Medium | SE-004 |
| Rejection reason behavior not covered | Medium | — |

A model that surfaces all four findings, with concrete evidence and no spurious additions, is the target.

## Evaluation Dimensions

- **Recall**: of the 4 golden findings, how many did the model surface? `recall = true_positives / 4`.
- **Precision**: of the findings the model reported, how many map to a golden finding? `precision = true_positives / total_reports`.
- **Finding quality** (manual review): does each reported finding contain a concrete piece of evidence (line, value, or behavior) that a developer could act on, or is it a vague restatement of the SE?

A model can score 100% recall and still produce noisy output if it lists 12 findings, of which 8 are speculative. The benchmark surfaces both numbers so you can pick the trade-off you care about.

## How to Run

You need an API key for at least one of: Anthropic, OpenAI, Google.

```bash
# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python benchmarks/model-comparison/run_benchmark.py --model anthropic/claude-sonnet-4-6

# OpenAI
export OPENAI_API_KEY=sk-...
python benchmarks/model-comparison/run_benchmark.py --model openai/gpt-4o

# Google (Gemini)
export GOOGLE_API_KEY=...
python benchmarks/model-comparison/run_benchmark.py --model google/gemini-2.5-pro
```

Without a matching API key the script prints a friendly message and exits cleanly — it does not pretend to have run.

Optional flags:

- `--case expense-approval` (default; only case shipped today)
- `--out results/<custom-name>.json` (override the auto-generated path)
- `--temperature 0.0` (default 0.0 for reproducibility)

## Result Format

Each run writes a JSON file to `results/<provider>-<model>-<UTC-timestamp>.json`:

```json
{
  "model": "anthropic/claude-sonnet-4-6",
  "case_id": "expense-approval",
  "timestamp_utc": "2026-06-02T08:30:00Z",
  "raw_findings": [ /* what the model returned */ ],
  "matched": [ /* model finding ↔ golden finding pairs */ ],
  "missed_golden": [ /* golden findings the model did not catch */ ],
  "extra": [ /* model findings with no golden match */ ],
  "scores": {
    "true_positives": 3,
    "total_reports": 5,
    "total_golden": 4,
    "recall": 0.75,
    "precision": 0.6
  },
  "prompt_hash": "sha256:abc123..."
}
```

The `prompt_hash` lets you detect when a prompt change invalidates older results — same hash means the runs are directly comparable.

## Results Directory

`results/` is gitignored except for its own README. Local runs stay local. To share a result, post the JSON content directly or commit it to a separate forkable benchmark-results repo.

## Adding More Cases

Today the benchmark ships one case. To add another:

1. Create `<case-id>/inputs/{prd.md, source_code.py, test_code.py}` (any source language is fine — keep filenames the same so `run_benchmark.py` finds them).
2. Create `<case-id>/golden/findings.json` following the schema in `expense-approval/golden/findings.json`.
3. Run with `--case <case-id>`.

Cases should expose a real class of missed-requirement behavior, not just inflate volume. See `benchmarks/semantic-coverage/cases.md` for the catalog of patterns Qualix already targets.
