# Order Status PRD

## Goal

Track the lifecycle of a customer order from placement to delivery, enforcing that status changes follow a defined sequence and that each transition is recorded.

## Status Model

```
PENDING -> CONFIRMED -> SHIPPED -> DELIVERED
PENDING -> CANCELLED
CONFIRMED -> CANCELLED
```

Any transition not listed above is illegal and must be rejected.

## Business Rules

- Only the transitions shown in the status model are permitted.
- An illegal transition must return a specific error code `INVALID_TRANSITION` and must not modify the order.
- Each successful transition must append one entry to the order's audit log: `{from, to, actor, timestamp}`.
- The same transition submitted twice must be idempotent: if the order is already in the target state, return success without appending a second audit log entry.
- A `CANCELLED` order cannot be transitioned to any other status.
- The delivery timestamp must be recorded when the status changes to `DELIVERED`.

## Non-Functional Requirements

- Transition logic must be safe under concurrent requests for the same order.
- Audit log entries must be written atomically with the status change.

## Open Questions

- Should cancelled orders be reactivated by a separate workflow, or should cancellation be permanent?
