# Rate Limiter PRD

## Goal

Protect backend API endpoints from abuse by limiting the number of requests a client can make within a sliding time window.

## Business Rules

- Each client is identified by an API key.
- The default limit is 100 requests per 60-second sliding window.
- A request at exactly the limit is permitted. A request that would exceed the limit is rejected.
- Each API key has its own independent counter. One key reaching its limit does not affect other keys.
- After a window expires, the counter for that key resets to zero.
- A rejected request must return HTTP 429 with a `Retry-After` header indicating when the window resets.
- The `Retry-After` value must be a whole number of seconds rounded up.

## Non-Functional Requirements

- The limiter must be safe under concurrent requests from the same key.
- Counter increments and limit checks must be atomic.
- The implementation must not count rejected requests against the limit.

## Open Questions

- Should the limit be configurable per key, or only globally?
- Should blocked requests be logged for audit purposes?
