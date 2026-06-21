"""Structured evidence citation contracts.

Evidence citations are intentionally *not* verdicts.  They identify small,
line-bounded snippets that a downstream phase or judge may inspect.  Q06 still
owns the semantic audit decision.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvidenceKind(StrEnum):
    """Type of artifact a citation points at."""

    PRD = "prd"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    TEST = "test"
    COVERAGE = "coverage"
    REPORT = "report"
    RECEIPT = "receipt"
    UNKNOWN = "unknown"


class EvidenceConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceCitation(BaseModel):
    """A line-bounded evidence candidate for one EUT.

    The ``eut_id`` field is required by design: Q05a/Q05b/Q06 evidence must
    remain EUT-per-item and must never regress to SE-level aggregation.
    """

    path: str = Field(min_length=1, description="File path, preferably relative to repo.")
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    kind: EvidenceKind = EvidenceKind.UNKNOWN
    phase: str = Field(default="", description="Phase that requested or consumed this citation, e.g. Q06.")
    se_id: str = Field(default="", description="Optional related SE ID.")
    eut_id: str = Field(pattern=r"^EUT-\d+$", description="Required EUT ID; citation is never SE-aggregated.")
    repo: str = Field(default="", description="Repository root used to produce this citation.")
    locator: str = Field(default="ripgrep", min_length=1, description="Locator/provider name.")
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM
    reason: str = Field(default="", description="Short explanation of why this range is relevant.")
    matched_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def line_end_gte_line_start(self) -> EvidenceCitation:
        if self.line_end is not None and self.line_end < self.line_start:
            raise ValueError(f"line_end ({self.line_end}) must be >= line_start ({self.line_start})")
        return self

    def reference(self) -> str:
        """Return a compact ``path:start-end`` reference."""
        if self.line_end is None or self.line_end == self.line_start:
            return f"{self.path}:{self.line_start}"
        return f"{self.path}:{self.line_start}-{self.line_end}"
