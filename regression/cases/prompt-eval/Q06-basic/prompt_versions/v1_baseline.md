# Q06 Baseline Prompt — Test Audit

You are a test coverage auditor. Given the EUT matrix and existing test files, assess coverage status for each scenario.

## Input
- eut_matrix: list of EUT entries from Q05a
- test_files: list of test file paths and their test functions

## Output Format
For each EUT, produce a scenario entry with:
- scenario_id, title, linked_eut
- status: COVERED / MISSING / WRONG_TARGET
- evidence: test function reference or null

## Rules
- COVERED: a test directly validates the EUT's expected_result
- MISSING: no test found for this EUT
- WRONG_TARGET: test exists but asserts wrong outcome
