# Goal Tracker — P3 Python Q05b Hardening

## IMMUTABLE Acceptance Criteria
- P3 makes Python Q05b less experimental by wiring Python compile/import validation into the deterministic Q05b test execution gate.
- The gate must run on configured Python code repos and return BLOCKED errors for syntax/import/runtime import failures in generated tests.
- The import check must work for common `src/` layouts and plain package layouts without requiring the Qualix source checkout as cwd.
- P3 must add a standard pytest mock template library covering constructor injection, `unittest.mock.patch`, `pytest-mock`, `pytest.mark.parametrize`, exception checks, and side-effect assertions.
- Python Q05b docs must explain that `compileall` alone is insufficient and that import validation is part of the gate.
- Do not overwrite unrelated P0/P1/P2 or user WIP already present in the working tree.

## Mutable Notes
- ROADMAP points to Python Q05b as the next near-term item after first-run UX hardening.
- `PythonProvider.compile_check()` already has a draft import-check path, but Q05b dispatch only routes TypeScript, Go, and Java.
- `profiles/python-service/baseline.md` has assertion guidance but no reusable mock templates yet.
