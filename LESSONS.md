# LESSONS.md

Entries:

- ID: BL-20260621-evidence-locator-candidate-only
  Scope: Q05/Q06 evidence location and EvidenceCitation schema
  Trigger: Adding or consuming locator output, file-line citations, or evidence_citations for Q06 audit items.
  Do: Keep locator output EUT-scoped and treat it as candidate evidence only; Q06 audit logic and validators still decide COVERED/PARTIAL/MISSING.
  Why: Locator hits prove that text was found, not that the test assertion verifies the business semantic expectation. SE-level aggregation can hide weak assertions.
  Evidence: tests/test_ripgrep_locator.py verifies candidate_only contract and EUT-scoped citations; tests/test_schemas.py verifies EvidenceCitation rejects non-EUT IDs.

- ID: BL-20260621-q06-sidecar-upstream-context-order
  Scope: Q06 sidecar generation and upstream context loading
  Trigger: Adding Q06 sidecar files that must appear in the first _upstream_context.md.
  Do: Generate the Q06 sidecar before load_context() in the CLI execute path; execute handlers should only be later-stage or non-CLI fallback paths.
  Why: load_context() snapshots sidecar context into _upstream_context.md. If sidecar generation happens only inside an execute handler after context loading, the first Q06 prompt misses the evidence pack.
  Evidence: src/qualix/commands/phase.py pre-generates Q06 evidence citations before load_context(); src/qualix/runtime/handlers/handlers_execute.py keeps handle_evidence_citations as a fallback handler; tests/test_q06_evidence_locator_context.py verifies citations appear in Q06 upstream context.

- ID: BL-20260621-q06-checks-file-line-gate
  Scope: Q06 structure checks and validator modules
  Trigger: Adding new Q06 checks or expanding existing check logic.
  Do: Watch the 400-line file-line gate; split cohesive checks into focused helper modules when needed.
  Why: Growing q06_structure_checks.py directly makes validator logic harder to review and can violate file-size quality gates. Independent helper modules keep checks testable and maintainable.
  Evidence: src/qualix/quality/checks/q06_evidence_contract.py now holds G10 evidence-citation checks; scripts/check_file_lines.py passed with q06_structure_checks.py under the 400-line gate.
