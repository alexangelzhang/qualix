# Q05a Enhanced Prompt — Test Generation

Goal: generate a complete EUT matrix from structured requirements, with explicit happy and exception paths.

## Input
- requirements: list of REQ/BR items with descriptions
- semantic_expectations: list of SE items with judgment basis

## Output Format
For each requirement, generate EUT entries with:
- eut_id, title, route_type (Happy Path / Exception Path / Edge Case)
- linked_req, steps (ordered), expected_result

## Rules
- Each REQ must have at least one Happy Path AND one Exception Path
- SE items with judgment_basis must map to at least one EUT
- Steps must be atomic and verifiable (no compound actions)
- Exception paths must include the trigger condition in steps
- Prefer 3-5 steps per EUT; split if exceeding 7
