# Python Service Baseline

## Test Shape

- Use `pytest` for unit and service-level tests.
- Keep tests readable with Arrange-Act-Assert structure.
- Prefer explicit value and side-effect assertions over truthiness checks.
- Use `pytest.raises` for expected exceptions and assert the business state after failure when state can change.
- For Q05b generation, start from `profiles/python-service/templates/pytest_mock_patterns.py.tmpl` and keep the `# EUT-xxx SE-xxx` traceability comment as the first line of each test body.

## Mock Templates

- Prefer constructor injection with `MagicMock` when the dependency is passed into `__init__`.
- Use `patch("module.under.test.Dependency")` when the production module imports the dependency directly.
- Use the `mocker` fixture only when `pytest-mock` is declared; otherwise use `unittest.mock`.
- For boundary rules, use `pytest.mark.parametrize` and assert each expected outcome explicitly.
- Verify side effects by inspecting saved payloads or emitted events, not just `assert_called()`.

## Assertion Quality

- Good: `assert result.status == "MANAGER_APPROVED"`.
- Good: `assert len(request.audit_log) == 1` after a retry.
- Weak: `assert result`.
- Weak: `mock_client.send.assert_called()` without checking payload or user-visible outcome.

## Domain Rules

- Use `Decimal` for money and threshold comparisons.
- Keep idempotency rules close to the domain/application layer, not only in handlers.
- Validate requester-visible error messages when the requirement names one.

## Default Quality Thresholds

- Line coverage >= 80%.
- Branch coverage >= 75%.
- Semantic coverage should be judged from requirement-bound EUTs, not line coverage alone.
