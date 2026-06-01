# Order Status Demo (Go)

This demo shows Qualix working on a Go service. It uses the same structure as the [expense-approval demo](../expense-approval/README.md): a synthetic PRD, a small implementation with deliberate gaps, and tests that pass ordinary coverage but miss key semantics.

The feature is an order status machine. The important rules are which transitions are legal, that illegal transitions are rejected, and that transition side effects (audit log, notification) are idempotent.

## Files

| File | Purpose |
| --- | --- |
| `prd.md` | Synthetic requirement input |
| `src/order.go` | Go implementation with deliberate gaps |
| `tests/order_test.go` | testify tests that pass coverage but miss semantics |
| `expected/q01-summary.md` | What Q01 should extract from the PRD |
| `expected/q05a-eut-matrix.md` | Test intent that should exist before code generation |
| `expected/q06-audit.md` | The kind of audit finding Qualix should report |

## Try It

```bash
qualix-run --profile go-service order-status init
qualix-run ingest examples/order-status/prd.md --project order-status
qualix-run order-status startup --json
```

Then ask your coding agent to run Q01 against `examples/order-status/prd.md`, followed by Q05a and Q06.

## The Point

The tests verify that valid transitions succeed and that the status field is updated. They do not verify that illegal transitions are rejected with the right error code, that the audit log grows by exactly one entry per transition (not more), or that repeating the same transition is idempotent. Q06 should surface these gaps.
