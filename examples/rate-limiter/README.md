# Rate Limiter Demo (TypeScript)

This demo shows Qualix working on a TypeScript Node.js service. It uses the same structure as the [expense-approval demo](../expense-approval/README.md): a synthetic PRD, a small implementation with deliberate gaps, and tests that pass ordinary coverage but miss key semantics.

The feature is an API rate limiter. The important rules are the sliding window behavior, the per-key isolation, and the idempotency of repeated requests within the same window.

## Files

| File | Purpose |
| --- | --- |
| `prd.md` | Synthetic requirement input |
| `src/rateLimiter.ts` | TypeScript implementation with deliberate gaps |
| `tests/rateLimiter.test.ts` | Jest tests that pass coverage but miss semantics |
| `expected/q01-summary.md` | What Q01 should extract from the PRD |
| `expected/q05a-eut-matrix.md` | Test intent that should exist before code generation |
| `expected/q06-audit.md` | The kind of audit finding Qualix should report |

## Try It

```bash
qualix-run --profile typescript-service rate-limiter init
qualix-run ingest examples/rate-limiter/prd.md --project rate-limiter
qualix-run rate-limiter startup --json
```

Then ask your coding agent to run Q01 against `examples/rate-limiter/prd.md`, followed by Q05a and Q06.

## The Point

The tests check that `isAllowed()` returns the right boolean and that the counter increments. They do not verify that the window resets at the correct boundary, that two different keys have independent counters, or that a burst exactly at the limit (not over) is permitted. Q06 should surface these gaps.
