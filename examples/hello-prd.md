# Hello Qualix PRD

This synthetic requirement file is intentionally small so new users can try Q01 without sharing private product data.

## Feature

Build a lightweight approval workflow for expense requests.

## Business Requirements

- A requester can create an expense request with amount, currency, category, reason, and receipt attachment.
- The system validates that amount is greater than zero and currency is one of `USD`, `EUR`, or `CNY`.
- Requests under 500 USD equivalent can be approved by the direct manager.
- Requests at or above 500 USD equivalent require both manager approval and finance approval.
- A rejected request must include a rejection reason visible to the requester.
- The requester receives a notification whenever the request status changes.

## Status Model

```text
DRAFT -> SUBMITTED -> MANAGER_APPROVED -> FINANCE_APPROVED -> PAID
SUBMITTED -> REJECTED
MANAGER_APPROVED -> REJECTED
```

## Non-Functional Requirements

- Status transitions must be idempotent.
- Approval decisions must be audit logged with actor, timestamp, previous status, next status, and comment.
- Amount comparison must use decimal arithmetic, not floating point.

## Open Questions

- Which exchange-rate source should be used for threshold conversion?
- Should requesters be allowed to edit a rejected request and resubmit it?
