# Qualix

AI-native development quality gates for requirements, designs, tests, and code reviews.

Qualix turns product requirements into traceable engineering checks. Instead of stopping at line coverage, it follows requirement IDs through design coverage, test intent, generated unit tests, audit reports, and review findings.

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
git clone https://github.com/alexangelzhang/qualix.git
cd qualix
./install.sh --dev
```

Then initialize a project workspace:

```bash
cd /path/to/your/project
qualix-run my-project init --profile java-ddd-tmf
qualix-run my-project startup --json
```

To try Qualix without private project data, start with the synthetic example in [examples/hello-prd.md](examples/hello-prd.md).

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
python -m pip install -e '.[feishu]'
python -m pip install -e '.[vlm]'
python -m pip install -e '.[deepeval]'
```

Feishu/Lark ingestion is optional. Local Markdown or text requirement files work for basic experiments.

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

## Community And Security

- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Synthetic starter input: [examples/hello-prd.md](examples/hello-prd.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
