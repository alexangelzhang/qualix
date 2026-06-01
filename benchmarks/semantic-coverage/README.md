# Semantic Coverage Benchmark

This directory contains public benchmark cases for Qualix semantic coverage.

Start with [cases.md](cases.md). Each case is short enough to review by hand: requirement, plausible weak test, expected finding.

**SC-001 to SC-006** are synthetic cases built around the expense-approval domain used in the main demo.

**SC-007 to SC-016** were derived from real Q01→Q06 pipeline runs on production Java services (three separate services across fulfillment, financial reporting, and work-order management domains). All identifying information has been removed; business rules and assertion gaps are real.

The benchmark grows by adding cases that expose a real class of missed requirement behavior, not by adding volume. Each new case should be reproducible: someone reading it can write a test that passes the gate.

