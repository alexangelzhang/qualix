# Expected Q01 Summary — Order Status

Q01 should turn the PRD into traceable requirement items. The exact IDs may differ, but these semantics should be present.

## Core Requirements

| Item | Expected Content |
| --- | --- |
| REQ | Orders move through a defined status lifecycle |
| BR | Legal transitions: PENDING→CONFIRMED, PENDING→CANCELLED, CONFIRMED→SHIPPED, CONFIRMED→CANCELLED, SHIPPED→DELIVERED |
| BR | Any other transition must be rejected with `INVALID_TRANSITION` |
| BR | An illegal transition must not modify the order |
| BR | CANCELLED is a terminal state — no further transitions allowed |
| BR | Each successful transition appends one audit log entry: from, to, actor, timestamp |
| SE | The delivery timestamp is recorded when status becomes DELIVERED |
| SE | Repeating a transition when the order is already in the target state is idempotent — no second audit entry |
| SE | Audit log entries are written atomically with the status change |
| GAP | Reactivation of cancelled orders not specified |
| OPEN | Should cancellation be permanent or reversible by a separate workflow? |

The idempotency rule matters: "return success without appending a second entry" is stronger than "return success".
