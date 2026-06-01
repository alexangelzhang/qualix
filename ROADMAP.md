# Qualix Roadmap

Qualix is in public alpha. This roadmap reflects the current state and near-term priorities. The pace shifts as we learn from real usage.

## What Is Working Now (0.2.0a1)

The following are complete and production-quality in the current release:

- **Phase pipeline (Q01–Q07)**: requirements structuring, design generation and review, EUT matrix design, unit test codegen, unit test coverage audit, code review
- **PyPI distribution**: `pip install qualix`
- **GitHub Actions composite action**: posts gate verdicts to Step Summary; `action.yml` available from Marketplace
- **pre-commit hook**: `.pre-commit-hooks.yaml` for gating on push
- **CI diff-aware mode**: `--diff HEAD~1` flag limits context to changed files
- **Multi-agent subprocess isolation**: Worker, Judge, and Critique run in isolated subprocesses with no shared context
- **Language providers**: Java (deepest), TypeScript, Go, Python (detection and basic gates)
- **Profile versioning**: `--profile java-ddd-tmf@v1` syntax with version-pinned directories
- **User workspace isolation**: `qualix-run <pid> init` creates `.qualix/` separate from tool source
- **Dashboard (17 pages)**: SE coverage heatmap, guard precision, judge annotation, multi-project aggregation, and more
- **Benchmark cases SC-001–SC-016**: ten cases derived from real production pipeline runs, sanitized

## Current Focus

**End-to-end verifiability**

The biggest gap right now is that visitors cannot independently run Qualix and verify its claims in under 10 minutes. The `examples/expense-approval/` directory has the right PRD and implementation, but the full Q01 → Q05a → Q06 chain needs a scripted path that works without configuration.

Work in progress:
- A `qualix-run expense-demo run-demo` command that runs Q01, Q05a, and Q06 against the synthetic expense-approval PRD with a mock model (or minimal API key usage) and prints a structured report

**Improving the first-time experience**

The Quick Start currently assumes an AI coding agent environment. A direct CLI path — give Qualix a PRD, get a structured SE report back in one command — lowers the barrier for users who want to evaluate without setting up an agent workflow first.

**Python Q05b**

Python test generation is experimental. The two specific gaps blocking it are documented in [Language Support](docs/language-support.md). Target milestone: 0.3.0.

## Near-Term (0.3.0)

- Python Q05b: reliable compile-and-import check + pytest mock template library
- End-to-end demo that runs Q01 + Q05a + Q06 with a single command, no agent required
- Structured `qualix-run explain <se-id>` command: given a SE ID, show the full evidence chain (PRD source → design mapping → EUT → test assertion → Q06 verdict)
- Expanded benchmark: per-phase failure patterns, not just semantic coverage gaps

## Longer-Term

- VS Code extension (MVP): sidebar showing SE coverage status for the open file
- GitHub App: zero-config PR comment posting without a YAML workflow
- Online sandbox: paste a PRD, get Q01 output without installing anything
- Multi-model benchmark: compare Q06 finding quality across GPT / Claude / Gemini on the public benchmark cases

## Not Planned

- Replacing existing test runners (pytest, JUnit, Jest) — Qualix sits above them
- Generic diff review without requirement traceability — that is what existing AI PR reviewers do
- Distributed agent infrastructure — the subprocess isolation in 0.2.0a1 is the right boundary

## Licensing

The core phases (Q01–Q07), CLI, all profiles, and all skills are Apache 2.0 and will remain so. Any future commercial offerings would focus on hosted services and team collaboration tooling, not on gating core functionality.

## Feedback

Open an issue or start a discussion on GitHub if something here is wrong, missing, or should be prioritized differently.
