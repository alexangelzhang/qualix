# Expected Q06 Audit Findings — Rate Limiter

The sample tests pass, but they do not prove the full PRD semantics.

## Findings

| Severity | Finding | Evidence |
| --- | --- | --- |
| High | Missing boundary test for exactly 100 requests. | Tests use limit=2 and check counts of 3. They never verify that a request at count=limit is permitted, not rejected. |
| High | Key isolation is not tested. | No test uses two different keys and verifies they have independent counters. |
| Medium | Window reset behavior is not tested. | No test advances time past the window boundary and checks that the counter resets. |
| Medium | Rejected requests are not verified to leave the counter unchanged. | The test at `over the limit` does not assert `remaining` after two rejections. |

## Why Line Coverage Is Not Enough

The tests can exercise the allowed and rejected branches. The most important semantic — the boundary value of exactly 100, and that two keys are independent — is never verified.
