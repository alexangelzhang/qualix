"""Runtime anti-rationalization enforcement layer.

Two-layer detection:
- Layer 1: Zero-cost regex scan against known rationalization patterns
- Layer 2: Lightweight LLM confirmation (only when Layer 1 hits)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qualix.constants import (
    DEFAULT_RATIONALIZATION_CONFIRM_MODEL,
    OVERCORRECTION_PATTERNS,
    RATIONALIZATION_PATTERNS,
)
from qualix.log import get_logger

log = get_logger(__name__)

# Pre-compile patterns at module level (avoid recompilation per Guard instance)
_COMPILED_PATTERNS: list[tuple[str, re.Pattern]] = [(p, re.compile(p)) for p in RATIONALIZATION_PATTERNS]

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
    action: str = "PASS"  # PASS | BLOCK_AND_REJUDGE | HARD_BLOCK
    hard_blocked: bool = False  # 二次确认仍放水，直接拦截不进入 approve


class RationalizationGuard:
    """Two-layer detection: keyword scan + LLM confirmation."""

    def __init__(self, confirm_model: str | None = None):
        self.patterns = _COMPILED_PATTERNS
        self.confirm_model = confirm_model or DEFAULT_RATIONALIZATION_CONFIRM_MODEL

    def scan_keywords(self, judge_output: str) -> list[KeywordMatch]:
        """Layer 1: Zero-cost regex scan against known patterns."""
        matches = []
        for pattern_str, compiled in self.patterns:
            for m in compiled.finditer(judge_output):
                matches.append(
                    KeywordMatch(
                        pattern=pattern_str,
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return matches

    def confirm_with_llm(
        self,
        matches: list[KeywordMatch],
        judge_output: str,
    ) -> list[ConfirmResult]:
        """Layer 2: Batch LLM confirmation for all keyword hits in a single call."""
        from qualix.agents.llm_backends import LLMConfig, create_backend

        api_key = LLMConfig(primary=self.confirm_model)._resolve_api_key(self.confirm_model)
        backend = create_backend(self.confirm_model, api_key)

        # Batch all matches into a single prompt
        match_entries = []
        for i, match in enumerate(matches):
            ctx_start = max(0, match.start - 100)
            ctx_end = min(len(judge_output), match.end + 100)
            context = judge_output[ctx_start:ctx_end]
            match_entries.append(f"[{i + 1}] 标记文本: {match.matched_text}\n    上下文: {context}")

        batch_prompt = (
            "你是质量审计员。以下是 Judge 评审中被标记的多个段落：\n\n"
            + "\n\n".join(match_entries)
            + '\n\n对每个标记段落，判断是否在"放水"（降低标准、找借口通过、回避问题）。\n'
            "逐条回答，格式为 `[编号] CONFIRMED` 或 `[编号] FALSE_POSITIVE`，不要解释。"
        )

        try:
            content, _ = backend.chat(
                [{"role": "user", "content": batch_prompt}],
                max_tokens=200,
            )
            # Parse batch response
            results = []
            for i, match in enumerate(matches):
                tag = f"[{i + 1}]"
                if tag in content:
                    line = [ln for ln in content.split("\n") if tag in ln]
                    if line and "CONFIRMED" in line[0].upper().split("FALSE_POSITIVE")[0]:
                        results.append(ConfirmResult(verdict="CONFIRMED", text=match.matched_text))
                    else:
                        results.append(ConfirmResult(verdict="FALSE_POSITIVE", text=match.matched_text))
                else:
                    # Default to CONFIRMED if can't parse (fail-safe)
                    results.append(ConfirmResult(verdict="CONFIRMED", text=match.matched_text))
            return results
        except Exception as e:
            log.warning("Guard batch LLM confirm failed: %s, defaulting all to CONFIRMED", e)
            return [ConfirmResult(verdict="CONFIRMED", text=m.matched_text) for m in matches]

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


# ---------------------------------------------------------------------------
# Overcorrection Guard（反向检测：Judge 过严误报）
# ---------------------------------------------------------------------------

_COMPILED_OVERCORRECTION: list[tuple[str, re.Pattern]] = [(p, re.compile(p)) for p in OVERCORRECTION_PATTERNS]

OVERCORRECTION_CONFIRM_PROMPT = """你是质量审计员。以下是 Judge 评审中被标记的段落：

{matched_text}

上下文：
{surrounding_context}

