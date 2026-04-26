# Q06 Enhanced Prompt — Test Audit

Goal: assess EUT coverage against the test codebase with direct evidence, mismatch detection, and confidence labels.

## Input
- eut_matrix: list of EUT entries from Q05 with steps and expected results
- test_files: list of test file paths, function names, and assertion targets

## Output Format
For each EUT, produce a scenario entry with:
- scenario_id, title, linked_eut
- status: COVERED / MISSING / WRONG_TARGET / PARTIAL
- evidence: test function reference with file path, or null
- confidence: HIGH / MEDIUM / LOW

## Rules
- COVERED: test directly validates the EUT's expected_result with correct assertion
- MISSING: no test found for this EUT
- WRONG_TARGET: test exists but asserts a different outcome than expected_result
- PARTIAL: test covers some steps but not the full scenario
- When status is WRONG_TARGET, explain the mismatch in evidence field
- Cross-reference SE judgment_basis when available for higher confidence
- Flag any test that covers multiple EUTs (potential weak isolation)
