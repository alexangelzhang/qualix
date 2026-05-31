# Synthetic Q05a Failure Input

PRD rule:

Requests at or above 500 USD equivalent require both manager approval and finance approval. Requests below 500 USD equivalent can be approved by the direct manager only.

Weak EUT output:

| EUT | Given | When | Then |
| --- | --- | --- | --- |
| EUT-001 | request amount is 120 USD | manager approves | status is payment ready |
| EUT-002 | request amount is 600 USD | manager approves | status is manager approved |

Missing case: exactly 500 USD.

