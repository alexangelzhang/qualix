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

---

## Cases from Production Pipelines

The following cases were derived from real Q01→Q06 pipeline runs on production Java services, then sanitized to remove all identifying information. The business rules and assertion gaps are real; the domain names are synthetic.

### Fulfillment-Domain Cases (SC-007 to SC-011)

These cases come from an order fulfillment service with a conditional routing rule: some order types use a fulfillment center integration; others fall back to a legacy path.

---

## Case SC-007: Conditional Interface Call — Negative Branch Not Tested

Requirement:

> When the order category is not eligible for the fulfillment-center path, the system must fall back to the legacy flow and must not call the fulfillment-center API.

Weak test:

```java
@Test
void eligibleCategory_callsFulfillmentCenter() {
    OrderResult result = service.route(order(ELIGIBLE_CATEGORY));
    verify(fulfillmentClient, times(1)).submit(any());
}
```

Expected finding:

The test proves the positive branch (eligible → API called once). The negative branch — ineligible category → API must not be called — has no test. A semantic coverage gate should flag the missing assertion on `verify(fulfillmentClient, never())`.

---

## Case SC-008: Two-Phase Validation — Second Phase Outcome Ignored

Requirement:

> Eligibility is checked twice: once at order creation and once at a later status transition. The second check may return a different result, and its outcome governs the final submission.

Weak test:

```java
@Test
void creationPhase_eligibleResult_orderCreated() {
    OrderResult result = service.create(order);
    assertEquals(OrderStatus.CREATED, result.getStatus());
}
```

Expected finding:

The test covers the first eligibility check at creation time. The second check — triggered at the status transition — is untested. A gate should flag that the requirement has two distinct check points and only one is covered.

---

## Case SC-009: Multi-Condition Gate — Parametric Coverage Gap

Requirement:

> Submission is only allowed when both conditions are met: fulfillment-path eligible AND processing-method is X. All other combinations must be rejected.

Weak test:

```java
@Test
void bothConditionsMet_returns200() {
    Response r = service.submit(order(ELIGIBLE, METHOD_X));
    assertEquals(200, r.getStatus());
}
```

Expected finding:

The test covers only the one passing combination. The requirement implies four combinations: (eligible, X), (ineligible, X), (eligible, not-X), (ineligible, not-X). Three rejection cases are uncovered.

---

## Case SC-010: Required Fields — Missing Negative Parametric Tests

Requirement:

> The upstream API call requires four mandatory fields: item ID, category ID, shipping address, and contact info. If any field is absent the call must be rejected with a validation error.

Weak test:

```java
@Test
void allFieldsPresent_callSucceeds() {
    Response r = client.call(request(ITEM_ID, CATEGORY_ID, ADDRESS, CONTACT));
    assertEquals(200, r.getStatus());
}
```

Expected finding:

The test proves the happy path with all fields present. It does not omit each required field individually and assert a validation error for each omission. A gate should flag that four negative parametric branches are missing.

---

## Case SC-011: Completed-State Side Effect — Downstream Record Must Not Be Created

Requirement:

> When an order reaches the completed state via path A, the system must not generate a downstream warehouse record. Records for path-A orders are handled by an external system.

Weak test:

```java
@Test
void pathAOrder_completedSuccessfully() {
    service.complete(order(PATH_A));
    assertEquals(OrderStatus.COMPLETED, order.getStatus());
}
```

Expected finding:

The test asserts the order status after completion. It does not query the downstream-records table and assert `count == 0`. The business rule about suppressing downstream record creation for path-A orders is uncovered.

---

### Approval-Workflow Cases (SC-012 to SC-013)

These cases come from a financial reporting service with a versioned approval workflow.

---

## Case SC-012: Version Lock — Previous Versions Must Become Read-Only

Requirement:

> When a new version is approved, all previous versions must become read-only and cannot be edited or resubmitted for approval.

Weak test:

```java
@Test
void newVersionApproved_statusIsActive() {
    Version v2 = service.approve(v2Draft);
    assertEquals(VersionStatus.ACTIVE, v2.getStatus());
}
```

Expected finding:

The test checks that the new version reaches active status. It does not verify that the previous version (v1) transitions to read-only, or that an edit attempt on v1 is rejected. The version-lock invariant is untested.

---

## Case SC-013: Approval-Flow Idempotency — Duplicate Submission Must Not Create a Second Flow

Requirement:

> Submitting an approval request more than once for the same record must not create multiple approval flows. Repeated calls must be idempotent.

Weak test:

```java
@Test
void submitApproval_flowCreated() {
    ApprovalFlow flow = service.submit(record);
    assertNotNull(flow.getId());
}
```

Expected finding:

The test submits once and checks that a flow was created. It never submits the same record twice and asserts that the second call returns the existing flow (not a new one). The idempotency rule is uncovered.

---

### Work-Order Approval Cases (SC-014 to SC-016)

These cases come from a work-order management service with a concurrent approval flow.

---

## Case SC-014: Concurrent Submission Idempotency — Only One Record Allowed

Requirement:

> Concurrent requests to start an approval process for the same work order must be idempotent: exactly one approval record must be created, and subsequent calls must return a conflict error.

Weak test:

```java
@Test
void submitApproval_succeeds() {
    Response r = service.submitApproval(workOrderId);
    assertEquals(200, r.getStatus());
}
```

Expected finding:

The test submits once and checks success. It does not submit the same work order ID a second time and assert a conflict response (`409`). The idempotency constraint — and the database invariant that only one record is created — is uncovered.

---

## Case SC-015: Post-Approval Button State — Mutual Exclusion Not Asserted

Requirement:

> After the approval decision, the action buttons returned to the client must be mutually exclusive: button A must be present and button B must be absent. Showing both simultaneously is a forbidden state.

Weak test:

```java
@Test
void approvalGranted_buttonAPresent() {
    WorkOrderDetail detail = service.getDetail(approvedWorkOrderId);
    assertTrue(detail.getButtons().contains(BUTTON_A));
}
```

Expected finding:

The test asserts that button A is present after approval. It does not assert that button B is absent at the same time. The mutual-exclusion invariant between the two buttons is uncovered.

---

## Case SC-016: Approval OR Logic — Either Approver Is Sufficient

Requirement:

> The approval flow uses OR logic: either approver role A or approver role B can approve independently. Approval by either one alone must trigger the approval outcome.

Weak test:

```java
@Test
void roleAApproves_outcomeTriggered() {
    service.approve(workOrderId, ROLE_A_ACTOR);
    assertEquals(ApprovalStatus.APPROVED, getApprovalStatus(workOrderId));
}
```

Expected finding:

The test proves that role A alone can approve. It does not test that role B alone can also approve without role A. A gate should flag that the OR branch from role B is untested.

---

## Language Smoke Rows

These rows keep language support honest. They are not separate claims of turnkey support; they are small checks that the same semantic miss can be expressed in different ecosystems.

| Row | Language | Minimal Fixture | Expected Finding |
| --- | --- | --- | --- |
| LS-TS-001 | TypeScript | Jest/Vitest test calls `expect(response.status).toBe(200)` after creating a duplicate rule. | Transport success does not prove the duplicate-rule rejection or required message. |
| LS-GO-001 | Go | `go test` uses `assert.NotNil(t, result)` after manager approval. | Existence of a result does not prove approval state, audit entry count, or idempotency. |
| LS-PY-001 | Python | pytest checks `assert classify_amount(600) == "finance_required"`. | The threshold rule is still missing the exact boundary value, `500`. |
