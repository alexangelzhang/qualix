# Expense Approval PRD

## Goal

Let employees submit expense requests and route them to the right approvers before payment.

## Business Rules

- A requester can create an expense request with `amount`, `currency`, `category`, `reason`, and one receipt attachment.
- `amount` must be greater than zero.
- `currency` must be one of `USD`, `EUR`, or `CNY`.
- A request below 500 USD equivalent can be approved by the requester’s direct manager.
- A request at or above 500 USD equivalent requires manager approval and finance approval.
- A manager cannot approve their own request.
- A rejected request must include a rejection reason visible to the requester.
- The requester must be notified whenever the request status changes.

## Status Model

```text
DRAFT -> SUBMITTED -> MANAGER_APPROVED -> FINANCE_APPROVED -> PAID
SUBMITTED -> REJECTED
MANAGER_APPROVED -> REJECTED
```

For requests below 500 USD equivalent, `MANAGER_APPROVED` is the final approval state before payment.

## Non-Functional Requirements

- Status transitions must be idempotent. Repeating the same approval request must not create a second audit entry or send a second notification.
- Each approval decision must be audit logged with `actor_id`, `timestamp`, `previous_status`, `next_status`, and `comment`.
- Amount comparison must use decimal arithmetic, not floating point.

## Open Questions

- Which exchange-rate source should be used for non-USD threshold conversion?
- Should a requester be allowed to edit and resubmit a rejected request?

