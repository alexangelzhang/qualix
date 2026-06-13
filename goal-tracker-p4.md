# Goal Tracker: P4 Phase Failure Patterns Benchmark

## Immutable Acceptance Criteria
- Public benchmark documents per-phase failure patterns, not only semantic coverage gaps.
- Benchmark covers the existing synthetic Q01, Q05a, and Q06 failure-library cases.
- Each benchmark case exposes phase, failure pattern, root cause, fix target, expected signal, actual miss, lesson, and category metadata.
- A machine-checkable validation path prevents schema drift.
- Roadmap and agent instruction files mention the P4 benchmark status.

## Working Notes
- Scope excludes new model scoring, dashboard UI, and adding non-sanitized production cases.

## Completion Evidence
- `python scripts/check_phase_failure_patterns.py` passed with 3 patterns across Q01/Q05a/Q06.
- `python -m pytest tests/test_phase_failure_patterns.py tests/test_regression.py -q` passed: 11 tests.
- `python -m ruff check scripts/check_phase_failure_patterns.py scripts/check_publish_readiness.py tests/test_phase_failure_patterns.py` passed.
- `python scripts/check_publish_readiness.py` passed.
- `python scripts/check_file_lines.py` passed with only existing legacy allowlist warnings.
- `python -m pytest -q` passed: 1254 passed, 1 skipped.
- Scoped GitNexus review in `/tmp/qualix-p4-review/worktree` passed with `Risk level: low`, `Affected processes: 0` after applying only P4 changes.
