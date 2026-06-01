import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from expense_policy import ExpenseRequest, approve_by_manager


def test_small_request_can_be_manager_approved() -> None:
    request = ExpenseRequest(
        request_id="REQ-1",
        requester_id="employee-1",
        amount_usd=Decimal("120"),
    )

    approved = approve_by_manager(request, actor_id="manager-1")

    assert approved.status == "PAID_READY"
    assert len(approved.audit_log) == 1


def test_large_request_waits_for_finance() -> None:
    request = ExpenseRequest(
        request_id="REQ-2",
        requester_id="employee-1",
        amount_usd=Decimal("600"),
    )

    approved = approve_by_manager(request, actor_id="manager-1")

    assert approved.status == "MANAGER_APPROVED"
