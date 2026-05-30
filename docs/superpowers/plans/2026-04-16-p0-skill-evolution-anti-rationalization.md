# P0: Skill Evolution + Anti-Rationalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two P0 features: (1) Skill Evolution auto-closed loop triggered by adaptive loop exhaustion, (2) Anti-Rationalization runtime enforcement via two-layer keyword+LLM guard on Judge output.

**Architecture:** Foundation-first approach — build `StructuredChatResult` + `chat_structured()` in backend layer, then `JudgeRunner` as unified Judge executor, then `RationalizationGuard` and `SkillReflector` on top. Adaptive loop is the integration point where both features converge.

**Tech Stack:** Python 3.11+, existing DQG framework (`dqg.agents`, `dqg.quality`, `dqg.tracking`), Anthropic/OpenAI SDKs for structured output.

**Spec:** `docs/superpowers/specs/2026-04-15-p0-skill-evolution-anti-rationalization-design.md`

---

### Task 1: Foundation — Constants + StructuredChatResult + chat_structured()

**Files:**
- Modify: `src/dqg/constants.py`
- Modify: `src/dqg/agents/llm_backends.py`
- Test: `tests/test_llm_backends_structured.py`

- [ ] **Step 1: Add anti-rationalization constants to `constants.py`**

Append after the `PERF_OUTPUT_TOKEN_WARNING` block (around line 155):

```python
# ---------------------------------------------------------------------------
# Anti-Rationalization Runtime Enforcement
# ---------------------------------------------------------------------------

RATIONALIZATION_PATTERNS: list[str] = [
    r"虽然.{0,20}但.{0,20}(可以接受|尚可|足够)",
    r"(基本|整体|总体).{0,10}(清晰|达标|合格|可接受)",
    r"考虑到.{0,15}(时间|复杂度|限制)",
    r"影响不大",
    r"已经(有了?|存在).{0,10}(改进|提升)",
    r"覆盖率.{0,5}达标",
    r"(不需要|没必要).{0,10}(边界|并发|异常)",
    r"上一轮已经",
]

DEFAULT_RATIONALIZATION_CONFIRM_MODEL = "claude-haiku-4-5-20251001"
RATIONALIZATION_MAX_REJUDGE = 1  # guard 层最多因放水重审 1 次

# Holdout replay
HOLDOUT_DIR = "regression/holdout"
HOLDOUT_SUITE_BASELINE_FILE = "suite_baseline.json"
HOLDOUT_SUITE_REGRESSION_THRESHOLD = 0.95   # suite score < baseline * 0.95 = regression
HOLDOUT_CASE_REGRESSION_THRESHOLD = 0.90    # single case < baseline * 0.90 = regression
```

- [ ] **Step 2: Add `StructuredChatResult` dataclass to `llm_backends.py`**

Add after the `LLMConfig` class (line 58):

```python
@dataclass
class StructuredChatResult:
    """Return type for chat_structured — preserves raw text for guard/audit."""
    parsed: dict[str, Any]
    raw_text: str
    provider_meta: dict[str, Any]
```

- [ ] **Step 3: Add `chat_structured()` to `LLMBackend` ABC**

Add to the `LLMBackend` class after the `chat()` method:

```python
def chat_structured(
    self, messages: list[dict[str, Any]], response_schema: dict[str, Any], **kwargs,
) -> StructuredChatResult:
    """Structured output with schema enforcement. Default: prompt-based fallback."""
    import re as _re
    prompt_suffix = (
        "\n\nIMPORTANT: Output ONLY a valid JSON object matching this schema, nothing else:\n"
        + json.dumps(response_schema, indent=2, ensure_ascii=False)
    )
    augmented = list(messages)
    if augmented:
        last = augmented[-1].copy()
        last["content"] = last["content"] + prompt_suffix
        augmented[-1] = last

    raw_text, usage = self.chat(augmented, **kwargs)

    # Parse JSON from response
    parsed = _extract_json(raw_text)
    if parsed is None:
        # Retry once with explicit JSON-only instruction
        retry_msgs = augmented + [
            {"role": "assistant", "content": raw_text},
            {"role": "user", "content": "你的回复不是有效 JSON。请只输出 JSON 对象，不要包含任何其他文本。"},
        ]
        raw_text_2, usage_2 = self.chat(retry_msgs, **kwargs)
        parsed = _extract_json(raw_text_2)
        if parsed is not None:
            raw_text = raw_text_2
            usage = usage_2

    return StructuredChatResult(
        parsed=parsed or {},
        raw_text=raw_text,
        provider_meta={"usage": usage},
    )
```

- [ ] **Step 4: Add `chat_structured()` override to `OpenAICompatibleBackend` with JSON mode**

```python
def chat_structured(
    self, messages: list[dict[str, Any]], response_schema: dict[str, Any], **kwargs,
) -> StructuredChatResult:
    """OpenAI-compatible: use response_format=json_object when available."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("pip install openai")

    client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
    clean_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    # Inject schema into last message
    schema_hint = (
        "\n\nOutput ONLY a valid JSON object matching this schema:\n"
        + json.dumps(response_schema, indent=2, ensure_ascii=False)
    )
    clean_msgs[-1]["content"] += schema_hint

    try:
        response = client.chat.completions.create(
            model=self.model,
            messages=clean_msgs,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", 0.0),
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        parsed = _extract_json(raw_text)
        return StructuredChatResult(
            parsed=parsed or {},
            raw_text=raw_text,
            provider_meta={"usage": usage},
        )
    except Exception:
        # Fallback to base implementation (prompt-based)
        return super().chat_structured(messages, response_schema, **kwargs)
```

