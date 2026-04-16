"""Runtime anti-rationalization enforcement layer.

Two-layer detection:
- Layer 1: Zero-cost regex scan against known rationalization patterns
- Layer 2: Lightweight LLM confirmation (only when Layer 1 hits)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dqg.constants import (
    RATIONALIZATION_PATTERNS,
    DEFAULT_RATIONALIZATION_CONFIRM_MODEL,
)
from dqg.log import get_logger

log = get_logger(__name__)

RATIONALIZATION_CONFIRM_PROMPT = """你是质量审计员。以下是 Judge 评审中被标记的段落：

{matched_text}

上下文：
{surrounding_context}

判断这段话是否在"放水"（降低标准、找借口通过、回避问题）：
- 如果是合理的上下文描述或客观陈述，回答 FALSE_POSITIVE
- 如果是在降低标准或找借口，回答 CONFIRMED

只回答 FALSE_POSITIVE 或 CONFIRMED，不要解释。"""

REJUDGE_WARNING = """⚠️ 你上一轮的评审被检测到以下放水信号：
{detected_patterns}

请严格按照评审标准重新评估，不要降低标准。
宁可多报不可漏报（FN 比 FP 更严重）。"""


@dataclass
class KeywordMatch:
    pattern: str
    matched_text: str
    start: int
    end: int


@dataclass
class ConfirmResult:
    verdict: str  # CONFIRMED | FALSE_POSITIVE
    text: str


@dataclass
class GuardResult:
    passed: bool
    detected_patterns: list[str] = field(default_factory=list)
    confirmed_rationalizations: list[str] = field(default_factory=list)
    action: str = "PASS"  # PASS | BLOCK_AND_REJUDGE


class RationalizationGuard:
    """Two-layer detection: keyword scan + LLM confirmation."""

    def __init__(self, confirm_model: str | None = None):
        self.patterns = [(p, re.compile(p)) for p in RATIONALIZATION_PATTERNS]
        self.confirm_model = confirm_model or DEFAULT_RATIONALIZATION_CONFIRM_MODEL

    def scan_keywords(self, judge_output: str) -> list[KeywordMatch]:
        """Layer 1: Zero-cost regex scan against known patterns."""
        matches = []
        for pattern_str, compiled in self.patterns:
            for m in compiled.finditer(judge_output):
                matches.append(KeywordMatch(
                    pattern=pattern_str,
                    matched_text=m.group(),
                    start=m.start(),
                    end=m.end(),
                ))
        return matches

    def confirm_with_llm(
        self, matches: list[KeywordMatch], judge_output: str,
    ) -> list[ConfirmResult]:
        """Layer 2: Lightweight LLM confirmation for keyword hits."""
        import os
        from dqg.agents.llm_backends import create_backend

        results = []
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        backend = create_backend(self.confirm_model, api_key)

        for match in matches:
            ctx_start = max(0, match.start - 100)
            ctx_end = min(len(judge_output), match.end + 100)
            context = judge_output[ctx_start:ctx_end]

            prompt = RATIONALIZATION_CONFIRM_PROMPT.format(
                matched_text=match.matched_text,
                surrounding_context=context,
            )
            try:
                content, _ = backend.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=50,
                )
                verdict = "CONFIRMED" if "CONFIRMED" in content.upper() else "FALSE_POSITIVE"
                results.append(ConfirmResult(verdict=verdict, text=match.matched_text))
            except Exception as e:
                log.warning("Guard LLM confirm failed: %s, defaulting to CONFIRMED", e)
                results.append(ConfirmResult(verdict="CONFIRMED", text=match.matched_text))

        return results

    def check(self, judge_output: str) -> GuardResult:
        """Full two-layer check pipeline."""
        matches = self.scan_keywords(judge_output)
        if not matches:
            return GuardResult(passed=True, action="PASS")

        log.info("Guard Layer 1: %d keyword matches found", len(matches))
        confirmations = self.confirm_with_llm(matches, judge_output)
        confirmed = [c for c in confirmations if c.verdict == "CONFIRMED"]

        if not confirmed:
            return GuardResult(
                passed=True,
                detected_patterns=[m.pattern for m in matches],
                action="PASS",
            )

        log.warning("Guard Layer 2: %d rationalizations confirmed", len(confirmed))
        return GuardResult(
            passed=False,
            detected_patterns=[m.pattern for m in matches],
            confirmed_rationalizations=[c.text for c in confirmed],
            action="BLOCK_AND_REJUDGE",
        )


def format_rejudge_warning(guard_result: GuardResult) -> str:
    """Format warning text for re-judge prompt injection."""
    patterns = "\n".join(f"- {p}" for p in guard_result.confirmed_rationalizations)
    return REJUDGE_WARNING.format(detected_patterns=patterns)
