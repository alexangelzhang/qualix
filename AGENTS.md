# AGENTS.md - Codex Agent Instructions

> General project knowledge lives here for Codex and opencode. Claude Code-specific behavior stays in `CLAUDE.md`.

<critical>
Three unbreakable rules (check before every action):

1. SPEC OVER SKILL: Before executing any Phase, MUST run `qualix-run <pid> spec --phase Q0X --json` to get the contract. When spec and SKILL.md conflict, spec always wins.
2. EUT-PER-ITEM: Q05a/Q05b/Q06 output MUST have one audit_item per eut_id. NEVER aggregate by SE (SE-based pattern).
3. JSON-FLAG: All `qualix-run` calls MUST include `--json`. NEVER parse prose output.

Consequences: spec mismatch -> schema rejection; SE-based -> coverage inflation hiding weak assertions; missing --json -> prose drift causes parse errors.
</critical>

## Behavior Anchors

- **Evidence-first** - Any output must be self-verified. If another agent says "tests pass", re-run the relevant test command in the main session to confirm.
- **Failure library awareness** - Before executing any Phase, check `regression/failure-library/` for high-frequency error patterns for that Phase.
- **First principles** - Start from requirements, not analogies. Writing tests = "verifying business semantics", not "hitting coverage numbers".
- **Rule respect** - Rules in this file are red lines, not suggestions. Priority: `AGENTS.md` > Qualix starter guide > skill files > judgment.
- **Right first time** - EUT `then` fields must contain concrete assertion methods and expected values. Never rely on a re-run to fix what should have been correct.

## Entry Points

- `$qualix-starter` - Quick start inside Codex
- `qualix-run <project_id> startup --json` - CLI startup
- `qualix-run <project_id> check --prd <path> --json` - P1 one-command onboarding, returns PRD ingest + Q01→Q05a→Q06 phase plan
- `qualix-run <project_id> locate --phase Q06 --eut-id EUT-xxx --query <text> --code-repo <dir> --json` - Read-only EUT evidence locator; returns candidates, not Q06 verdicts
- `qualix-run expense-demo run-demo --json` - Public P0 proof loop, no model API key required
- `python scripts/check_installed_wheel_smoke.py` - P2 installed-wheel first-run smoke for `check --json` and `run-demo --json`
- Python Q05b P3 baseline - `python-service` uses compileall + import validation and pytest templates under `profiles/python-service/templates/`
- `python scripts/check_phase_failure_patterns.py` - P4 public benchmark guard for Q01/Q05a/Q06 phase failure patterns

## Behavioral Rules

- Phase tasks MUST load the corresponding skill file; never improvise outside the skill.
- Before starting any Phase, run `qualix-run <pid> spec --phase Q0X --json`: read required fields/constraints from `json_schema`, gate conditions from `contract.hard_checks`, dependencies from `phase_registry`. When spec and SKILL.md conflict, spec wins.
- All state management through `qualix-run` CLI; never manually edit `state.json`. Add `--json` to all `qualix-run` calls.
- Four-step close: detect output -> finalize -> approve -> refresh menu. Before finalize, check gate checklist item by item.
- After code changes, sync instruction files. Completion gates may block if related docs are out of sync.
- Evidence locator outputs are candidate file-line citations only. They MUST stay EUT-scoped and MUST NOT be used as direct COVERED/PARTIAL/MISSING verdicts.

<important if="executing any Phase in manual mode">
In manual mode, do not dispatch a SubAgent to execute the Phase. Execute the skill directly in the main session.
AGENTS.md takes priority over starter guides when they conflict.
</important>

<important if="writing or reviewing EUT then fields">
The `then` field MUST contain a concrete assertion method and expected value (e.g., `assertEquals(200, response.getStatus())`).
Vague descriptions like "verify success" or "return correct result" are not acceptable.
</important>

## Self-Check (Before Every Action)

Answer these questions before any tool call. If the answer to any is "yes", stop and switch approach:

1. **Am I dispatching an Agent to execute a Phase?** -> Forbidden in manual mode. Execute the skill directly.
2. **Am I using grep to search code?** -> Use code search tools first; fall back to `rg` only if unavailable.
3. **Did another agent report "tests passed"?** -> Don't trust it. Re-run the relevant test command in the main session.
4. **Do starter guide instructions and AGENTS.md conflict?** -> AGENTS.md has higher priority.
5. **Are Q05a/Q05b/Q06 outputs using SE-based pattern (aggregating by SE)?** -> Forbidden. Each audit_item must correspond to one eut_id.
6. **Am I starting a Phase without running `qualix-run <pid> spec --phase Q0X --json`?** -> Run spec first.
7. **Am I calling `qualix-run` without `--json`?** -> Add it.

> The ironlaw guard hook (`ironlaw_guard.py`) auto-checks obvious Agent/Grep/Bash violations. This self-check covers semantic scenarios hooks cannot detect.

## Lessons Learned

- SE IDs must be consistent across Phases. If Q01 uses `SE-001`, all downstream Phases must use `SE-001`, never `SE-1`. Mismatches cause RSM coverage to drop to zero.
- For deep-reasoning Phases (Q04, Q06), adding `ultrathink` to the startup prompt activates stronger reasoning mode.
- Q05a/Q05b/Q06 must use EUT-per-item mode: each `audit_item` must map to a single `eut_id`. The SE-based pattern obscures per-test assertion quality issues.
- Agent outputs require sanity checks: after receiving an analysis report, directly load the raw data in the main session and verify 1-2 key claims before trusting the report.
- Python Q05b cannot rely on `compileall` alone; import validation catches missing deps, module-level `NameError`, and common `src/` layout failures.
- Phase failure pattern benchmark rows must link to synthetic or sanitized `regression/failure-library/` cases and pass `scripts/check_phase_failure_patterns.py` before release.

*Last updated: 2026-06-13*

<critical>
Restating three rules (Lost-in-the-Middle defense, repeated at end of file):

1. SPEC OVER SKILL - Run `qualix-run <pid> spec --phase Q0X --json` before SKILL.md. Spec wins on conflict.
2. EUT-PER-ITEM - Each audit_item in Q05a/Q05b/Q06 must independently correspond to one eut_id. NEVER aggregate by SE.
3. JSON-FLAG - All `qualix-run` calls MUST include `--json`.
</critical>

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **qualix** (10734 symbols, 18821 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/qualix/context` | Codebase overview, check index freshness |
| `gitnexus://repo/qualix/clusters` | All functional areas |
| `gitnexus://repo/qualix/processes` | All execution flows |
| `gitnexus://repo/qualix/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