- [ ] **Step 5: Add `_extract_json()` helper at module level**

Add before the backend classes:

```python
def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text. Returns None if no valid JSON found."""
    import re as _re
    # Try ```json code block first
    m = _re.search(r"```json\s*\n([\s\S]*?)\n```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: first { to last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None
```

- [ ] **Step 6: Write test for `chat_structured()`**

```python
# tests/test_llm_backends_structured.py
"""Tests for StructuredChatResult and chat_structured()."""
import json
import pytest
from unittest.mock import patch, MagicMock
from dqg.agents.llm_backends import (
    StructuredChatResult, OpenAICompatibleBackend, _extract_json,
)


def test_extract_json_from_code_block():
    text = '```json\n{"verdict": "PASS", "overall": 4.0}\n```'
    result = _extract_json(text)
    assert result == {"verdict": "PASS", "overall": 4.0}


def test_extract_json_from_raw():
    text = 'Here is the result: {"verdict": "FAIL", "overall": 2.0} done.'
    result = _extract_json(text)
    assert result == {"verdict": "FAIL", "overall": 2.0}


def test_extract_json_returns_none_on_invalid():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


def test_structured_chat_result_fields():
    r = StructuredChatResult(parsed={"a": 1}, raw_text="raw", provider_meta={"usage": {}})
    assert r.parsed == {"a": 1}
    assert r.raw_text == "raw"
```

- [ ] **Step 7: Run tests**

Run: `cd /path/to/rd-gate && python -m pytest tests/test_llm_backends_structured.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/dqg/constants.py src/dqg/agents/llm_backends.py tests/test_llm_backends_structured.py
git commit -m "feat: add StructuredChatResult + chat_structured() + anti-rationalization constants"
```

---

### Task 2: JudgeRunner — Unified Judge Execution

**Files:**
- Create: `src/dqg/quality/judge_runner.py`
- Test: `tests/test_judge_runner.py`

- [ ] **Step 1: Write failing test for JudgeRunner.normalize()**

```python
# tests/test_judge_runner.py
"""Tests for JudgeRunner canonical schema normalization."""
import pytest
from dqg.quality.judge_runner import JudgeRunner, JudgeResult


def test_normalize_adaptive_format():
    """Adaptive output uses 'overall' not 'overall_score', and scores dict."""
    raw = {
        "overall": 3.5,
        "verdict": "PASS_WITH_CONCERNS",
        "scores": {"faithfulness": 4, "completeness": 3},
        "issues": [{"severity": "medium", "description": "missing edge case"}],
    }
    result = JudgeRunner.normalize(raw, raw_output="raw text here")
    assert result.overall_score == 3.5
    assert result.verdict == "PASS_WITH_CONCERNS"
    assert isinstance(result.dimensions, list)
    assert result.dimensions[0]["id"] == "faithfulness"
    assert result.raw_output == "raw text here"
    assert result.health == "HEALTHY"


def test_normalize_manual_format():
    """Manual judge output uses 'overall_score' and dimensions list."""
    raw = {
        "overall_score": 4.0,
        "verdict": "PASS",
        "dimensions": [
            {"id": "faithfulness", "name": "忠实度", "score": 4, "weight": 0.25, "issues": []},
        ],
        "issues": [],
    }
    result = JudgeRunner.normalize(raw, raw_output="raw")
    assert result.overall_score == 4.0
    assert result.dimensions[0]["id"] == "faithfulness"


def test_normalize_empty_returns_infra_failure():
    """Empty parsed dict → INFRA_FAILURE."""
    result = JudgeRunner.normalize({}, raw_output="garbage")
    assert result.health == "INFRA_FAILURE"
    assert result.overall_score == 0
    assert result.verdict == "FAIL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_judge_runner.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Implement JudgeRunner**

```python
# src/dqg/quality/judge_runner.py
"""Unified Judge execution with canonical output schema.

Serves manual, adaptive, and holdout execution modes.
All modes produce the same canonical schema for downstream consumers.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from dqg.agents.llm_backends import (
    LLMConfig, StructuredChatResult, create_backend, _extract_json,
)
from dqg.log import get_logger

log = get_logger(__name__)

JUDGE_RESPONSE_SCHEMA = {
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

        # Aggregate issues from dimensions + top-level
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

        # Try primary
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
            api_key = self._resolve_api_key(model)
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

    @staticmethod
    def _resolve_api_key(model: str) -> str:
        """Resolve API key from environment based on model name."""
        if any(p in model.lower() for p in ("claude", "opus", "sonnet", "haiku")):
            return os.environ.get("ANTHROPIC_API_KEY", "")
        if "deepseek" in model.lower():
            return os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        return os.environ.get("OPENAI_API_KEY", "")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_judge_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/quality/judge_runner.py tests/test_judge_runner.py
git commit -m "feat: add JudgeRunner with canonical schema + primary/fallback chain"
```

---

### Task 3: RationalizationGuard — Two-Layer Detection

**Files:**
- Create: `src/dqg/quality/rationalization_guard.py`
- Test: `tests/test_rationalization_guard.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_rationalization_guard.py
"""Tests for RationalizationGuard two-layer detection."""
import pytest
from unittest.mock import patch, MagicMock
from dqg.quality.rationalization_guard import RationalizationGuard, GuardResult


def test_scan_keywords_no_match():
    guard = RationalizationGuard()
    matches = guard.scan_keywords("所有维度均已严格评审，发现 3 个问题。")
    assert len(matches) == 0


def test_scan_keywords_match_basic():
    guard = RationalizationGuard()
    matches = guard.scan_keywords("虽然缺少边界测试，但整体可以接受。")
    assert len(matches) >= 1
    assert any("虽然" in m.matched_text for m in matches)


def test_scan_keywords_match_multiple():
    guard = RationalizationGuard()
    text = "基本清晰，覆盖率达标，影响不大。"
    matches = guard.scan_keywords(text)
    assert len(matches) >= 2


def test_check_passes_when_no_keywords():
    guard = RationalizationGuard()
    result = guard.check("严格评审结果：FAIL，发现 5 个严重问题。")
    assert result.passed is True
    assert result.action == "PASS"


def test_check_blocks_when_confirmed(monkeypatch):
    guard = RationalizationGuard()
    # Mock LLM confirmation to return CONFIRMED
    monkeypatch.setattr(guard, "confirm_with_llm", lambda matches, text: [
        MagicMock(verdict="CONFIRMED", text="虽然缺少边界测试，但整体可以接受")
    ])
    result = guard.check("虽然缺少边界测试，但整体可以接受。")
    assert result.passed is False
    assert result.action == "BLOCK_AND_REJUDGE"


def test_check_passes_on_false_positive(monkeypatch):
    guard = RationalizationGuard()
    monkeypatch.setattr(guard, "confirm_with_llm", lambda matches, text: [
        MagicMock(verdict="FALSE_POSITIVE", text="")
    ])
    result = guard.check("虽然这个接口名称不太直观，但功能实现正确。")
    assert result.passed is True
    assert result.action == "PASS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rationalization_guard.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement RationalizationGuard**

```python
# src/dqg/quality/rationalization_guard.py
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
            # Extract surrounding context (100 chars each side)
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_rationalization_guard.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/quality/rationalization_guard.py tests/test_rationalization_guard.py
git commit -m "feat: add RationalizationGuard with two-layer keyword+LLM detection"
```

---

### Task 4: Adaptive Loop Integration — JudgeRunner + Guard + Health Gate

**Files:**
- Modify: `src/dqg/agents/adaptive_loop.py`
- Test: `tests/test_adaptive_loop_guard.py`

- [ ] **Step 1: Write failing tests for guard integration**

```python
# tests/test_adaptive_loop_guard.py
"""Tests for adaptive loop guard + JudgeRunner integration."""
import pytest
from unittest.mock import patch, MagicMock
from dqg.agents.adaptive_loop import (
    JudgeVote, _run_single_judge, _parse_judge_output,
)


def test_judge_vote_has_raw_output_and_health():
    """JudgeVote must have raw_output and health fields after integration."""
    vote = JudgeVote(
        model="test", scores={}, overall=3.5, verdict="PASS",
        issues=[], duration=1.0, raw_output="raw text", health="HEALTHY",
    )
    assert vote.raw_output == "raw text"
    assert vote.health == "HEALTHY"


def test_judge_vote_health_defaults_to_healthy():
    vote = JudgeVote(
        model="test", scores={}, overall=3.5, verdict="PASS",
        issues=[], duration=1.0,
    )
    assert vote.health == "HEALTHY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_adaptive_loop_guard.py -v`
Expected: FAIL (JudgeVote missing raw_output/health fields)

- [ ] **Step 3: Update `JudgeVote` dataclass**

In `src/dqg/agents/adaptive_loop.py`, modify the `JudgeVote` dataclass (line 40-46):

```python
@dataclass
class JudgeVote:
    model: str
    scores: dict[str, int]
    overall: float
    verdict: str  # PASS / PASS_WITH_CONCERNS / FAIL
    issues: list[dict[str, Any]]
    duration: float = 0
    raw_output: str = ""       # preserved for guard layer
    health: str = "HEALTHY"    # HEALTHY | INFRA_FAILURE | GUARD_EXHAUSTED
```

- [ ] **Step 4: Rewrite `_run_single_judge()` as JudgeRunner thin wrapper**

Replace the existing `_run_single_judge()` function (lines 57-133) with:

```python
def _run_single_judge(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    model: str,
    fallback: str,
    warning_override: str | None = None,
) -> JudgeVote | None:
    """Thin wrapper: delegates to JudgeRunner, handles round orchestration."""
    from dqg.quality.judge_runner import JudgeRunner

    runner = JudgeRunner()
    result = runner.run(
        phase="",  # phase not needed for rubric-based judge
        report_path=str(report_path),
        output_dir=str(output_dir),
        model=model,
        fallback=fallback,
        rubric=rubric,
        warning_override=warning_override,
    )

    if result.health == "INFRA_FAILURE":
        log.warning("JudgeRunner returned INFRA_FAILURE for model=%s", model)
        return None

    return JudgeVote(
        model=result.model,
        scores={d["id"]: d.get("score", 0) for d in result.dimensions},
        overall=result.overall_score,
        verdict=result.verdict,
        issues=result.issues,
        duration=result.duration,
        raw_output=result.raw_output,
        health=result.health,
    )
```

- [ ] **Step 5: Add guard integration to `multi_judge_vote()`**

In `multi_judge_vote()` (around line 159), after the primary vote is obtained and before the boundary check, insert guard logic:

```python
    # --- Guard: Anti-Rationalization check on primary vote ---
    if primary_vote is not None and primary_vote.raw_output:
        from dqg.quality.rationalization_guard import RationalizationGuard, format_rejudge_warning
        from dqg.constants import RATIONALIZATION_MAX_REJUDGE

        guard = RationalizationGuard()
        guard_result = guard.check(primary_vote.raw_output)

        if not guard_result.passed:
            log.warning("Guard detected rationalization in primary judge, re-judging")
            warning_text = format_rejudge_warning(guard_result)
            primary_vote = _run_single_judge(
                output_dir, report_path, rubric, primary_model, fallback,
                warning_override=warning_text,
            )
            if primary_vote is not None:
                # Check re-judged output again
                guard_result_2 = guard.check(primary_vote.raw_output)
                if not guard_result_2.passed:
                    log.warning("Guard budget exhausted, marking as GUARD_EXHAUSTED")
                    primary_vote.health = "GUARD_EXHAUSTED"
                    primary_vote.verdict = "INVALID"

        # If guard exhausted, exclude from valid votes
        if primary_vote is not None and primary_vote.health == "GUARD_EXHAUSTED":
            log.warning("Primary vote GUARD_EXHAUSTED, excluding from consensus")
            primary_vote = None  # triggers fallback to secondary models
```

- [ ] **Step 6: Add judge_health_check helper**

Add after `_compute_consensus()`:

```python
def judge_health_check(judge_results: list[VoteResult]) -> str:
    """Check if judge results contain enough valid votes.

    Returns:
        'HEALTHY' if >= 2 valid votes across all iterations
        'SEMANTIC_FAIL' if valid votes exist but all FAIL
        'INFRA_FAILURE' if insufficient valid votes
    """
    valid_votes = 0
    for vr in judge_results:
        for v in vr.votes:
            if v.health == "HEALTHY":
                valid_votes += 1
    if valid_votes < 2:
        return "INFRA_FAILURE"
    if all(vr.consensus == "FAIL" for vr in judge_results):
        return "SEMANTIC_FAIL"
    return "HEALTHY"
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_adaptive_loop_guard.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/dqg/agents/adaptive_loop.py tests/test_adaptive_loop_guard.py
git commit -m "feat: integrate JudgeRunner + RationalizationGuard into adaptive loop"
```

---

### Task 5: resolve_worker_prompt() — Unified Skill Resolution

**Files:**
- Modify: `src/dqg/context/skill_loader.py`
- Modify: `src/dqg/commands/agents.py`
- Modify: `src/dqg/agents/dag_scheduler.py`
- Test: `tests/test_skill_loader_resolve.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_skill_loader_resolve.py
"""Tests for resolve_worker_prompt unified skill resolution."""
import pytest
from pathlib import Path
from unittest.mock import patch
from dqg.context.skill_loader import resolve_worker_prompt


def test_resolve_worker_prompt_default():
    """Default resolution uses PHASE_DEFS skill path."""
    with patch("dqg.context.skill_loader.load_skill_progressive") as mock_load:
        mock_load.return_value = "skill content"
        result = resolve_worker_prompt("A")
        assert result == "skill content"
        # Verify it was called with the correct path from PHASE_DEFS
        call_args = mock_load.call_args
        assert "requirement-structuring" in str(call_args[0][0])
        assert call_args[0][1] == "A"


def test_resolve_worker_prompt_with_override(tmp_path):
    """Override replaces SKILL.md path but still goes through progressive loader."""
    override_file = tmp_path / "custom_skill.md"
    override_file.write_text("custom content")
    with patch("dqg.context.skill_loader.load_skill_progressive") as mock_load:
        mock_load.return_value = "loaded via progressive"
        result = resolve_worker_prompt("A", skill_override=str(override_file))
        assert result == "loaded via progressive"
        # Verify override path was passed to loader
        call_args = mock_load.call_args
        assert str(call_args[0][0]) == str(override_file)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_loader_resolve.py -v`
Expected: FAIL (resolve_worker_prompt not defined)

- [ ] **Step 3: Add `resolve_worker_prompt()` to `skill_loader.py`**

Append after `load_skill_progressive()`:

```python
def resolve_worker_prompt(phase: str, skill_override: str | None = None) -> str:
    """Unified skill resolution for ALL execution paths.

    Consolidates cmd_agent_run, cmd_adaptive, dag_scheduler, and replay_executor.
    All paths go through load_skill_progressive() to ensure prompt equivalence.

    Args:
        phase: Phase identifier (e.g., "A", "B", "C")
        skill_override: Optional path to override skill file

    Returns:
        Resolved skill content string
    """
    from dqg.core.phase_registry import PHASE_DEFS

    skill_path = Path(PHASE_DEFS[phase]["skill"])

    if skill_override:
        skill_path = Path(skill_override)

    return load_skill_progressive(skill_path, phase)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_skill_loader_resolve.py -v`
Expected: All PASS

- [ ] **Step 5: Migrate callers in `commands/agents.py`**

Search for direct `read_text()` or `load_skill_progressive()` calls on skill files in `src/dqg/commands/agents.py` and replace with `resolve_worker_prompt(phase)`. The exact locations depend on the current code — grep for `SKILL_FILE_MAP` or `skill` + `read_text` in that file.

- [ ] **Step 6: Migrate callers in `dag_scheduler.py`**

Search for `load_skill_progressive()` calls in `src/dqg/agents/dag_scheduler.py` and replace with `resolve_worker_prompt(phase)`.

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: No new failures

- [ ] **Step 8: Commit**

```bash
git add src/dqg/context/skill_loader.py src/dqg/commands/agents.py src/dqg/agents/dag_scheduler.py tests/test_skill_loader_resolve.py
git commit -m "feat: add resolve_worker_prompt() and migrate all callers to unified skill resolution"
```

---

### Task 6: SkillReflector — Reflect→Write→Verify Loop

**Files:**
- Create: `src/dqg/tracking/skill_reflector.py`
- Test: `tests/test_skill_reflector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_skill_reflector.py
"""Tests for SkillReflector reflect→write→verify loop."""
import hashlib
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dqg.tracking.skill_reflector import (
    SkillReflector, ReflectResult, WriteResult, EvolutionOutcome,
    compute_case_fingerprint,
)


def test_compute_case_fingerprint():
    fp1 = compute_case_fingerprint("A", "FN", "SKILL_RULE", "missing boundary check")
    fp2 = compute_case_fingerprint("A", "FN", "SKILL_RULE", "missing boundary check")
    fp3 = compute_case_fingerprint("A", "FP", "SKILL_RULE", "missing boundary check")
    assert fp1 == fp2  # same input → same fingerprint
    assert fp1 != fp3  # different error_type → different fingerprint


def test_reflect_extracts_patterns():
    reflector = SkillReflector(phase="A", project_id="test-proj")
    judge_results = [
        {"verdict": "FAIL", "overall": 2.0, "issues": [
            {"severity": "high", "description": "missing boundary test for concurrent access"},
        ]},
        {"verdict": "FAIL", "overall": 2.5, "issues": [
            {"severity": "high", "description": "missing boundary test for null input"},
        ]},
        {"verdict": "FAIL", "overall": 2.0, "issues": [
            {"severity": "high", "description": "missing boundary test for edge case"},
        ]},
    ]
    result = reflector.reflect(judge_results)
    assert result.actionable is True
    assert result.root_cause == "SKILL_RULE"
    assert len(result.failure_patterns) > 0


def test_reflect_not_actionable_on_diverse_failures():
    reflector = SkillReflector(phase="A", project_id="test-proj")
    judge_results = [
        {"verdict": "FAIL", "overall": 2.0, "issues": [
            {"severity": "high", "description": "completely different issue A"},
        ]},
        {"verdict": "FAIL", "overall": 2.5, "issues": [
            {"severity": "high", "description": "unrelated problem B"},
        ]},
        {"verdict": "PASS", "overall": 4.0, "issues": []},
    ]
    result = reflector.reflect(judge_results)
    # May or may not be actionable depending on pattern detection
    # At minimum, should not crash
    assert isinstance(result, ReflectResult)


def test_write_low_confidence_returns_human_review():
    reflector = SkillReflector(phase="A", project_id="test-proj")
    reflect_result = ReflectResult(
        actionable=True,
        root_cause="SKILL_RULE",
        failure_patterns=["missing boundary"],
        suggested_changes=["add boundary check rule"],
    )
    # support_count < 3 → HUMAN_REVIEW
    result = reflector.write(reflect_result, support_count=1)
    assert result.mode == "HUMAN_REVIEW"


def test_write_non_skill_rule_always_human_review():
    reflector = SkillReflector(phase="A", project_id="test-proj")
    reflect_result = ReflectResult(
        actionable=True,
        root_cause="CONTEXT",
        failure_patterns=["token budget too low"],
        suggested_changes=["increase budget"],
    )
    result = reflector.write(reflect_result, support_count=5)
    assert result.mode == "HUMAN_REVIEW"  # CONTEXT → always human review in v1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_reflector.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement SkillReflector**

```python
# src/dqg/tracking/skill_reflector.py
"""Reflect→Write→Verify loop for automatic skill evolution.

Triggered when adaptive loop exhausts all iterations with FAIL.
Only SKILL_RULE root cause can be auto-merged (v1).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.constants import CASES_DIR, SKILL_FILE_MAP
from dqg.json_utils import save_json
from dqg.log import get_logger
from dqg.tracking.skill_evolution import HIGH_CONFIDENCE_THRESHOLD

log = get_logger(__name__)


def compute_case_fingerprint(
    phase: str, error_type: str, root_cause: str, lesson: str,
) -> str:
    """Compute dedupe fingerprint for a failure case."""
    normalized = f"{phase}|{error_type}|{root_cause}|{lesson.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class ReflectResult:
    actionable: bool
    root_cause: str = ""  # SKILL_RULE | KNOWLEDGE | CONTEXT | SCHEMA
    failure_patterns: list[str] = field(default_factory=list)
    suggested_changes: list[str] = field(default_factory=list)


@dataclass
class WriteResult:
    mode: str  # AUTO_APPLY | HUMAN_REVIEW
    path: str = ""
    changes: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


@dataclass
class EvolutionOutcome:
    action: str  # SKIP | HUMAN_REVIEW | AUTO_MERGED | REVERTED
    reason: str = ""
    suggestion_path: str = ""
    changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "suggestion_path": self.suggestion_path,
            "changes": self.changes,
        }


class SkillReflector:
    """Analyzes adaptive loop failures and auto-evolves skill rules."""

    def __init__(self, phase: str, project_id: str):
        self.phase = phase
        self.project_id = project_id

    def reflect(self, judge_results: list[dict]) -> ReflectResult:
        """Analyze judge results, extract repeated failure patterns."""
        all_issues = []
        for jr in judge_results:
            for issue in jr.get("issues", []):
                all_issues.append(issue.get("description", ""))

        if not all_issues:
            return ReflectResult(actionable=False)

        # Find repeated patterns (simple keyword frequency)
        words = Counter()
        for desc in all_issues:
            for word in desc.split():
                if len(word) > 3:
                    words[word] += 1

        # If most issues share common keywords → likely SKILL_RULE
        common = words.most_common(5)
        if common and common[0][1] >= 2:
            return ReflectResult(
                actionable=True,
                root_cause="SKILL_RULE",
                failure_patterns=all_issues,
                suggested_changes=[f"Add rule to address: {all_issues[0][:100]}"],
            )

        return ReflectResult(actionable=False, failure_patterns=all_issues)

    def write(self, reflect_result: ReflectResult, support_count: int) -> WriteResult:
        """Apply changes based on root_cause type and confidence level.

        v1: Only SKILL_RULE with support >= HIGH_CONFIDENCE_THRESHOLD can auto-apply.
        All other types → HUMAN_REVIEW.
        """
        # v1: only SKILL_RULE can auto-merge
        if reflect_result.root_cause != "SKILL_RULE":
            suggestion_path = self._write_suggestion_file(reflect_result)
            return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

        if support_count < HIGH_CONFIDENCE_THRESHOLD:
            suggestion_path = self._write_suggestion_file(reflect_result)
            return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

        # Auto-apply: modify skill file
        skill_path = SKILL_FILE_MAP.get(self.phase, "")
        if not skill_path:
            return WriteResult(mode="HUMAN_REVIEW", path="")

        return WriteResult(
            mode="AUTO_APPLY",
            changes=reflect_result.suggested_changes,
            target_files=[skill_path],
        )

    def snapshot_targets(self, target_files: list[str]) -> dict[str, str]:
        """Save original content of target files for rollback."""
        snapshots = {}
        for fp in target_files:
            p = Path(fp)
            if p.exists():
                snapshots[fp] = p.read_text(encoding="utf-8")
        return snapshots

    def rollback(self, snapshot: dict[str, str]) -> None:
        """Restore files from snapshot."""
        for fp, content in snapshot.items():
            Path(fp).write_text(content, encoding="utf-8")
            log.info("Rolled back: %s", fp)

    def persist_as_bug_case(self, reflect_result: ReflectResult) -> str:
        """Persist failure as bug case in failure-library."""
        case_id = f"AUTO-{self.phase}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_dir = Path(CASES_DIR) / f"phase{self.phase}" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        fingerprint = compute_case_fingerprint(
            self.phase, "FN", reflect_result.root_cause,
            reflect_result.failure_patterns[0] if reflect_result.failure_patterns else "",
        )

        case_data = {
            "case_id": case_id,
            "phase": self.phase,
            "error_type": "FN",
            "root_cause": reflect_result.root_cause,
            "lesson": reflect_result.failure_patterns[0] if reflect_result.failure_patterns else "",
            "fingerprint": fingerprint,
            "source_signature": f"{self.project_id}",
            "auto_generated": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_json(case_data, case_dir / "case.json")
        return case_id

    def cluster_and_count_support(self, case_id: str) -> int:
        """Count distinct source signatures for cases with same fingerprint."""
        case_path = Path(CASES_DIR) / f"phase{self.phase}" / case_id / "case.json"
        if not case_path.exists():
            return 1

        current = json.loads(case_path.read_text())
        fingerprint = current.get("fingerprint", "")
        if not fingerprint:
            return 1

        # Scan all cases in this phase for matching fingerprint
        phase_dir = Path(CASES_DIR) / f"phase{self.phase}"
        if not phase_dir.exists():
            return 1

        signatures = set()
        for case_dir in phase_dir.iterdir():
            cf = case_dir / "case.json"
            if not cf.exists():
                continue
            try:
                data = json.loads(cf.read_text())
                if data.get("fingerprint") == fingerprint:
                    sig = data.get("source_signature", "")
                    if sig:
                        signatures.add(sig)
            except (json.JSONDecodeError, OSError):
                continue

        return len(signatures)

    def reflect_and_write(self, judge_results: list[dict]) -> EvolutionOutcome:
        """Full Reflect→Persist→Cluster→Write→Verify pipeline."""
        reflect_result = self.reflect(judge_results)
        if not reflect_result.actionable:
            return EvolutionOutcome(action="SKIP", reason="No actionable pattern found")

        case_id = self.persist_as_bug_case(reflect_result)
        support_count = self.cluster_and_count_support(case_id)

        write_result = self.write(reflect_result, support_count)
        if write_result.mode == "HUMAN_REVIEW":
            return EvolutionOutcome(
                action="HUMAN_REVIEW", suggestion_path=write_result.path,
            )

        # Patch-level transactional rollback
        snapshot = self.snapshot_targets(write_result.target_files)
        # TODO: apply_changes + verify in future iteration
        # For v1, auto-apply generates the suggestion but does not modify files
        # until holdout replay infrastructure is ready
        return EvolutionOutcome(
            action="HUMAN_REVIEW",
            reason="v1: auto-apply deferred until holdout replay is ready",
            changes=write_result.changes,
        )

    def _write_suggestion_file(self, reflect_result: ReflectResult) -> str:
        """Write suggestion file for human review."""
        from dqg.constants import PHASE_DIR_MAP
        suggestion_dir = Path("output") / self.project_id / PHASE_DIR_MAP.get(self.phase, self.phase)
        suggestion_dir.mkdir(parents=True, exist_ok=True)
        path = suggestion_dir / f"_skill_suggestions_{self.phase}.md"

        content = f"# Skill Evolution Suggestions — Phase {self.phase}\n\n"
        content += f"Root Cause: {reflect_result.root_cause}\n\n"
        content += "## Failure Patterns\n\n"
        for p in reflect_result.failure_patterns:
            content += f"- {p}\n"
        content += "\n## Suggested Changes\n\n"
        for c in reflect_result.suggested_changes:
            content += f"- {c}\n"

        path.write_text(content, encoding="utf-8")
        return str(path)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_skill_reflector.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/tracking/skill_reflector.py tests/test_skill_reflector.py
git commit -m "feat: add SkillReflector with reflect→persist→cluster→write pipeline"
```

---

### Task 7: Adaptive Loop — SkillReflector Integration + Judge Health Gate

**Files:**
- Modify: `src/dqg/agents/adaptive_loop.py`
- Test: `tests/test_adaptive_skill_evolution.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adaptive_skill_evolution.py
"""Tests for adaptive loop → SkillReflector integration."""
import pytest
from unittest.mock import patch, MagicMock
from dqg.agents.adaptive_loop import judge_health_check, VoteResult, JudgeVote


def test_judge_health_check_healthy():
    votes = [JudgeVote(model="m", scores={}, overall=4.0, verdict="PASS", issues=[], health="HEALTHY")]
    vr1 = VoteResult(votes=votes, consensus="PASS", avg_score=4.0, disagreements=[])
    vr2 = VoteResult(votes=votes, consensus="PASS", avg_score=4.0, disagreements=[])
    assert judge_health_check([vr1, vr2]) == "HEALTHY"


def test_judge_health_check_semantic_fail():
    votes = [JudgeVote(model="m", scores={}, overall=2.0, verdict="FAIL", issues=[], health="HEALTHY")]
    vr1 = VoteResult(votes=votes, consensus="FAIL", avg_score=2.0, disagreements=[])
    vr2 = VoteResult(votes=votes, consensus="FAIL", avg_score=2.0, disagreements=[])
    assert judge_health_check([vr1, vr2]) == "SEMANTIC_FAIL"


def test_judge_health_check_infra_failure():
    votes = [JudgeVote(model="m", scores={}, overall=0, verdict="FAIL", issues=[], health="INFRA_FAILURE")]
    vr1 = VoteResult(votes=votes, consensus="FAIL", avg_score=0, disagreements=[])
    assert judge_health_check([vr1]) == "INFRA_FAILURE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_adaptive_skill_evolution.py -v`
Expected: FAIL (judge_health_check not importable or missing health field)

- [ ] **Step 3: Add SkillReflector trigger to adaptive loop**

In `src/dqg/agents/adaptive_loop.py`, find the section where all iterations are exhausted with FAIL (the end of the adaptive loop's main iteration). Add after the loop exits:

```python
# After adaptive loop exhausts all iterations
# Check judge health before triggering skill evolution
if all_failed:
    health = judge_health_check(all_judge_results)
    if health == "SEMANTIC_FAIL":
        log.info("All iterations FAIL with healthy judges → triggering SkillReflector")
        from dqg.tracking.skill_reflector import SkillReflector
        reflector = SkillReflector(phase=phase, project_id=project_id)
        # Collect judge issues from all iterations
        judge_dicts = []
        for vr in all_judge_results:
            for v in vr.votes:
                judge_dicts.append({
                    "verdict": v.verdict,
                    "overall": v.overall,
                    "issues": v.issues,
                })
        evolution_outcome = reflector.reflect_and_write(judge_dicts)
        log.info("SkillReflector outcome: %s", evolution_outcome.action)
    elif health == "INFRA_FAILURE":
        log.warning("Judge infrastructure failure detected, skipping skill evolution")
```

Note: The exact insertion point depends on the current loop structure. Look for where `IterationRecord` objects are collected and the final summary is built.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_adaptive_skill_evolution.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: No new failures

- [ ] **Step 6: Commit**

```bash
git add src/dqg/agents/adaptive_loop.py tests/test_adaptive_skill_evolution.py
git commit -m "feat: integrate SkillReflector into adaptive loop with judge health gate"
```

---

### Task 8: Phase Registry — required_report_sections + Structure Contract

**Files:**
- Modify: `src/dqg/core/phase_registry.py`
- Modify: `src/dqg/runtime/phase_contract.py`
- Test: `tests/test_report_structure_check.py`

- [ ] **Step 1: Write failing test for structure check**

```python
# tests/test_report_structure_check.py
"""Tests for report structure contract check."""
import pytest
from dqg.runtime.phase_contract import check_report_structure


def test_check_report_structure_all_present():
    report = """# Phase A Report

## 需求清单

REQ-001: 用户登录

## SE 关键语义清单

SE-001: 并发登录互斥

## 业务规则

BR-001: 密码复杂度

## Gap 分析

GAP-001: 未定义超时策略
"""
    result = check_report_structure(report, "A")
    assert result["passed"] is True
    assert len(result["missing"]) == 0


def test_check_report_structure_missing_section():
    report = """# Phase A Report

## 需求清单

REQ-001: 用户登录

## 业务规则

BR-001: 密码复杂度
"""
    result = check_report_structure(report, "A")
    assert result["passed"] is False
    assert len(result["missing"]) >= 1


def test_check_report_structure_alias_match():
    """Aliases should match too."""
    report = """# Phase A Report

## REQ/BR 需求清单

content

## SE List

content

## BR 业务规则

content

## GAP 缺口清单

content
"""
    result = check_report_structure(report, "A")
    assert result["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_report_structure_check.py -v`
Expected: FAIL (check_report_structure not defined)

- [ ] **Step 3: Add `required_report_sections` to `phase_registry.py`**

Add to each PHASE_DEFS entry. For Phase A (after `approve_checklist`):

```python
        "required_report_sections": [
            {"canonical": "需求清单", "aliases": ["REQ/BR 需求清单", "需求列表", "需求点"]},
            {"canonical": "SE 列表", "aliases": ["SE 关键语义清单", "关键语义", "SE List"]},
            {"canonical": "业务规则", "aliases": ["BR 业务规则", "Business Rules"]},
            {"canonical": "Gap 分析", "aliases": ["GAP 缺口清单", "缺口分析", "Gap Analysis"]},
        ],
```

For Phase B:

```python
        "required_report_sections": [
            {"canonical": "测试用例清单", "aliases": ["单测用例", "Test Cases", "EUT Matrix"]},
            {"canonical": "覆盖率矩阵", "aliases": ["Coverage Matrix", "覆盖率"]},
        ],
```

For Phase C:

```python
        "required_report_sections": [
            {"canonical": "审计结果", "aliases": ["Audit Results", "审计发现"]},
            {"canonical": "覆盖率分析", "aliases": ["Coverage Analysis", "覆盖率"]},
        ],
```

For Phase D:

```python
        "required_report_sections": [
            {"canonical": "评审发现", "aliases": ["Review Findings", "发现列表"]},
            {"canonical": "需求代码对齐", "aliases": ["Req-Code Alignment", "对齐分析"]},
        ],
```

For other phases (A.3, A.5, A.6), add appropriate sections based on their deliverables.

- [ ] **Step 4: Add `check_report_structure()` to `phase_contract.py`**

```python
def check_report_structure(report_content: str, phase: str) -> dict[str, Any]:
    """Check report against required_report_sections from phase_registry.

    Uses fuzzy matching: section header must contain canonical name or any alias.

    Returns:
        {"passed": bool, "missing": [str], "found": [str]}
    """
    import re
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase, {})
    required = phase_def.get("required_report_sections", [])
    if not required:
        return {"passed": True, "missing": [], "found": []}

    # Extract H2/H3 headers from markdown
    headers = re.findall(r"^#{2,3}\s+(.+)$", report_content, re.MULTILINE)
    headers_lower = [h.strip().lower() for h in headers]

    found = []
    missing = []
    for section in required:
        canonical = section["canonical"]
        aliases = section.get("aliases", [])
        all_names = [canonical] + aliases

        matched = False
        for name in all_names:
            name_lower = name.lower()
            if any(name_lower in h for h in headers_lower):
                matched = True
                break

        if matched:
            found.append(canonical)
        else:
            missing.append(canonical)

    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "found": found,
    }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_report_structure_check.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/core/phase_registry.py src/dqg/runtime/phase_contract.py tests/test_report_structure_check.py
git commit -m "feat: add required_report_sections to phase_registry + check_report_structure()"
```

---

## Execution Order & Dependencies

```
Task 1: Constants + StructuredChatResult + chat_structured()
  ↓
Task 2: JudgeRunner (depends on Task 1: StructuredChatResult)
  ↓
Task 3: RationalizationGuard (depends on Task 1: constants)
  ↓
Task 4: Adaptive Loop Integration (depends on Task 2 + Task 3)
  ↓
Task 5: resolve_worker_prompt() (independent, can parallel with Task 3-4)
  ↓
Task 6: SkillReflector (depends on Task 1: constants)
  ↓
Task 7: Adaptive Loop + SkillReflector (depends on Task 4 + Task 6)
  ↓
Task 8: Phase Registry + Structure Contract (independent, can parallel with Task 5-7)
```

Parallelizable groups:
- Group A: Task 1 → Task 2 → Task 4 → Task 7 (critical path)
- Group B: Task 3 (after Task 1), Task 5, Task 6, Task 8 (can run in parallel with Group A where deps allow)