判断这段话是否在"过度纠正"（把正确代码判为不合规、用风格/规范问题替代功能缺陷、无具体证据就判 FAIL）：
- 如果 Judge 有具体代码行号和功能性问题作为证据，回答 FALSE_POSITIVE
- 如果 Judge 在没有功能性问题的情况下判 FAIL，或用风格问题充当严重缺陷，回答 CONFIRMED

只回答 FALSE_POSITIVE 或 CONFIRMED，不要解释。"""

OVERCORRECTION_WARNING = """⚠️ 你上一轮的评审被检测到以下过度纠正信号：
{detected_patterns}

请注意：
- FAIL 判定必须基于功能性缺陷或需求不满足，不能仅因风格/规范问题
- 每个 FAIL 必须附带具体代码行号和功能性影响说明
- 代码逻辑正确但不符合"最佳实践"应标记为 SUGGESTION/INFO，不是 FAIL/BLOCKER"""


@dataclass
class OvercorrectionResult:
    has_overcorrection: bool
    detected_patterns: list[str] = field(default_factory=list)
    confirmed_overcorrections: list[str] = field(default_factory=list)
    fail_without_evidence: list[str] = field(default_factory=list)


class OvercorrectionGuard:
    """Detect Judge overcorrection: marking correct code as non-compliant.

    Two checks:
    1. Keyword scan for overcorrection patterns (style-over-substance)
    2. Evidence check: FAIL verdicts without file:line citations
    """

    # file:line 引用模式
    _EVIDENCE_RE = re.compile(r"[\w/\\]+\.(?:java|py|go|ts|js|kt):\d+")
    # FAIL 判定模式
    _FAIL_RE = re.compile(r"(?:FAIL|BLOCKER|MAJOR|不通过|不合格|不达标)")

    def __init__(self, confirm_model: str | None = None):
        self.patterns = _COMPILED_OVERCORRECTION
        self.confirm_model = confirm_model or DEFAULT_RATIONALIZATION_CONFIRM_MODEL

    def scan_keywords(self, judge_output: str) -> list[KeywordMatch]:
        """Layer 1: Scan for overcorrection signal patterns."""
        matches = []
        for pattern_str, compiled in self.patterns:
            for m in compiled.finditer(judge_output):
                matches.append(
                    KeywordMatch(
                        pattern=pattern_str,
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return matches

    def check_evidence_on_fails(self, judge_output: str) -> list[str]:
        """Check that FAIL verdicts have file:line evidence.

        Splits output into paragraphs, finds those containing FAIL/BLOCKER,
        and checks each has at least one file:line citation.
        """
        missing: list[str] = []
        paragraphs = judge_output.split("\n\n")
        for para in paragraphs:
            if not self._FAIL_RE.search(para):
                continue
            if not self._EVIDENCE_RE.search(para):
                # FAIL without evidence — potential overcorrection
                snippet = para.strip()[:120]
                missing.append(snippet)
        return missing

    def check(self, judge_output: str) -> OvercorrectionResult:
        """Full overcorrection check pipeline."""
        keyword_matches = self.scan_keywords(judge_output)
        fail_no_evidence = self.check_evidence_on_fails(judge_output)

        if not keyword_matches and not fail_no_evidence:
            return OvercorrectionResult(has_overcorrection=False)

        confirmed: list[str] = []

        # Keyword matches get logged but not LLM-confirmed (keep it zero-cost)
        if keyword_matches:
            log.info(
                "Overcorrection Guard: %d keyword matches found",
                len(keyword_matches),
            )
            confirmed.extend(m.matched_text for m in keyword_matches)

        if fail_no_evidence:
            log.warning(
                "Overcorrection Guard: %d FAIL verdicts without file:line evidence",
                len(fail_no_evidence),
            )

        return OvercorrectionResult(
            has_overcorrection=bool(confirmed) or bool(fail_no_evidence),
            detected_patterns=[m.pattern for m in keyword_matches],
            confirmed_overcorrections=confirmed,
            fail_without_evidence=fail_no_evidence,
        )


def format_overcorrection_warning(result: OvercorrectionResult) -> str:
    """Format warning text for overcorrection re-judge prompt injection."""
    parts = []
    if result.confirmed_overcorrections:
        parts.extend(f"- 过度纠正: {t}" for t in result.confirmed_overcorrections)
    if result.fail_without_evidence:
        parts.extend(f"- FAIL 缺少证据行号: {s}" for s in result.fail_without_evidence[:5])
    return OVERCORRECTION_WARNING.format(detected_patterns="\n".join(parts))
