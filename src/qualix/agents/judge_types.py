"""Shared dataclasses for multi-judge voting and adaptive loop iteration state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeVote:
    model: str
    scores: dict[str, int]
    overall: float
    verdict: str  # PASS / PASS_WITH_CONCERNS / FAIL
    issues: list[dict[str, Any]]
    duration: float = 0
    raw_output: str = ""
    health: str = "HEALTHY"  # HEALTHY | INFRA_FAILURE | GUARD_EXHAUSTED
    token_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class VoteResult:
    votes: list[JudgeVote]
    consensus: str  # PASS / PASS_WITH_CONCERNS / FAIL
    avg_score: float
    disagreements: list[str]


@dataclass
class IterationRecord:
    iteration: int
    worker_result: Any | None = None
    judge_result: VoteResult | None = None
    critique_result: Any | None = None
    fix_applied: bool = False
    duration: float = 0
    #: Pydantic / finalize 同源校验（validate_phase_output），供 Judge rubric 与下轮 handoff 消费（T14）
    schema_errors: list[str] = field(default_factory=list)
