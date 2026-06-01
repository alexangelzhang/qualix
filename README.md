# Qualix

[![Tests](https://github.com/alexangelzhang/qualix/actions/workflows/qualix-self-check.yml/badge.svg)](https://github.com/alexangelzhang/qualix/actions/workflows/qualix-self-check.yml)
[![PyPI](https://img.shields.io/pypi/v/qualix)](https://pypi.org/project/qualix/)
[![Python](https://img.shields.io/pypi/pyversions/qualix)](https://pypi.org/project/qualix/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![codecov](https://codecov.io/gh/alexangelzhang/qualix/branch/main/graph/badge.svg)](https://codecov.io/gh/alexangelzhang/qualix)

AI-native development quality gates for requirements, designs, tests, and code reviews.

Qualix turns product requirements into traceable engineering checks. Instead of stopping at line coverage, it follows requirement IDs through design coverage, test intent, generated unit tests, audit reports, and review findings.

## The Problem in One Example

A PRD says: *requests at or above 500 USD require manager **and** finance approval.*

Your tests pass:

```
120 USD → manager approval only ✓
600 USD → finance approval required ✓
```

Line coverage is green. But the test at exactly **500 USD** is missing — and the implementation uses `> 500` instead of `>= 500`, so the boundary case silently escapes to the wrong path.

Qualix calls this a **semantic coverage gap**. Q06 reports it even when coverage tools do not:

```
[HIGH] Missing boundary test for exactly 500 USD.
       Implementation uses > 500; threshold rule says ≥ 500.
       Add: approve(Request(amount=Decimal("500.00"))) → finance_required
```

## Numbers from Real Projects

Three production Java services run through the full Q01→Q06 pipeline:

| Project | PRD size | Q01: SE extracted | Q06: EUT audited | Weak / missing |
| --- | --- | --- | --- | --- |
| Approval workflow | 67 requirements | 22 semantic expectations | 22 | 1 partial |
| Renewal service | 31 requirements | 11 semantic expectations | 90 | 0 |
| Platform service | 50 requirements | 18 semantic expectations | 103 | 16 partial, 2 missing |

In the platform service, 18 of 103 audited test targets had assertion gaps that line coverage did not flag.

## The Short Version

Give Qualix a PRD, then move through small quality checkpoints:

1. Turn messy requirements into explicit requirement items and business rules.
2. Check whether a technical design really covers those requirements.
3. Design tests around business behavior, not just lines of code.
4. Audit generated tests and code review findings against the original intent.

The terms map to normal development work:

| Term | Plain meaning |
| --- | --- |
| Phase | One workflow step, such as structuring requirements or auditing tests |
| Gate | A pass/fail check before moving on |
| Judge / Critique | A second-pass review of the agent's own output |
| SE | A key semantic expectation the product depends on |
| EUT | A test target: behavior that should be proven by unit tests |
| RSM | A requirement-to-code/test trace map used to catch missing coverage |

You can learn the vocabulary gradually. For a first run, start with Q01 and inspect the generated requirement report.

## Why Qualix

| Problem | What Usually Happens | Qualix Approach |
| --- | --- | --- |
| Requirement drift | PRDs lose detail as they move into design and code | Q01 extracts structured REQ/BR/SE items with traceable IDs |
| Design gaps | Technical designs are reviewed loosely | Q03/Q04 review design quality and requirement coverage |
| Shallow tests | Coverage is green but business behavior is not tested | Q05a/Q05b design and generate requirement-driven unit tests |
| Weak assertions | Tests assert calls or existence, not semantics | Q06 audits test intent, weak assertions, and coverage evidence |
| Review inconsistency | Code review depends on reviewer memory | Q07 produces structured, evidence-backed review findings |

## Status

Qualix is early and evolving. The repository is useful for experimentation, internal quality-gate workflows, and evaluating the phase model. APIs, file formats, and phase reports may still change before a stable `1.0.0` release.

## Quick Start

```bash
pip install qualix
qualix-run --profile python-service hello init
qualix-run ingest examples/hello-prd.md --project hello
qualix-run hello startup --json
```

Then run an AI-backed phase (requires a model API key):

```bash
export ANTHROPIC_API_KEY="..."   # or OPENAI_API_KEY / GEMINI_API_KEY / DASHSCOPE_API_KEY
qualix-run --profile python-service hello execute Q01 --json
qualix-run hello finalize Q01 --json
qualix-run hello approve Q01 --json
```

## Flagship Demo: Expense Approval

The [expense approval demo](examples/expense-approval/README.md) is the fastest way to see what Qualix catches. It ships with a synthetic PRD, a Python implementation with deliberate gaps, and tests that pass ordinary coverage — but miss the 500 USD boundary and idempotency rules.

Expected outputs are in [`examples/expense-approval/expected/`](examples/expense-approval/expected/): what Q01 should extract, what EUT matrix Q05a should produce, and what Q06 should report.

```bash
qualix-run --profile python-service expense-demo init
qualix-run ingest examples/expense-approval/prd.md --project expense-demo
qualix-run expense-demo startup --json
```

To try without private project data, start with the simpler [examples/hello-prd.md](examples/hello-prd.md).

Inside an AI coding agent, use the project starter instructions:

```text
$qualix-starter
```

You can also run phases manually:

```bash
qualix-run my-project execute Q01 --json
qualix-run my-project finalize Q01 --json
qualix-run my-project approve Q01 --json
```

## Phase Model

```text
Q01 Requirements Structuring
├── Q02 Technical Design Generation (optional)
│   └── Q03 Technical Design Quality Review
│       └── Q04 Technical Design Coverage Audit
│           └── Q07 Code Review
└── Q05a EUT Matrix Design
    └── Q05b Unit Test Code Generation
        └── Q06 Unit Test Coverage Audit
```

| Phase | Goal | Main Output |
| --- | --- | --- |
| Q01 | Structure requirements | REQ/BR/SE/GAP/OPEN report and JSON |
| Q02 | Generate technical design | Implementation-ready design draft |
| Q03 | Review design quality | Architecture/API/data/error/performance findings |
| Q04 | Audit design coverage | Requirement-to-design coverage matrix |
| Q05a | Design executable unit-test targets | EUT matrix |
| Q05b | Generate unit-test code | Test code and execution notes |
| Q06 | Audit unit-test quality | Coverage and assertion-quality report |
| Q07 | Review code changes | Evidence-backed code review report |

Every phase follows the same lifecycle:

```text
collect evidence -> execute skill -> write report + structured JSON -> self-check -> judge/critique -> finalize -> approve
```

New to the terms? Read [Concepts](docs/concepts.md) for the short version of Phase, Gate, Harness, Judge, Critique, SE, EUT, and RSM.

## Installation Notes

The root `install.sh` installs the Python package and copies runtime resources into a user-level Qualix directory. Development mode keeps those resources symlinked to this repository:

```bash
./install.sh --dev
```

For a lighter editable install:

```bash
python -m pip install -e '.[dev]'
```

Optional extras:

```bash
python -m pip install -e '.[tree-sitter]'
python -m pip install -e '.[feishu]'
python -m pip install -e '.[vlm]'
python -m pip install -e '.[deepeval]'
```

Tree-sitter adds file-local symbol extraction and parse diagnostics for Java, TypeScript, Go, and Python. Q01 document ingest works with local Markdown/text/html files today:

```bash
qualix-run ingest docs/prd.md --project my-project
```

Enterprise document URLs are handled through the provider-based ingest layer. DingTalk and Feishu/Lark URLs are recognized as optional integrations; if a connector is not configured, Qualix explains the missing setup instead of starting OAuth automatically. For a first run, export the document from your browser or use a local Markdown/text/html file.

For model-provider configuration, see [Model Setup](docs/model-setup.md).

For ecosystem maturity, see [Language Support](docs/language-support.md). Java is the deepest path today; TypeScript, Go, and Python have built-in providers for detection and basic quality gates, plus optional Tree-sitter code intelligence.

## CLI Overview

Global commands:

```bash
qualix init
qualix dashboard start
qualix version
```

Project commands:

```bash
qualix-run <project_id> init
qualix-run <project_id> startup --json
qualix-run <project_id> status --json
qualix-run <project_id> execute <phase_id> --json
qualix-run <project_id> finalize <phase_id> --json
qualix-run <project_id> approve <phase_id> --json
qualix-run <project_id> doctor
```

## Repository Layout

```text
qualix/
├── src/qualix/          # Python package and CLI/runtime implementation
├── skills/              # Phase skills and workflow prompts
├── references/          # Report templates and risk catalogs
├── profiles/            # Language/domain profiles
├── regression/          # Regression cases and failure-library examples
├── examples/            # Synthetic input examples
├── docs/                # User and architecture docs
├── tests/               # pytest suite
├── AGENTS.md            # Codex/opencode instructions
├── CLAUDE.md            # Claude Code instructions
├── GEMINI.md            # Gemini CLI instructions
└── install.sh           # Local installer
```

## Development

```bash
ruff check src/ tests/
pytest tests/ -q
```

For a narrower smoke test after install changes:

```bash
python -m pytest tests/test_version.py tests/test_install_sh.py -q
```

## Data And Examples

The public repository should contain only synthetic or sanitized regression examples. Real enterprise failure libraries, customer requirements, and private review data should stay outside the public repo or be distributed under a separate commercial data license.

Public benchmark seeds live in [benchmarks/semantic-coverage](benchmarks/semantic-coverage/README.md). They are small, synthetic cases for inspecting semantic coverage failures by hand.

## Comparison

Qualix is adjacent to AI PR reviewers, test-generation tools, and coding-agent workflows, but its core differentiator is requirement-semantic traceability rather than line coverage or generic diff review. See [Comparison](docs/comparison.md) for details.

## Community And Security

- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Roadmap: [ROADMAP.md](ROADMAP.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Concepts: [docs/concepts.md](docs/concepts.md)
- Model setup: [docs/model-setup.md](docs/model-setup.md)
- Language support: [docs/language-support.md](docs/language-support.md)
- Comparison: [docs/comparison.md](docs/comparison.md)
- Benchmark seed cases: [benchmarks/semantic-coverage](benchmarks/semantic-coverage/README.md)
- Synthetic starter input: [examples/hello-prd.md](examples/hello-prd.md)
- Expense approval demo: [examples/expense-approval](examples/expense-approval/README.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
