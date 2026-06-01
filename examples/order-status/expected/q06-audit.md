# Expected Q06 Audit Findings — Order Status

The sample tests pass, but they do not prove the full PRD semantics.

## Findings

| Severity | Finding | Evidence |
| --- | --- | --- |
| High | Illegal transition rejection is not tested. | No test calls an illegal transition and asserts `ErrInvalidTransition`. Tests only exercise valid paths. |
| High | Terminal state (CANCELLED) is not tested. | No test verifies that a CANCELLED order cannot transition to any other status. |
| High | Idempotency is not tested. | No test repeats the same transition and asserts that the audit log does not grow. |
| Medium | Audit log entry count is not asserted precisely. | `assert.Len(t, o.AuditLog, 1)` is present but only after one transition. No test verifies that two transitions produce exactly two entries (not more). |

## Why Line Coverage Is Not Enough

The valid-path tests execute the transition logic and the audit log append. They do not reach the `ErrInvalidTransition` branch or the idempotency check. Line coverage can look reasonable while all three high-severity gaps remain open.
