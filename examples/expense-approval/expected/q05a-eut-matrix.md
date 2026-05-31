# Expected Q05a EUT Matrix

Q05a should design tests around business semantics rather than only branches.

| EUT | Requirement | Given | When | Then |
| --- | --- | --- | --- | --- |
| EUT-001 | below-threshold approval | A submitted request for 499.99 USD | Manager approves | Status becomes `PAID_READY`; one audit row is written. |
| EUT-002 | threshold boundary | A submitted request for exactly 500.00 USD | Manager approves | Status becomes `MANAGER_APPROVED`; finance approval is still required. |
| EUT-003 | above-threshold approval | A submitted request for 600.00 USD | Manager approves | Status becomes `MANAGER_APPROVED`; no payment-ready status is emitted. |
| EUT-004 | self-approval block | Requester acts as manager | Requester approves own request | Operation is rejected; status and audit log are unchanged. |
| EUT-005 | idempotent manager approval | A request already approved by the same manager | Same approval command is retried | No duplicate audit row and no duplicate notification are produced. |
| EUT-006 | rejection reason | Manager rejects a submitted request | No rejection reason is provided | Rejection is refused with a clear validation error. |

If a generated test suite only covers 120 USD and 600 USD, it has branch coverage but misses the 500 USD rule.

