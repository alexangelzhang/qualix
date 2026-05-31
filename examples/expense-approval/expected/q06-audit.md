# Expected Q06 Audit Findings

The sample tests pass, but they do not prove the full PRD semantics.

## Findings

| Severity | Finding | Evidence |
| --- | --- | --- |
| High | Missing boundary test for exactly 500.00 USD. | `tests/test_expense_policy.py` checks 120 and 600 only. The implementation uses `> 500`, so 500 incorrectly skips finance approval. |
| High | Idempotency is not tested. | Repeating `approve_by_manager` appends another audit row. The PRD says repeated transitions must not create duplicate audit entries or notifications. |
| Medium | Audit log schema is incomplete. | The PRD requires timestamp, but `approve_by_manager` writes actor, previous status, next status, and comment only. |
| Medium | Rejection reason behavior is not covered. | No test exercises rejection without a visible reason. |

## Why Line Coverage Is Not Enough

The tests can exercise both approval branches and still miss the most important threshold detail. Q06 should report that the test suite does not cover the semantic boundary and idempotency rules, even if ordinary coverage looks fine.

