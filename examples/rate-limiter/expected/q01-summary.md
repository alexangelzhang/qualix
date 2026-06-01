# Expected Q01 Summary — Rate Limiter

Q01 should turn the PRD into traceable requirement items. The exact IDs may differ, but these semantics should be present.

## Core Requirements

| Item | Expected Content |
| --- | --- |
| REQ | Clients are identified by API key |
| BR | Default limit is 100 requests per 60-second sliding window |
| BR | A request at exactly the limit is permitted |
| BR | A request that would exceed the limit is rejected with HTTP 429 |
| BR | `Retry-After` header is required on rejected responses |
| BR | `Retry-After` must be rounded up to whole seconds |
| BR | Each API key has its own independent counter |
| BR | Rejected requests must not be counted against the limit |
| SE | Counter for a key resets to zero after the window expires |
| SE | Concurrent requests from the same key are handled atomically |
| SE | A key reaching its limit does not affect other keys |
| SE | The boundary value (exactly 100) is permitted, not rejected |
| GAP | Per-key configurable limits not specified |
| OPEN | Should blocked requests be logged for audit? |

The boundary wording matters: "at exactly the limit is permitted" is different from "below the limit is permitted".
