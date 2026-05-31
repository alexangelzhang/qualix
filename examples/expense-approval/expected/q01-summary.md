# Expected Q01 Summary

Q01 should turn the PRD into traceable requirement items. The exact IDs may differ, but these semantics should be present.

## Core Requirements

| Item | Expected Content |
| --- | --- |
| REQ | Employees can create expense requests with amount, currency, category, reason, and receipt attachment. |
| BR | `amount` must be greater than zero. |
| BR | `currency` must be one of `USD`, `EUR`, or `CNY`. |
| BR | Requests below 500 USD equivalent need manager approval only. |
| BR | Requests at or above 500 USD equivalent need manager and finance approval. |
| BR | A manager cannot approve their own request. |
| BR | Rejection requires a requester-visible reason. |
| SE | Every status change sends one requester notification. |
| SE | Approval transitions are idempotent. |
| SE | Approval decisions are audit logged with actor, timestamp, previous status, next status, and comment. |
| SE | Amount comparison uses decimal arithmetic. |
| GAP | Non-USD exchange-rate source is not decided. |
| OPEN | Decide whether rejected requests can be edited and resubmitted. |

The boundary wording matters: “at or above 500” is different from “above 500”.

