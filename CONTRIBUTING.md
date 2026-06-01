# Contributing to Qualix

Thanks for helping improve Qualix. The project is in public alpha, so small, focused changes are the easiest to review.

## Development Setup

```bash
git clone https://github.com/alexangelzhang/qualix.git
cd qualix
python -m pip install -e '.[dev]'
```

Run the core checks before opening a pull request:

```bash
python scripts/check_publish_readiness.py
python -m compileall -q src/qualix tests scripts
python -m pytest tests/ -q
```

## Pull Request Guidelines

- Keep changes scoped to one topic.
- Add or update tests when behavior changes.
- Update README or docs when user-facing commands, paths, outputs, or workflows change.
- Do not commit real customer requirements, private review data, internal links, or production failure-library cases.
- Use synthetic or sanitized examples under `regression/failure-library/`.

## Adding a New Language Profile

A profile tells Qualix how to detect your language, run tests, and find assertion patterns. The four built-in profiles (`java-ddd-tmf`, `typescript-service`, `go-service`, `python-service`) are the best starting point.

See [docs/custom-profile.md](docs/custom-profile.md) for a step-by-step guide. The minimum required file is `profiles/<profile-id>/profile.json`. A `baseline.md` adds language-specific rules for Q05a/Q06.

When contributing a new profile:
- Use a synthetic project as the acceptance test — no real customer code.
- Add at least one entry to `benchmarks/semantic-coverage/cases.md` that exercises a finding your profile can catch.

## Contributing Benchmark Cases

The `benchmarks/semantic-coverage/cases.md` file is the easiest place to contribute. Each case is:

1. A short requirement statement (one or two sentences).
2. A plausible weak test that passes line coverage but misses the semantic rule.
3. The expected finding Qualix should report.

Cases SC-007 to SC-016 were derived from real pipeline runs and show the expected format. A good case exposes a class of semantic miss not already covered — boundary values, idempotency, mutual exclusion, OR-logic branches, and side-effect counts are the most productive areas.

## Reporting Issues

Please include:

- Qualix version (`qualix version`) and install method.
- OS and Python version.
- The command you ran.
- Output of `qualix-run doctor` (sanitized — remove project names, tokens, and internal paths).

## Project Status

Qualix is not yet stable `1.0.0`. APIs, report schemas, and phase outputs may change while the phase model is being validated.
