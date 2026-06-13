# Goal Tracker — P1 One-Command Onboarding

## IMMUTABLE Acceptance Criteria
- P1 turns `qualix-run <project_id> check --prd <path> --code <dir> --profile <profile> --json` into a stable PRD → executable phase plan onboarding command.
- The default path must not require a model API key and must not execute AI phase reasoning itself.
- Output must be pure JSON when `--json` is supplied, including project id, PRD path, code paths, profile, initialized/ingested signals, ordered phase plan, and next commands.
- State changes must go through existing Qualix command/runtime APIs; do not manually edit `state.json`.
- The command must be idempotent enough for first-time users to rerun after a partial setup.
- Do not overwrite unrelated user changes already present in the working tree.

## Mutable Notes
- P0 public proof loop is complete: `qualix-run expense-demo run-demo --json` materializes Q01 → Q05a → Q06 and points to `explain` via EvidenceGraph.
- Existing WIP already has `src/qualix/commands/check.py`, README snippets, and runner dispatch for `qualix-run <pid> check --prd ...`; P1 should harden this path instead of rewriting from scratch.
- `check` is an onboarding on-ramp, not a replacement for the agent loop: it prepares workspace/input and prints the exact execute/finalize/approve sequence.
