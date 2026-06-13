# Phase Failure Patterns Benchmark

This benchmark catalogs where the Qualix phase pipeline can fail, not just which product semantics are missing from tests.

- `benchmarks/semantic-coverage/` asks: "Which business behavior did the tests miss?"
- `benchmarks/phase-failure-patterns/` asks: "Which Qualix phase failed to preserve, expand, or audit that behavior?"

The seed set is intentionally small and reviewable. Each row links to a synthetic public case in `regression/failure-library/`; real enterprise failure libraries must stay outside this repository.

## Seed Patterns

| Pattern | Phase | Failure Pattern | Case |
| --- | --- | --- | --- |
| `PFP-Q01-uniqueness-boundary` | Q01 | Scoped uniqueness requirement is summarized as generic creation behavior. | `SYNTH-Q01-001` |
| `PFP-Q05a-inclusive-threshold` | Q05a | Inclusive threshold matrix omits the exact boundary value. | `SYNTH-Q05A-001` |
| `PFP-Q06-idempotency-single-shot` | Q06 | Single happy-path assertion is treated as idempotency coverage. | `SYNTH-Q06-001` |

## Manifest Contract

`manifest.json` is the machine-readable catalog. Every pattern must define:

- `pattern_id`, `phase`, `case_id`, and `case_path`
- `failure_pattern`, `benchmark_focus`, `expected_signal`, and `actual_miss`
- `why_it_matters`, `triage`, and `source_safety`

The linked `case.json` must keep the public failure-library fields: `phase`, `error_type`, `root_cause`, `fix_target`, `expected`, `actual`, `lesson`, and `case_category`.

## Validation

Run the checker before publishing benchmark changes:

```bash
python scripts/check_phase_failure_patterns.py
```

The checker verifies that each manifest row links to an existing synthetic or sanitized failure-library case, that case IDs and phases match, and that required explanatory fields are present.
