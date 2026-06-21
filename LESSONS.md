# LESSONS.md

Entries:

- ID: BL-20260621-evidence-locator-candidate-only
  Scope: Q05/Q06 evidence location and EvidenceCitation schema
  Trigger: Adding or consuming locator output, file-line citations, or evidence_citations for Q06 audit items.
  Do: Keep locator output EUT-scoped and treat it as candidate evidence only; Q06 audit logic and validators still decide COVERED/PARTIAL/MISSING.
  Why: Locator hits prove that text was found, not that the test assertion verifies the business semantic expectation. SE-level aggregation can hide weak assertions.
  Evidence: tests/test_ripgrep_locator.py verifies candidate_only contract and EUT-scoped citations; tests/test_schemas.py verifies EvidenceCitation rejects non-EUT IDs.
