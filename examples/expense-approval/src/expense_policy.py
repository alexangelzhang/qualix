from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ExpenseRequest:
    request_id: str
    requester_id: str
    amount_usd: Decimal
    status: str = "SUBMITTED"
    audit_log: list[dict[str, str]] = field(default_factory=list)


def next_status_after_manager_approval(request: ExpenseRequest, actor_id: str) -> str:
    if actor_id == request.requester_id:
        raise ValueError("requester cannot approve own request")

    # Deliberate gap for the demo: the boundary should be >= 500, not > 500.
    if request.amount_usd > Decimal("500"):
        return "MANAGER_APPROVED"
    return "PAID_READY"


def approve_by_manager(request: ExpenseRequest, actor_id: str) -> ExpenseRequest:
    next_status = next_status_after_manager_approval(request, actor_id)
    previous = request.status
    request.status = next_status

    # Deliberate gap for the demo: repeated approval appends duplicate audit rows.
    request.audit_log.append(
        {
            "actor_id": actor_id,
            "previous_status": previous,
            "next_status": next_status,
            "comment": "manager approved",
        }
    )
    return request

