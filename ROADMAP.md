# Qualix Roadmap

Qualix is in public alpha. This roadmap describes the major directions, not a fixed release schedule. Priorities shift as we learn from real usage.

## Current Focus

**Stabilizing the phase model**

The Q01–Q07 phase pipeline is functional. Current work is hardening the contract between phases and making the harness easier to adopt without deep familiarity with the codebase.

- Tighter schema validation with per-iteration feedback inside the adaptive loop (so agents fix errors before finalize, not after)
- `phase_b_structured.schema.json` documentation for Q05a output
- Guard precision dashboard for tracking false-positive and false-negative rates on rationalization checks

**Language support breadth**

Java has the deepest path today. TypeScript, Go, and Python have built-in providers for detection and basic quality gates. The next step is expanding compile and assertion-quality gates to TypeScript (Jest) and Go (testing package).

See [Language Support](docs/language-support.md) for current status.

## Near-Term

- `Q02` optional design-generation phase: improve coverage when a technical design does not exist yet
- Expanded regression benchmark: synthetic cases for each phase covering the most common failure patterns
- Structured changelog in CHANGELOG.md as the project moves toward a stable `1.0.0`

## Longer-Term

- Profile versioning and compatibility selectors (`java-ddd-tmf@v2`)
- CI/PR gate integration: GitHub Action wrapper that runs selected phases against a diff and posts structured findings
- PyPI distribution: `pip install qualix`

## Not Planned

- Replacing existing test runners (pytest, JUnit, Jest) — Qualix sits above them
- Generic diff review without requirement traceability — that is what existing AI PR reviewers do

## Feedback

If something here is wrong, missing, or should be prioritized differently, open an issue or start a discussion on GitHub.
