# Expected Q05a EUT Matrix — Rate Limiter

These are the test targets that should exist before code generation.

| EUT ID | SE/BR | When | Then |
| --- | --- | --- | --- |
| EUT-001 | BR: at-limit permitted | count equals limit exactly | `isAllowed` returns true, remaining = 0 |
| EUT-002 | BR: over-limit rejected | count exceeds limit | `isAllowed` returns false, HTTP 429 |
| EUT-003 | SE: counter reset | request arrives after window expires | counter resets, request is allowed |
| EUT-004 | SE: key isolation | two keys each reach limit independently | key-A reaching limit does not affect key-B |
| EUT-005 | BR: Retry-After rounding | 1500ms remaining in window | retryAfterSeconds = 2 (ceiling) |
| EUT-006 | BR: rejected requests not counted | two requests over limit | counter stays at limit, not limit+2 |
