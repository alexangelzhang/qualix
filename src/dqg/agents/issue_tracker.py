"""Track Judge/Critique issues across adaptive loop iterations.

Assigns stable IDs to issues and tracks their lifecycle:
discovered_in → resolved_in (or still open).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


@dataclass
class TrackedIssue:
    issue_id: str
    severity: str
    description: str
    suggestion: str
    source: str  # "judge" or "critique"
    discovered_in: int  # iteration number
    resolved_in: int | None = None  # iteration where it disappeared


SIMILARITY_THRESHOLD = 0.6


def _similarity(a: str, b: str) -> float:
    """Quick string similarity ratio."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class IssueTracker:
    """Accumulates issues across iterations, matches by description similarity."""

    def __init__(self) -> None:
        self._issues: list[TrackedIssue] = []
        self._next_judge_seq = 0
        self._next_critique_seq = 0

    def record_iteration(
        self,
        iteration: int,
        judge_issues: list[dict[str, Any]],
        critique_issues: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record issues from one iteration, updating lifecycle tracking."""
        current_descriptions: list[str] = []

        # Process judge issues
        for issue in judge_issues:
            severity = issue.get("severity", "medium")
            if severity in ("info", "suggestion"):
                continue
            desc = issue.get("description", "")
            current_descriptions.append(desc)
            if not self._find_and_update(desc, iteration):
                self._next_judge_seq += 1
                self._issues.append(
                    TrackedIssue(
                        issue_id=f"J-{iteration:02d}-{self._next_judge_seq:03d}",
                        severity=severity,
                        description=desc,
                        suggestion=issue.get("suggestion", ""),
                        source="judge",
                        discovered_in=iteration,
                    )
                )

        # Process critique issues
        for issue in critique_issues or []:
            desc = issue.get("description", "")
            current_descriptions.append(desc)
            cid = issue.get("id", "")
            if not self._find_and_update(desc, iteration):
                if not cid:
                    self._next_critique_seq += 1
                    cid = f"C-{iteration:02d}-{self._next_critique_seq:03d}"
                self._issues.append(
                    TrackedIssue(
                        issue_id=cid,
                        severity=issue.get("severity", "medium"),
                        description=desc,
                        suggestion=issue.get("suggestion", ""),
                        source="critique",
                        discovered_in=iteration,
                    )
                )

        # Mark issues not seen in this iteration as resolved
        for tracked in self._issues:
            if tracked.resolved_in is not None:
                continue
            if tracked.discovered_in == iteration:
                continue
            still_present = any(
                _similarity(tracked.description, d) >= SIMILARITY_THRESHOLD for d in current_descriptions
            )
            if not still_present:
                tracked.resolved_in = iteration

    def _find_and_update(self, description: str, iteration: int) -> bool:
        """Check if description matches an existing open issue."""
        for tracked in self._issues:
            if tracked.resolved_in is not None:
                continue
            if _similarity(tracked.description, description) >= SIMILARITY_THRESHOLD:
                return True
        return False

    def get_summary(self) -> list[dict[str, Any]]:
        """Return serializable summary of all tracked issues."""
        return [
            {
                "issue_id": t.issue_id,
                "severity": t.severity,
                "description": t.description[:200],
                "source": t.source,
                "discovered_in": t.discovered_in,
                "resolved_in": t.resolved_in,
                "status": "resolved" if t.resolved_in else "open",
            }
            for t in self._issues
        ]

    @property
    def total(self) -> int:
        return len(self._issues)

    @property
    def resolved_count(self) -> int:
        return sum(1 for t in self._issues if t.resolved_in is not None)

    @property
    def open_count(self) -> int:
        return self.total - self.resolved_count
