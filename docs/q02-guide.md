# Q02 Technical Design Generation Guide

Q02 generates a technical design document from Q01 structured requirements. It is optional — skip it when you already have a design. Use it when no design exists and you need one before reviewing or auditing.

## When to Use Q02

| Situation | Action |
| --- | --- |
| You have a PRD and want to build something new | Run Q02 after Q01 approves |
| You already have a technical design document | Skip Q02 — point Q03 directly at your design |
| You want to review code but have no design | Run Q02 to generate a design baseline, then Q03/Q04 |
| You only need test coverage, not design review | Skip Q02 — go directly to Q05a |

To skip Q02 explicitly:

```bash
qualix-run my-project skip Q02 -c "existing design at docs/design.md"
```

## Q01 → Q02 → Q03 / Q04

```
Q01  Requirements structuring
      ↓ phase_a_structured.json
Q02  Technical design generation       ← this phase
      ↓ tech_design.md
      ↓ phase_a3_structured.json
Q03  Design quality review
Q04  Design coverage audit
      (both read tech_design.md and phase_a3_structured.json)
```

Q02 reads `Q01/phase_a_structured.json` for the canonical list of requirements, business rules, and semantic expectations. It does not re-read the original PRD.

## Running Q02

```bash
export ANTHROPIC_API_KEY="..."   # or OPENAI_API_KEY / GEMINI_API_KEY
qualix-run my-project execute Q02 --json
qualix-run my-project finalize Q02 --json
qualix-run my-project approve Q02 --json
```

**With an existing code repository:**

```bash
qualix-run my-project execute Q02 --code-repo /path/to/repo --json
```

When a code repository is provided, Q02 scans existing interfaces and classes and incorporates them into the design instead of inventing new ones. This produces a design that extends the existing system rather than replacing it.

## Outputs

| File | Contents |
| --- | --- |
| `output/my-project/Q02/tech_design.md` | The generated technical design (HLD + LLD) |
| `output/my-project/Q02/phase_a3_structured.json` | Structured design data used by Q03/Q04 |
| `output/my-project/Q02/_reasoning_log.md` | Agent reasoning trace |

The design covers ten mandatory chapters: architecture style, module decomposition, interface definitions, data models, state machines, error handling, idempotency strategy, performance considerations, security considerations, and requirement-to-design mapping.

## From Scratch (No Existing Design)

When there is no existing technical design:

1. Ensure Q01 is approved first (`qualix-run my-project status --json`).
2. Run Q02 — the agent will generate a complete design from the Q01 structured output.
3. The generated `tech_design.md` covers all REQ/BR/SE items from Q01.
4. GAP items from Q01 that cannot be resolved architecturally are listed in a "Pending Decisions" section at the end of the design.
5. After Q02 approves, Q03 and Q04 can review the generated design exactly as they would review a human-written one.

The quality of the generated design depends on the quality of Q01 output. If Q01 has many OPEN items or vague SE definitions, Q02 will flag them as architectural decisions that need human input before design can proceed.

## Quality Gate

Q02 finalize checks include:

- All REQ/BR items from Q01 have a corresponding design section
- Each interface definition includes request/response types, error codes, and idempotency behavior
- HLD and LLD are both present (neither alone is sufficient)
- No fabricated frameworks or APIs not found in the code repository (when repo is provided)

## Common Questions

**The generated design looks too high-level.**

Q02 produces both HLD and LLD. If the LLD is thin, it usually means Q01 semantic expectations were vague. Re-run Q01 to extract more precise SE items, then re-run Q02.

**Q03 found architecture issues after Q02.**

This is expected. Q02 generates a candidate design; Q03 reviews its quality. Findings from Q03 feed back into a revised Q02 output. The two phases are designed to iterate.

**I have a partial design — some modules exist, others do not.**

Use `--code-repo` to point Q02 at the existing codebase. It will incorporate existing interfaces and only generate designs for the missing parts. List the existing design file as a context reference in the Q02 execute command if it exists locally.
