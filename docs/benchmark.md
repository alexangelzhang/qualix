# Semantic Coverage Benchmark

Qualix needs public examples that can be inspected without private customer data. This benchmark is a small seed set for that purpose.

It is not a leaderboard yet. It is a transparent set of cases where ordinary tests can look fine while requirement semantics are still missing.

## What The Benchmark Measures

Each case has four parts:

1. A requirement sentence.
2. A code or test excerpt that looks plausible.
3. The semantic gap a gate should catch.
4. The expected Qualix-style finding.

The benchmark is about recall on business semantics, not model eloquence.

## Seed Cases

The public seed set lives in [benchmarks/semantic-coverage/cases.md](../benchmarks/semantic-coverage/cases.md).

Current themes:

- inclusive threshold boundaries;
- idempotent side effects;
- user-visible rejection reasons;
- decimal money comparison;
- self-approval restrictions;
- weak assertions that only check transport success.

## How To Use It Today

For now, use the benchmark as a reading and review fixture:

1. Read one case.
2. Ask a tool or agent whether the test suite proves the requirement.
3. Compare the answer with the expected finding.
4. Record false passes as synthetic failure-library cases.

The next step is a runner that scores Q06 output against the expected findings. Until that exists, the benchmark is intentionally small and human-auditable.

## Why This Still Helps

The benchmark keeps the claim concrete. Instead of saying “semantic coverage is better,” it asks whether a tool catches a specific miss:

> The test covers 120 USD and 600 USD, but not exactly 500 USD.

That is easy for a maintainer to inspect and hard to hide behind a coverage percentage.

