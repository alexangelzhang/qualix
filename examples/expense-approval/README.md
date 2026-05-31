# Expense Approval Demo

This demo is small on purpose. It shows the kind of issue Qualix is meant to catch: code and tests can look tidy while missing a business rule from the PRD.

The feature is an expense approval workflow. The important rule is the approval threshold:

- requests below 500 USD equivalent need manager approval only;
- requests at or above 500 USD equivalent need manager and finance approval;
- all status changes must be idempotent and audit logged.

The sample implementation and test files are synthetic. They are not meant to be a production service; they are a readable target for the quality-gate flow.

## Files

| File | Purpose |
| --- | --- |
| `prd.md` | Public synthetic requirement input |
| `src/expense_policy.py` | Small Python implementation with deliberate gaps |
| `tests/test_expense_policy.py` | Tests that pass but miss key semantics |
| `expected/q01-summary.md` | What Q01 should extract from the PRD |
| `expected/q05a-eut-matrix.md` | Test intent that should exist before code generation |
| `expected/q06-audit.md` | The kind of audit finding Qualix should report |

## Try It

From a project where Qualix is installed:

```bash
qualix-run expense-demo init --profile python
qualix-run expense-demo startup --json
```

Then ask your coding agent to run Q01 against `examples/expense-approval/prd.md`, followed by Q05a and Q06. If you are evaluating manually, read the three files under `expected/` in order.

## The Point

A line-coverage tool can be happy if the tests execute both branches. The real question here is narrower and more useful:

> Did the tests prove that finance approval is required exactly at the 500 USD boundary, and that duplicate approval calls do not create duplicate audit entries?

That is the sort of question Qualix tries to keep visible.

