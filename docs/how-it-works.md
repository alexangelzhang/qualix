# How Qualix Works

This page explains the design decisions behind Qualix: why phases exist, how the SE extraction works, what the Judge/Critique isolation achieves, and why line coverage misses the gaps that Qualix catches. It is written for developers who want to understand the mechanism before committing to a workflow change.

---

## The core problem: tests generated from code inherit its errors

When a developer writes a test by hand, they read the requirement and write code that verifies it. The test is evidence of understanding.

When an AI coding agent writes a test, it reads the code and writes a test that exercises it. The test is evidence of execution.

This distinction matters when the code has a logic error. Consider:

```python
# PRD: "requests at or above 500 USD require finance approval"
# Implementation:
if amount > Decimal("500"):   # bug: should be >=
    return "FINANCE_REQUIRED"
```

An AI agent generating tests from this code will generate:

```python
assert classify(Decimal("120")) == "manager_only"   # passes ✓
assert classify(Decimal("600")) == "finance_required"  # passes ✓
```

Both pass. Line coverage is green. The agent has learned from the wrong implementation, so it generates tests that confirm the implementation, not the requirement. The 500 USD boundary case — the one the PRD explicitly defined — is never tested.

Qualix breaks this feedback loop by deriving test targets from the PRD first, before looking at the code.

---

## How SE extraction works (Q01)

Q01 reads the PRD and produces structured output, including a list of Semantic Expectations (SEs). Each SE is a business behavior that downstream tests must prove.

For the expense-approval PRD, Q01 extracts:

```
SE-001  Every status change sends exactly one notification
SE-002  Approval transitions are idempotent
SE-003  A request at exactly 500 USD requires finance approval (inclusive boundary)
SE-004  Audit log includes actor, timestamp, and status transition
SE-005  Amount comparison uses decimal arithmetic
```

SE-003 exists because the PRD says "at or above" — a phrase Q01 specifically flags as a boundary condition that needs its own test. The agent does not infer this from the code; it extracts it from the natural-language requirement.

This is the key difference: Qualix's test targets come from what the product *said*, not from what the code *does*.

---

## How the coverage audit works (Q06)

Q06 loads the SE list from Q01 and the test suite from the code repository. For each SE, it tries to find a test that proves the expected behavior.

It is not looking for a test that happens to cover the relevant lines. It is looking for a test that:
1. Exercises the specific scenario the SE describes
2. Makes an assertion about the outcome the SE requires

For SE-003, a valid test would be:
```python
result = approve(Request(amount=Decimal("500.00")), actor="manager")
assert result.status == "MANAGER_APPROVED"  # finance still required
```

If the test suite only contains `Decimal("120")` and `Decimal("600")` cases, Q06 reports SE-003 as `PARTIAL`: the requirement is partially covered but the boundary case is missing.

The verdict is:
- `COVERED` — a test proves the SE with a concrete assertion on the expected outcome
- `PARTIAL` — a test exercises the relevant code path but the assertion is too weak
- `MISSING` — no test exercises the scenario at all

This produces a different signal than line coverage. A test that calls the function and asserts `response is not None` contributes to line coverage but produces a `PARTIAL` verdict in Q06 — because existence of a result does not prove the business rule.

---

## Why phases exist (and why a single prompt does not work)

A single prompt can produce a useful answer. It cannot produce a *verifiable* answer.

When you ask an agent to "review these tests against the requirement," the agent produces prose. The output is an opinion. There is no way to:
- Re-run it and get a stable result
- Cite which part of the requirement each finding traces back to
- Compare results across runs or across models
- Use the output as an input to the next step without re-parsing natural language

Qualix splits the work into phases so each output has a defined schema and a defined job. Q01 produces `phase_a_structured.json` — a machine-readable list of requirements, business rules, and semantic expectations. Q06 reads that file and produces `phase_c_structured.json` — a machine-readable audit with status and evidence for each SE.

Each phase output is:
- **Schema-validated** at finalize time (missing required fields block approval)
- **Traceable** (each finding cites the SE ID it corresponds to)
- **Reusable** (Q06 reads Q01 output; a human reviewing Q06 can look up the original SE)
- **Diff-able** (re-running Q06 after adding tests produces a new structured output that can be compared to the previous one)

This is the harness. It keeps outputs from being treated as true just because an agent generated them.

---

## How Judge and Critique isolation works

LLM outputs are not self-verifying. A worker agent that produces a report will tend to defend its own reasoning if asked to critique it.

Qualix runs Worker, Judge, and Critique in isolated subprocesses with no shared context:

```
Worker process     → writes phase_a_report.md
Judge process      → reads report + rubric, writes _judge_result.json
Critique process   → reads report + judge result, writes _critique.json
```

The Judge never sees the Worker's reasoning trace. The Critique sees the report and the Judge's verdict, but not how either of them arrived at their output. Each process starts from a clean context.

This matters in practice because:
- A Judge that can see the Worker's chain of thought will tend to rationalize rather than evaluate
- Concurrent Judge calls from different models can be compared for consensus without one influencing the other
- The deterministic gate (schema validation, required sections check) has the final word regardless of what Judge and Critique say — preventing a confident but wrong evaluation from overriding a structural failure

---

## What the gate lifecycle does

Every phase follows the same three commands:

```
execute  → agent runs the phase skill, writes report + structured JSON
finalize → deterministic checks run: schema, required sections, gate rules
approve  → human (or CI) marks the phase as accepted
```

The finalize step is the safety net. It runs checks that the agent cannot override:
- Does `phase_a_structured.json` match the schema?
- Are all required report sections present?
- Is the SE count non-negative compared to the previous run?

These checks exist because an agent under pressure to pass will sometimes produce an output that looks complete but omits required structure. The finalize gate catches this before the output becomes an input to the next phase.

The approve step is explicit because downstream phases depend on upstream verdicts. Q06 reads Q01 output. If Q01 was approved with a weak SE list, Q06 will audit against that weak list. The explicit approval makes the dependency visible.

---

## The diff-aware mode

Running Q06 on every push against the full test suite is expensive. The `--diff HEAD~1` flag limits the context to files changed in the current branch:

```bash
qualix-run my-project execute Q06 --diff HEAD~1 --json
```

Qualix computes a diff against the base branch, identifies which source files changed, and focuses the Q06 audit on the SEs that are most likely to be affected by those changes. This makes the gate fast enough to run in CI on every push.

---

## What Qualix does not do

- It does not replace pytest, JUnit, or Jest. Tests still need to be run; Qualix audits their intent.
- It does not run a language server or resolve cross-file references. Tree-sitter extraction is file-local.
- It does not enforce a specific assertion style. A test can use any assertion library; Q06 evaluates whether the assertion proves the SE, not how it is written.
- It does not generate production code. The only generated artifacts are test skeletons (Q05b) and structured reports.

---

## Further reading

- [Concepts](concepts.md) — short glossary of terms
- [Comparison](comparison.md) — how Qualix relates to line coverage, test-generation tools, and PR reviewers
- [Real-world results](real-world-results.md) — three production services, sanitized numbers
- [Language support](language-support.md) — which ecosystems are supported and at what depth
- [Q02 guide](q02-guide.md) — when and how to use the design generation phase
