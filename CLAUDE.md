# CLAUDE.md — Claude Code Agent Instructions

> General project knowledge is in `AGENTS.md`. This file contains only Claude Code CLI–specific behavior instructions.

<critical>
Three unbreakable rules (check before every action):

1. SPEC OVER SKILL: Before executing any Phase, MUST run `dqg-run <pid> spec --phase Q0X --json` to get the contract. When spec and SKILL.md conflict, spec always wins.
2. EUT-PER-ITEM: Q05a/Q05b/Q06 output MUST have one audit_item per eut_id. NEVER aggregate by SE (SE-based pattern).
3. JSON-FLAG: All `dqg-run` calls MUST include `--json`. NEVER parse prose output.

Consequences: spec mismatch → schema rejection; SE-based → coverage inflation hiding weak assertions; missing --json → prose drift causes parse errors.
</critical>

## Behavior Anchors

- **Evidence-first** — Any output must be self-verified. If a SubAgent says "tests pass", re-run `mvn test` in the main session to confirm.
- **Failure library awareness** — Before executing any Phase, check `regression/failure-library/` for high-frequency error patterns for that Phase.
- **First principles** — Start from requirements, not analogies. Writing tests = "verifying business semantics", not "hitting coverage numbers".
- **Rule respect** — Rules in this file are red lines, not suggestions. Priority: CLAUDE.md > dqg_starter.md > skill files > your judgment.
- **Right first time** — EUT `then` fields must contain concrete assertion methods and expected values. Never rely on a re-run to fix what should have been correct.

## Entry Points

- `/dqg-starter` — Quick start
- `dqg-run <project_id> startup` — CLI startup

## Behavioral Rules

- Phase tasks MUST load the corresponding skill file; never improvise outside the skill.
- **Before starting any Phase, run `dqg-run <pid> spec --phase Q0X --json`**: read required fields/constraints from `json_schema`, gate conditions from `contract.hard_checks`, dependencies from `phase_registry`. When spec and SKILL.md conflict, spec wins.
- All state management through `dqg-run` CLI; never manually edit `state.json`. Add `--json` to all `dqg-run` calls.
- Four-step close: detect output → finalize → approve → refresh menu. Before finalize, check gate checklist item by item.
- After code changes, sync instruction files — `completion_gate.py` auto-detects and blocks if out of sync.

<important if="executing any Phase in manual mode">
In manual mode, do NOT dispatch a SubAgent to execute the Phase. Execute the skill directly in the main session.
CLAUDE.md takes priority over dqg_starter.md when they conflict.
</important>

<important if="writing or reviewing EUT then fields">
The `then` field MUST contain a concrete assertion method and expected value (e.g., `assertEquals(200, response.getStatus())`).
Vague descriptions like "verify success" or "return correct result" are NOT acceptable.
</important>

## Self-Check (Before Every Action)

Answer these questions before any tool call. If the answer to any is "yes", stop and switch approach:

1. **Am I dispatching an Agent to execute a Phase?** → Forbidden in manual mode. Execute the skill directly.
2. **Am I using grep to search code?** → Use code search tools first; fall back to grep only if unavailable.
3. **Did a SubAgent report "tests passed"?** → Don't trust it. Re-run `mvn test` in the main session.
4. **Do dqg_starter.md and CLAUDE.md conflict?** → CLAUDE.md has higher priority.
5. **Are Q05a/Q05b/Q06 outputs using SE-based pattern (aggregating by SE)?** → Forbidden. Each audit_item must correspond to one eut_id.
6. **Am I starting a Phase without running `dqg-run <pid> spec --phase Q0X --json`?** → Run spec first.
7. **Am I calling `dqg-run` without `--json`?** → Add it.

> The ironlaw guard hook (`ironlaw_guard.py`) auto-checks Agent/Grep/Bash calls, but hooks can only catch obvious violations. This self-check covers semantic scenarios hooks cannot detect.

## Lessons Learned

- SE IDs must be consistent across Phases. If Q01 uses `SE-001`, all downstream Phases must use `SE-001`, never `SE-1`. Mismatches cause RSM coverage to drop to zero.
- For deep-reasoning Phases (Q04, Q06), adding `ultrathink` to the startup prompt activates stronger reasoning mode.
- **Q05a/Q05b/Q06 must use EUT-per-item mode**: each `audit_item` must map to a single `eut_id`. The SE-based pattern obscures per-test assertion quality issues.
- **SubAgent outputs require sanity checks**: after receiving an analysis report, directly `json.load` the raw data in the main session and verify 1–2 key claims before trusting the report.

*Last updated: 2026-05-30*

<critical>
Restating three rules (Lost-in-the-Middle defense, repeated at end of file):

1. SPEC OVER SKILL — Run `dqg-run <pid> spec --phase Q0X --json` before SKILL.md. Spec wins on conflict.
2. EUT-PER-ITEM — Each audit_item in Q05a/Q05b/Q06 must independently correspond to one eut_id. NEVER aggregate by SE.
3. JSON-FLAG — All `dqg-run` calls MUST include `--json`.
</critical>
