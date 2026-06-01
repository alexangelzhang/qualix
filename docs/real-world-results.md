# Real-World Results

These results are from running Qualix on three production Java services. All identifying information has been removed; domain names and service descriptions are generic.

The pipeline was: Q01 (requirements structuring) → Q05a (EUT matrix design) → Q05b (unit test generation) → Q06 (unit test coverage audit). Q03/Q04 (design review) was not run on these services.

---

## Service A — Renewal Workflow Service

A service handling service-order renewal, including routing logic that conditionally calls an external fulfillment center API.

| Phase | Metric | Result |
| --- | --- | --- |
| Q01 | Requirements extracted | 31 |
| Q01 | Semantic expectations (SE) | 11 |
| Q01 | Gaps identified | 6 |
| Q06 | EUT targets audited | 90 |
| Q06 | Covered | 90 |
| Q06 | Partial / Missing | 0 / 0 |
| Q06 | Verdict | **PASS** |

**What Qualix found:** The 90 EUT targets were fully covered after Q05b generation. The 6 Q01 gaps were OPEN items in the PRD (exchange-rate source, edge-case routing for unsupported categories) — not failures in the test suite. The service had clean assertion quality across all targets.

---

## Service B — Financial Reporting Service

A service managing monthly financial data submissions for retail locations, with a versioned approval workflow.

| Phase | Metric | Result |
| --- | --- | --- |
| Q01 | Requirements extracted | 67 |
| Q01 | Semantic expectations (SE) | 22 |
| Q01 | Gaps identified | 13 |
| Q06 | EUT targets audited | 22 |
| Q06 | Covered | 21 |
| Q06 | Partial / Missing | 1 / 0 |
| Q06 | Verdict | **PASS_WITH_RISKS** |

**What Qualix found:** One EUT was flagged PARTIAL. The requirement stated that a specific field type must be filled monthly even when the value does not change. The test verified that the field was present in the template structure, but not that "filling the same value repeatedly" was semantically valid and idempotent. The test proved template structure, not the monthly-fill semantic.

---

## Service C — Work-Order Approval Platform

A platform managing work-order lifecycle with an approval flow that includes concurrency control and idempotency requirements.

| Phase | Metric | Result |
| --- | --- | --- |
| Q01 | Requirements extracted | 50 |
| Q01 | Semantic expectations (SE) | 18 |
| Q01 | Gaps identified | 12 |
| Q06 | EUT targets audited | 103 |
| Q06 | Covered | 87 |
| Q06 | Partial / Missing | 16 / 2 |
| Q06 | Verdict | **PASS_WITH_RISKS** (score 3.5/5) |

**What Qualix found:**

- 16 PARTIAL: Tests relied on indirect coverage — the method under test was exercised as a side effect of another call, rather than being the direct call target. Q06 flagged these because indirect coverage does not prove that the specific method's contract was tested.
- 2 MISSING: Two semantic expectations from Q01 had no corresponding test at all. One covered the mutual-exclusion rule for UI button states after approval; the other covered the OR-logic rule (either approver role is sufficient, not both required).

The 2 missing cases matched the benchmark cases SC-015 and SC-016 in [`benchmarks/semantic-coverage/cases.md`](../benchmarks/semantic-coverage/cases.md), which were derived from this service.

---

## Summary

| | Service A | Service B | Service C |
| --- | --- | --- | --- |
| SE extracted | 11 | 22 | 18 |
| EUT audited | 90 | 22 | 103 |
| Semantic coverage | 100% | 95.5% | 84.5% |
| Verdict | PASS | PASS_WITH_RISKS | PASS_WITH_RISKS |

Line coverage was green on all three services before Qualix was run. The two missing cases in Service C and the partial case in Service B were not flagged by the existing coverage tools.

The most common pattern Q06 identified: tests that **verify execution** (the method was called, the response was non-null, the status code was 200) rather than **verifying the business rule** (the specific boundary, the idempotency invariant, the mutual-exclusion constraint).

---

*These results are from private production deployments. The full pipeline output files are not published; the numbers above are the final gate verdicts.*
