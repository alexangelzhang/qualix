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

## Reporting Issues

Please include:

- Qualix version and install method.
- OS and Python version.
- The command you ran.
- Relevant error output or a sanitized `qualix-run doctor --no-upload` bundle.

## Project Status

Qualix is not yet stable `1.0.0`. APIs, report schemas, and phase outputs may change while the phase model is being validated.
