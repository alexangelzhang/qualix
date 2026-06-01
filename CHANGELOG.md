# Changelog

All notable changes to Qualix are documented here.

---

## 2026-05-31 — Q05a/Q05b semantic split

- Removed standalone Q05 from phase registry; Q05a (EUT matrix design) and Q05b (unit test codegen) are now separate phases with distinct gates
- Q05a finalize gate: EUT coverage, concrete `then` fields, SE traceability
- Q05b finalize gate: real compile check, weak assertion gate (high-risk ≥ 1 blocked), multi-repo completeness
- DAG scheduler: parallel batches derived from dependency antichain; failed phases excluded from worker/adaptive; finalize failure counted as DAG failure
- New CLI flags: `--auto-approve`, `--force-skip`, `--skip-reason`; `skip` command respects `phase_def.skippable`
- DAG resume reads running checkpoint

## 2026-05-22 — Infrastructure hardening

- `qualix-run ingest` enterprise document URL provider (DingTalk, Feishu/Lark)
- Tree-sitter code intelligence provider for Java, TypeScript, Go, Python
- Public regression fixtures sanitized; internal project names removed from all public examples and tests

## 2026-05-10 — Skill governance and Q05a/Q06 quality

- `adaptive_loop` schema validation feedback loop design (T14): schema errors from `validate_phase_output` will feed into next-iteration worker prompt
- Q05a branch coverage guardrail (`Q05BranchCoverageGuardrail`)
- Unified enum source (`EnumSource`) injected into worker and judge prompts
- Schema–prompt consistency CI hook (`check_schema_prompt_sync.py`)

## 2026-05-09 — System health improvements (T1–T8, T11)

- Q03 `failure_modes` schema + required field checklist
- Q05a → Q06 EUT ID subset hard constraint (`validate_eut_id_subset`)
- Failure-library `lesson` backfill (1776 cases) and `case_category` five-type taxonomy
- Guard precision report (`reporting/guard_precision_report.py`)
- `RationalizationProbeGuardrail` field-level check

## 2026-04-09 — LLM-as-Judge and self-critique loop

- LLM-as-Judge automatic review after `finalize` for Q01/Q04/Q03/Q06
- Self-Critique + RLAIF preference loop; effective critique saved as bug case
- Structured bug case library per phase (`regression/failure-library/`)
- Case auto-injection: relevance-matched examples injected at skill execution time
- Multi-platform agent instructions: `AGENTS.md` (Codex/opencode), `GEMINI.md`, `.cursor/rules/qualix.mdc`
- Rule-level quality tracking: health score and known-pattern hit on `finalize`
- Cross-project knowledge injection (`_cross_project_insights.md`)
- Phase Q05b compile-verification gate
- Runtime kernel (11 independent handlers)
- Cross-session progress file, session startup protocol, task store
- Dynamic Judge grading criteria, blast-radius impact analysis
- Judge anti-rationalization table, confidence tagging

## 2026-04-02 — Output path restructure

- Output path changed from `output/{id}_phaseA/` to `output/{id}/phaseA/`; `state.json` moved into project subdirectory
- Feishu image parallel download (8 workers, ~5–8× faster)
- Exception matrix extended to 364 entries with Java DDD+TMF trigger conditions
- Test suite expanded from 85 to 129 cases

## 2026-04-01 — Regression cases

- 87 real bug cases imported from internal Feishu Bitable (sanitized before public release)
- 4 hand-authored synthetic examples: concurrent idempotency, coverage misclassification, RPC without compensation, weak assertions
