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
- **Phase failure patterns benchmark**: public Q01/Q05a/Q06 synthetic failure patterns backed by `regression/failure-library/` and validated by `scripts/check_phase_failure_patterns.py`

## Current Focus

**End-to-end verifiability**

The biggest gap right now is that visitors cannot independently run Qualix and verify its claims in under 10 minutes. The `examples/expense-approval/` directory has the right PRD and implementation, but the full Q01 → Q05a → Q06 chain needs a scripted path that works without configuration.

Done in the P0 proof loop:
- `qualix-run expense-demo run-demo --json` materializes the synthetic expense-approval Q01 → Q05a → Q06 outputs without a model API key, runs the public test signal when possible, computes semantic coverage, and writes an EvidenceGraph for `qualix-run expense-demo explain SE-003 --json`

**Improving the first-time experience**

Done in the P1 onboarding loop:
- `qualix-run <project_id> check --prd <path> --code <dir> --profile <profile> --json` initializes the workspace, creates project state, ingests the PRD, records code repos, and returns an exact Q01 → Q05a → Q06 phase plan without requiring a model API key.

Done in the P2 first-run hardening loop:
- `scripts/check_installed_wheel_smoke.py` builds or reuses a wheel, installs it into a clean temporary virtualenv outside the source tree, and verifies both `check --json` and `run-demo --json` against the installed package.
- `.github/workflows/qualix-self-check.yml` now runs the installed-wheel smoke on PR/push, and `.github/workflows/publish.yml` runs it after `hatch build` before publishing to PyPI.

**Python Q05b**

Python test generation is still earlier than Java, but the P3 hardening loop closed the initial compile/import and pytest-template gaps documented in [Language Support](docs/language-support.md). Target milestone: 0.3.0.

Done in the P3 Python Q05b hardening loop:
- Q05b now dispatches `language_id=python` to a Python deterministic gate that runs `PythonProvider.compile_check()` across configured code repos.
- Python compile validation now combines `compileall` with subprocess import validation that supports common `src/` layouts and catches import-time failures that syntax checks miss.
- `profiles/python-service/templates/pytest_mock_patterns.py.tmpl` provides standard pytest patterns for constructor injection, `unittest.mock.patch`, `pytest-mock`, parametrized boundaries, exceptions, and side-effect assertions.

**Public benchmark coverage**

Done in the P4 benchmark loop:
- `benchmarks/phase-failure-patterns/manifest.json` maps public failure-library seeds to phase-specific failure patterns for Q01, Q05a, and Q06.
- `scripts/check_phase_failure_patterns.py` validates the benchmark manifest, linked case metadata, synthetic/sanitized source safety, and phase/case ID alignment.
- `scripts/check_publish_readiness.py` runs the phase-failure-pattern checker so release readiness fails on benchmark schema drift.

## Near-Term (0.3.0)

- Python Q05b: expand real-world fixture coverage and coverage-report normalization
- End-to-end demo hardening: keep `run-demo` stable across packaged installs and add one CI smoke test for the installed wheel
- Expanded benchmark: add more sanitized phase failure patterns beyond the Q01/Q05a/Q06 seed set

## Longer-Term

- VS Code extension (MVP): sidebar showing SE coverage status for the open file
- GitHub App: zero-config PR comment posting without a YAML workflow
- Online sandbox: paste a PRD, get Q01 output without installing anything
- Multi-model benchmark: compare Q06 finding quality across GPT / Claude / Gemini on the public benchmark cases

**SE weight modeling** (issue #se-weights): today semantic_coverage_rate treats all SEs equally. A SE that captures the core business invariant (e.g., the boundary at exactly 500 USD) should carry more weight than an auxiliary SE (e.g., audit log format). This issue tracks adding an optional `weight` field to SE items (values: `critical` / `high` / `normal`, defaulting to `normal`) so that Q06 can produce a weighted semantic coverage score alongside the unweighted one. This aligns with the weight modeling used in Scale AI's Agentic Rubrics work (arXiv:2601.04171), where must-have criteria (weight=3) dominate patch selection over nice-to-have criteria (weight=1). Prerequisite: establish a weighting heuristic in Q01 based on RE/BR coupling strength before exposing the field to users.

**Q06 failure axis tagging** (issue #failure-axis): Q06 audit items currently report status (COVERED / PARTIAL / MISSING / WRONG_TARGET) and severity, but not *why* the item failed. Tagging each non-COVERED item with a failure axis — `spec_alignment` (SE not tested), `integrity` (test written but assertion weakened), `runtime` (behavior incorrect), or `scope` (wrong module targeted) — enables per-axis rollup in the dashboard and gives developers actionable triage ("write the test" vs "fix the assertion" vs "fix the logic"). Inspired by the four-axis rubric structure in arXiv:2601.04171.

**Q01 over-specification guard** (issue #se-overspec): SEs that describe implementation means ("must call XxxValidator.check()") rather than observable outcomes ("must return HTTP 400 with errorCode=INVALID_AMOUNT") produce false MISSING findings in Q06 when equivalent implementations satisfy the business rule via a different code path. Adding an over-specification check to Q01's SE quality gate — analogous to the low-utility rubric patterns (Over-Specified Fix, Spec Clash) identified in arXiv:2601.04171 — would reduce Q06 false positive rate without changing the audit logic.

**Incremental re-run and output versioning** (issue #incremental-rerun): three design patterns worth adopting once real-world re-run latency becomes a user complaint — (1) `isLatest` + `parent_run_id` on SE/EUT/Q06 outputs so dashboard and CLI surface current results without relying on directory timestamp ordering; (2) `stability: "core" | "derived"` field on SE items so core SEs (bound to stable PRD requirements) are not regenerated on every run; (3) EUT upsert keyed on `(pid, eut_id, phase)` so unchanged EUTs reuse the previous Q06 judge score rather than re-scoring from scratch. Inspired by the version-chain and deduplication patterns in supermemoryai/supermemory (not a dependency — patterns only).

## Not Planned

- Replacing existing test runners (pytest, JUnit, Jest) — Qualix sits above them
- Generic diff review without requirement traceability — that is what existing AI PR reviewers do
- Distributed agent infrastructure — the subprocess isolation in 0.2.0a1 is the right boundary

## Licensing

The core phases (Q01–Q07), CLI, all profiles, and all skills are Apache 2.0 and will remain so. Any future commercial offerings would focus on hosted services and team collaboration tooling, not on gating core functionality.

## Feedback

Open an issue or start a discussion on GitHub if something here is wrong, missing, or should be prioritized differently.
