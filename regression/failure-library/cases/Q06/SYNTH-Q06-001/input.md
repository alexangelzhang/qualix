# Synthetic Q06 Failure Input

PRD rule:

Status transitions must be idempotent. Repeating the same approval request must not create a second audit entry or send a second notification.

Test suite excerpt:

```python
def test_small_request_can_be_manager_approved():
    request = ExpenseRequest(amount_usd=Decimal("120"))
    approved = approve_by_manager(request, actor_id="manager-1")
    assert approved.status == "PAID_READY"
    assert len(approved.audit_log) == 1
```

Implementation excerpt:

```python
def approve_by_manager(request, actor_id):
    request.status = next_status_after_manager_approval(request, actor_id)
    request.audit_log.append({"actor_id": actor_id})
    return request
```

Missing check: call `approve_by_manager` twice and assert the audit log remains length 1.

