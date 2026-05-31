# Concepts

Qualix has a few terms that can look heavier than they are. This page gives the short version first.

## The Short Version

| Term | Plain Meaning |
| --- | --- |
| Phase | One step in the quality workflow. Q01 structures requirements, Q06 audits tests, and so on. |
| Gate | A check that decides whether a phase output is good enough to approve. |
| Harness | The runtime around the agent: schemas, files, prompts, logs, checks, and lifecycle commands. |
| Judge | A reviewer pass that scores or critiques a phase output. |
| Critique | A sharper second look at what the judge or worker may have missed. |
| SE | Semantic Expectation: a business behavior that should be preserved downstream. |
| EUT | Executable Unit-Test target: a test intent tied to a requirement or SE. |
| RSM | Requirement Semantic Matrix: the mapping from requirements/SEs to downstream coverage. |

## Why Phases Exist

A single prompt can produce a useful answer, but it is hard to audit later. Qualix splits the work into phases so each output has a job.

```text
Q01  What did the requirement actually say?
Q02  What design would implement it?
Q03  Is the design internally sound?
Q04  Does the design cover the requirement?
Q05a What tests should exist?
Q05b What test code should be generated?
Q06  Do those tests prove the requirement?
Q07  Does the code review cite real evidence?
```

You do not need every phase on day one. Most users should start with Q01, then read the output. After that, Q05a and Q06 are the quickest way to see the semantic-coverage idea.

## Execute, Finalize, Approve

Each phase has three ordinary commands:

```bash
qualix-run <project> execute Q01 --json
qualix-run <project> finalize Q01 --json
qualix-run <project> approve Q01 --json
```

- `execute` creates the report and structured JSON.
- `finalize` runs checks and writes a gate verdict.
- `approve` marks the phase as accepted so downstream phases can use it.

That lifecycle is the harness. It keeps outputs from being treated as true just because an agent wrote them.

## SE And EUT

An SE is a requirement-level behavior. For example:

> Repeating the same approval request must not create a second audit entry.

An EUT turns that behavior into test intent:

> Given an already approved request, when the same manager approval is retried, then the audit log length remains unchanged.

This is where Qualix differs from ordinary coverage. The target is not just to execute a line. The target is to prove a business behavior.

## Judge And Critique

Qualix uses judge and critique steps because LLM output is not self-verifying.

- The worker creates or revises an artifact.
- The judge checks it against the phase contract.
- The critique step looks for missed issues, weak reasoning, or overconfident passes.
- Deterministic gates still have the final say when schemas or required files are missing.

The point is not to make the model sound more formal. The point is to stop one unchecked model answer from becoming a release signal.

