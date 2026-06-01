# Expected Q05a EUT Matrix — Order Status

These are the test targets that should exist before code generation.

| EUT ID | SE/BR | When | Then |
| --- | --- | --- | --- |
| EUT-001 | BR: illegal transition rejected | DELIVERED → PENDING called | returns `ErrInvalidTransition`, status unchanged |
| EUT-002 | BR: CANCELLED is terminal | CANCELLED → CONFIRMED called | returns `ErrInvalidTransition` |
| EUT-003 | BR: illegal transition does not modify | PENDING → DELIVERED called | `order.Status` is still PENDING after call |
| EUT-004 | SE: idempotent repeat | PENDING → CONFIRMED called twice | second call returns nil, AuditLog length is 1 not 2 |
| EUT-005 | BR: one audit entry per transition | PENDING → CONFIRMED | `len(AuditLog) == 1` with correct From/To/Actor |
| EUT-006 | SE: delivery timestamp | SHIPPED → DELIVERED | `DeliveredAt` is not nil and matches the `now` argument |
