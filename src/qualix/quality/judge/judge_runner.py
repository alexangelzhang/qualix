"""Unified Judge execution with canonical output schema.

Serves manual, adaptive, and holdout execution modes.
All modes produce the same canonical schema for downstream consumers.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, Final

from qualix.agents.llm_backends import (
    LLMConfig,
    create_backend,
)
from qualix.log import get_logger

log = get_logger(__name__)

# 当 JSON 结构化输出失败时，要求 LLM 在最后一行写 sentinel 以保留 pass/fail + score 信号
_SENTINEL_INSTRUCTION: Final[str] = (
    "\n\n---\n"
    "**FALLBACK**: If JSON output fails for any reason, output ONLY one of these lines as the very last line:\n"
    "`DQG_VERDICT:PASS:X.X` or `DQG_VERDICT:FAIL:X.X` (where X.X is the overall score 1.0–5.0)"
)

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
    token_usage: dict[str, int] = field(default_factory=dict)
    failing_dimensions: list[str] = field(default_factory=list)  # 触发 fail_threshold 的维度 ID
    _schema_version: int = 1


def _extract_sentinel_verdict(raw_output: str) -> tuple[str, float] | None:
    """检查 raw_output 最后 5 个非空行是否含 DQG_VERDICT sentinel.

    支持带 score 格式（DQG_VERDICT:PASS:4.2）和无 score 旧格式（DQG_VERDICT:PASS）。
    返回 (verdict, score) 或 None。
    """
    if not raw_output:
        return None
    last_lines = [ln.strip() for ln in raw_output.splitlines() if ln.strip()][-5:]
    for line in last_lines:
        for prefix, verdict in (("DQG_VERDICT:PASS", "PASS"), ("DQG_VERDICT:FAIL", "FAIL")):
            if line.startswith(prefix):
                parts = line.split(":")
                score = 0.0
                if len(parts) == 3:
                    with contextlib.suppress(ValueError):
                        score = float(parts[2])
                return (verdict, score)
    return None


class JudgeRunner:
    """Unified Judge execution with primary→fallback model chain."""

    def __init__(self, rubric_dims: list[dict[str, Any]] | None = None) -> None:
        """Initialize runner.

        Args:
            rubric_dims: 可选的评分维度定义（含 fail_threshold），传入后
                内部 _call_judge 调 normalize 时会自动应用门限机制。
                不传则保持旧行为（只加权平均打分，不做门限降级）。
        """
        self._rubric_dims = rubric_dims

    @staticmethod
    def normalize(
        raw: dict[str, Any],
        raw_output: str = "",
        rubric_dims: list[dict[str, Any]] | None = None,
    ) -> JudgeResult:
        """Normalize any Judge output variant to canonical schema.

        Handles:
        - overall vs overall_score
        - scores dict → dimensions list conversion
        - Empty/invalid → INFRA_FAILURE
        - fail_threshold 门限：当 rubric_dims 提供且某维度 score < 其 fail_threshold
          时，整体 verdict 被强制降级为 FAIL，不受加权平均稀释。
          触发的维度 ID 记录在 result.failing_dimensions。

        Wire-compatible: existing consumers可不传 rubric_dims，行为保持不变。
        """
        if not raw or (not raw.get("overall") and not raw.get("overall_score")):
            sentinel = _extract_sentinel_verdict(raw_output)
            if sentinel:
                s_verdict, s_score = sentinel
                log.info("Judge JSON parse failed, sentinel fallback: %s score=%.1f", s_verdict, s_score)
                return JudgeResult(
                    overall_score=s_score,
                    verdict=s_verdict,
                    dimensions=[],
                    issues=[],
                    raw_output=raw_output,
                    health="SENTINEL_FALLBACK",
                )
            return JudgeResult(
                overall_score=0,
                verdict="FAIL",
                dimensions=[],
                issues=[],
                raw_output=raw_output,
                health="INFRA_FAILURE",
            )

        overall = raw.get("overall_score") or raw.get("overall", 0)

        # Normalize dimensions: if scores dict, convert to list
        dimensions = raw.get("dimensions", [])
        if not dimensions and isinstance(raw.get("scores"), dict):
            dimensions = [{"id": k, "name": k, "score": v, "weight": 0, "issues": []} for k, v in raw["scores"].items()]

        all_issues = list(raw.get("issues", []))
        verdict = raw.get("verdict", "FAIL")

        # 维度门限检查：任一维度 score < 其 fail_threshold 直接降级为 FAIL
        failing_dims: list[str] = []
        if rubric_dims:
            thresholds = {d["id"]: d["fail_threshold"] for d in rubric_dims if "fail_threshold" in d}
            if thresholds:
                scores_map = {d["id"]: d.get("score", 0) for d in dimensions}
                if not scores_map and isinstance(raw.get("scores"), dict):
                    scores_map = dict(raw["scores"])
                for dim_id, threshold in thresholds.items():
                    score = scores_map.get(dim_id)
                    if score is not None and score < threshold:
                        failing_dims.append(dim_id)
                if failing_dims:
                    verdict = "FAIL"

        return JudgeResult(
            overall_score=float(overall),
            verdict=verdict,
            dimensions=dimensions,
            issues=all_issues,
            raw_output=raw_output,
            health="HEALTHY",
            failing_dimensions=failing_dims,
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

        rubric_text = rubric + _SENTINEL_INSTRUCTION
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
                messages,
                JUDGE_RESPONSE_SCHEMA,
                max_tokens=2000,
            )
            result = self.normalize(structured.parsed, raw_output=structured.raw_text, rubric_dims=self._rubric_dims)
            result.model = model
            result.token_usage = structured.provider_meta.get("usage", {})
            log.info("JudgeRunner %s: verdict=%s, overall=%.1f", model, result.verdict, result.overall_score)
            return result
        except Exception as e:
            log.error("JudgeRunner %s failed: %s", model, e)
            return JudgeResult(
                overall_score=0,
                verdict="FAIL",
                dimensions=[],
                issues=[],
                raw_output=str(e),
                health="INFRA_FAILURE",
                model=model,
            )
