# Comparison: Semantic Coverage vs Line Coverage

Qualix sits next to several familiar tools, but it is trying to answer a different question.

Most code-review and test-generation tools start from code. They inspect a diff, write tests, or look for suspicious changes. That is useful. It is also late in the process. By the time code exists, the original requirement may already have been shortened, reworded, or quietly dropped.

Qualix starts earlier. It turns a requirement document into named expectations, then checks whether design notes, test intent, generated tests, and review findings still line up with those expectations.

## A Small Example

Suppose a PRD says:

> Requests at or above 500 USD require manager approval and finance approval. Requests below 500 USD require manager approval only.

A normal unit-test suite might contain:

- `120 USD -> manager approval is enough`
- `600 USD -> finance approval is required`

That can exercise both branches. It can even improve line coverage. But it still misses the exact rule that matters: `500 USD` belongs to the finance path.

Qualix calls this a semantic coverage gap. The missing test is not just another branch. It is a missing business promise.

## Where Qualix Fits

| Tool Type | Usually Starts From | Good At | Where Qualix Adds Pressure |
| --- | --- | --- | --- |
| AI coding agents | Prompt or issue | Writing code quickly | Checking whether generated code still follows the requirement |
| PR review assistants | Code diff | Finding likely implementation bugs | Tying review findings back to requirement IDs |
| Test-generation tools | Existing code | Producing tests and raising coverage | Checking whether tests prove business behavior, not only execution paths |
| Coverage tools | Test execution | Measuring lines and branches | Reporting missing requirement semantics and weak assertions |
| Eval harnesses | Prompts and model outputs | Measuring model behavior | Applying gates to a software delivery workflow |

Qualix is not a replacement for these tools. It is a gate around the work they produce.

## Qualix vs Qodo / PR Review Assistants

Qodo-style tools are strongest when the code diff is the center of gravity. They can explain changes, suggest tests, and catch common defects.

Qualix is useful when the diff is not enough context. It asks questions like:

- Which requirement does this test prove?
- Did the design cover every business rule from Q01?
- Is this assertion checking the outcome users care about, or just that a method was called?
- Did review findings cite evidence from code, tests, or upstream artifacts?

A PR-only tool is easier to drop in because it never leaves the diff. That is also its ceiling: it cannot tell you whether a requirement from the PRD was silently dropped before the diff existed, because it never saw the PRD. Qualix keeps requirement IDs, phase outputs, and gate state precisely so it can answer that question. The setup cost buys traceability a diff-only tool structurally cannot offer — and `qualix-run <pid> check --prd <path>` collapses that setup into one command.

## Qualix vs CoverAgent / Test-Generation Tools

CoverAgent-like tools are useful when a team wants more executable tests from existing code. The usual feedback loop is code -> tests -> coverage.

Qualix changes the order:

```text
requirement -> EUT intent -> test code -> audit -> gate verdict
```

That order matters when a generated test is technically valid but semantically weak. For example:

```python
assert response.status_code == 200
```

This may be fine for a smoke test. It is not enough to prove that a duplicate approval did not create a second audit row. Q06 is built to call out that difference.

The tradeoff is speed. A narrow test-generation tool can feel faster because it only has to look at code. Qualix spends more effort preserving intent across phases.

## Qualix vs Line Coverage

Line coverage answers: did the tests execute this code?

Semantic coverage asks: did the tests prove this requirement?

Both are useful, but they fail differently.

| Situation | Line Coverage | Semantic Coverage |
| --- | --- | --- |
| Test hits both approval branches but skips exactly 500 USD | Looks acceptable | Flags missing boundary behavior |
| Test asserts HTTP 200 but not the stored audit row | Looks acceptable | Flags weak assertion |
| Test checks success path but not idempotent retry | May look acceptable | Flags uncovered side effect |
| Requirement says rejection reason is visible to requester, test only checks exception type | Looks partial | Flags missing user-visible outcome |

Qualix does not make line coverage obsolete. It gives teams a second lens when line coverage is too shallow.

## What Is Strong Today

- The phase model is explicit: Q01 through Q07 cover requirements, design, tests, audit, and review.
- Phase outputs are structured, not just prose.
- Gates are repeatable: execute, finalize, approve.
- Judge and critique steps are treated as review mechanisms, not unquestioned truth.
- Failure cases can be kept as regression inputs instead of disappearing into chat history.

## What Is Still Early

- Public examples are synthetic.
- The first-time setup still expects an AI coding agent; `qualix-run <pid> check` shortens the on-ramp but does not remove the agent loop.
- Language support is not equally deep across ecosystems.
- The public project needs more benchmark-style examples before broad claims would be fair.

For now, the honest positioning is simple: Qualix is a public-alpha quality gate for teams who care about requirement traceability more than raw code-generation speed.

