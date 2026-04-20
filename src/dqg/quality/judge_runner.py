"""Unified Judge execution with canonical output schema.

Serves manual, adaptive, and holdout execution modes.
All modes produce the same canonical schema for downstream consumers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Final

from dqg.agents.llm_backends import (
    LLMConfig, StructuredChatResult, create_backend,
)
from dqg.log import get_logger

log = get_logger(__name__)

JUDGE_RESPONSE_SCHEMA: Final[dict[str, Any]] = {
    "verdict": "PASS | FAIL | PASS_WITH_CONCERNS",
    "overall": "1-5 float",
    "scores": {"dimension_id": "score (int 1-5)"},
    "issues": [{"severity": "high|medium|low", "description": "string"}],
}


@dataclass
class JudgeResult:
    """Canonical Judge output — wire-compatible with existing _judge_result.json."""
    overall_score: float
    verdict: str
    dimensions: list[dict[str, Any]]  # [{id, name, score, weight, rationale, issues}]
    issues: list[dict[str, Any]]
    raw_output: str
    health: str = "HEALTHY"  # HEALTHY | INFRA_FAILURE | GUARD_EXHAUSTED
    model: str = ""
    duration: float = 0
    _schema_version: int = 1


class JudgeRunner:
    """Unified Judge execution with primary→fallback model chain."""

    @staticmethod
    def normalize(raw: dict[str, Any], raw_output: str = "") -> JudgeResult:
        """Normalize any Judge output variant to canonical schema.

        Handles:
        - overall vs overall_score
        - scores dict → dimensions list conversion
        - Empty/invalid → INFRA_FAILURE
        Wire-compatible: existing consumers can read without changes.
        """
        if not raw or (not raw.get("overall") and not raw.get("overall_score")):
            return JudgeResult(
                overall_score=0, verdict="FAIL", dimensions=[], issues=[],
                raw_output=raw_output, health="INFRA_FAILURE",
            )

        overall = raw.get("overall_score") or raw.get("overall", 0)

        # Normalize dimensions: if scores dict, convert to list
        dimensions = raw.get("dimensions", [])
        if not dimensions and isinstance(raw.get("scores"), dict):
            dimensions = [
                {"id": k, "name": k, "score": v, "weight": 0, "issues": []}
                for k, v in raw["scores"].items()
            ]

        all_issues = list(raw.get("issues", []))

        return JudgeResult(
            overall_score=float(overall),
            verdict=raw.get("verdict", "FAIL"),
            dimensions=dimensions,
            issues=all_issues,
            raw_output=raw_output,
            health="HEALTHY",
        )

    def run(
        self,
        phase: str,
        report_path: str,
        output_dir: str,
        model: str,
        fallback: str | None = None,
        *,
        rubric: str = "",
        warning_override: str | None = None,
    ) -> JudgeResult:
        """Execute Judge with primary→fallback and structured output.

        Fallback semantics:
        - Try primary model via chat_structured()
        - If primary INFRA_FAILURE and fallback provided: retry with fallback
        - Both fail → result.health = INFRA_FAILURE
        """
        from pathlib import Path

        start = time.time()
        report_content = ""
        rp = Path(report_path)
        if rp.exists():
            report_content = rp.read_text(encoding="utf-8", errors="ignore")
            if len(report_content) > 15000:
                report_content = report_content[:15000] + "\n...(truncated)"

        rubric_text = rubric
        if warning_override:
            rubric_text += f"\n\n{warning_override}"

        messages = [
            {"role": "user", "content": f"## Evaluation Rubric\n{rubric_text}", "cache_control": True},
            {"role": "user", "content": f"## Report\n{report_content}"},
        ]

        result = self._call_judge(messages, model, start)
        if result.health == "INFRA_FAILURE" and fallback:
            log.warning("Judge primary %s failed, trying fallback %s", model, fallback)
            result = self._call_judge(messages, fallback, start)
            if result.health == "INFRA_FAILURE":
                log.error("Judge fallback %s also failed", fallback)

        result.duration = time.time() - start
        return result

    def _call_judge(self, messages: list[dict], model: str, start: float) -> JudgeResult:
        """Single model call with structured output."""
        try:
            api_key = LLMConfig(primary=model)._resolve_api_key(model)
            backend = create_backend(model, api_key)
            structured = backend.chat_structured(
                messages, JUDGE_RESPONSE_SCHEMA, max_tokens=2000,
            )
            result = self.normalize(structured.parsed, raw_output=structured.raw_text)
            result.model = model
            log.info("JudgeRunner %s: verdict=%s, overall=%.1f", model, result.verdict, result.overall_score)
            return result
        except Exception as e:
            log.error("JudgeRunner %s failed: %s", model, e)
            return JudgeResult(
                overall_score=0, verdict="FAIL", dimensions=[], issues=[],
                raw_output=str(e), health="INFRA_FAILURE", model=model,
            )
