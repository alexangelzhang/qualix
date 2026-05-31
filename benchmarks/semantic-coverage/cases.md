# Semantic Coverage Seed Cases

## Case SC-001: Inclusive Threshold

Requirement:

> Requests at or above 500 USD require manager and finance approval.

Weak tests:

```text
120 USD -> payment ready after manager approval
600 USD -> manager approved, finance still required
```

Expected finding:

The test suite misses exactly 500 USD. A semantic coverage gate should not mark the threshold rule covered until the boundary value is tested.

## Case SC-002: Idempotent Side Effect

Requirement:

> Repeating the same approval request must not create a second audit entry or send a second notification.

Weak test:

```python
approved = approve_by_manager(request, actor_id="manager-1")
assert len(approved.audit_log) == 1
```

Expected finding:

The test never retries the same approval command. It proves the first audit row, not idempotency.

## Case SC-003: Visible Rejection Reason

Requirement:

> A rejected request must include a rejection reason visible to the requester.

Weak test:

```python
assert reject(request, reason="duplicate").status == "REJECTED"
```

Expected finding:

The test checks state only. It does not prove that the requester can see the reason.

## Case SC-004: Decimal Money Comparison

Requirement:

> Amount comparison must use decimal arithmetic, not floating point.

Weak test:

```python
assert classify_amount(100.10 + 399.90) == "FINANCE_REQUIRED"
```

Expected finding:

The test uses floating-point input and does not prove decimal arithmetic. A stronger test should use `Decimal` or inspect the implementation boundary where money is parsed.

## Case SC-005: Self-Approval

Requirement:

> A manager cannot approve their own request.

Weak test:

```python
assert approve_by_manager(request, actor_id="manager-1").status in {"PAID_READY", "MANAGER_APPROVED"}
```

Expected finding:

The test never sets `actor_id == requester_id`. The self-approval rule is uncovered.

## Case SC-006: Transport Success Is Not Business Success

Requirement:

> Duplicate active rule codes under the same account must be rejected with `Rule code already exists`.

Weak test:

```python
response = client.post("/rules", json=payload)
assert response.status_code == 200
```

Expected finding:

The assertion checks transport success for a create call. It does not create an existing active rule, submit a duplicate, or assert the required error message.

