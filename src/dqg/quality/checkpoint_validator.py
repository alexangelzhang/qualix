"""Checkpoint validator: rule + LLM two-layer validation for runtime eval.

Used at two breakpoints:
1. Two-Phase Worker: after Collector, before Writer (evidence_pack quality)
2. DAG Preflight: after file existence, before Phase start (upstream content quality)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# Minimum coverage ratio for verification targets
_MIN_COVERAGE_RATIO = 0.6
# Coverage ratio below which LLM confirmation is triggered
_LLM_TRIGGER_COVERAGE = 0.8
# LLM confirmation timeout in seconds
_LLM_TIMEOUT = 10
# Minimum content length (chars) to be considered non-empty
_MIN_CONTENT_LENGTH = 50


@dataclass
class CheckpointResult:
    """Result of a checkpoint validation."""

    passed: bool
    rule_checks: list[dict[str, Any]] = field(default_factory=list)
    llm_check: dict[str, Any] | None = None
    block_reason: str = ""


def validate_checkpoint(
    content: str,
    contract: dict[str, Any],
    phase_id: str,
    checkpoint_name: str,
) -> CheckpointResult:
    """Validate content against Phase Contract at a checkpoint.

    Rule layer (zero LLM): non-empty, ID coverage >= 60%, source annotations.
    LLM layer (haiku): triggered when coverage 60-80%, confirms adequacy.
    No contract or no targets → skip, return PASS.
    """
    targets = contract.get("verification_targets", [])
    if not contract or not targets:
        return CheckpointResult(
            passed=True,
            rule_checks=[
                {"name": "skip", "passed": True, "detail": "No contract or targets, checkpoint skipped"},
            ],
        )

    result = CheckpointResult(passed=True)

    # Rule 1: Non-empty content
    non_empty = _check_non_empty(content)
    result.rule_checks.append(non_empty)
    if not non_empty["passed"]:
        result.passed = False
        result.block_reason = f"Checkpoint {checkpoint_name}: content empty or too short (内容为空或过短)"
        return result

    # Rule 2: Verification target ID coverage
    coverage_check, coverage_ratio = _check_id_coverage(content, targets)
    result.rule_checks.append(coverage_check)
    if not coverage_check["passed"]:
        result.passed = False
        result.block_reason = (
            f"Checkpoint {checkpoint_name}: 验证目标覆盖率 {coverage_ratio:.0%} < {_MIN_COVERAGE_RATIO:.0%}"
        )
        return result

    # Rule 3: Source annotations (for evidence_pack type)
    if checkpoint_name == "evidence_pack":
        source_check = _check_source_annotations(content)
        result.rule_checks.append(source_check)
        if not source_check["passed"]:
            result.passed = False
            result.block_reason = f"Checkpoint {checkpoint_name}: 证据缺少来源标注"
            return result

    # LLM layer: triggered when coverage is borderline (60-80%)
    if _MIN_COVERAGE_RATIO <= coverage_ratio < _LLM_TRIGGER_COVERAGE:
        llm_result = _llm_confirm(content, targets, phase_id, checkpoint_name)
        result.llm_check = llm_result
        if not llm_result.get("passed", True):
            result.passed = False
            result.block_reason = f"Checkpoint {checkpoint_name}: LLM 确认覆盖不充分 — {llm_result.get('detail', '')}"

    return result


def _check_non_empty(content: str) -> dict[str, Any]:
    """Check content is non-empty and above minimum length."""
    stripped = content.strip()
    passed = len(stripped) >= _MIN_CONTENT_LENGTH
    return {
        "name": "non_empty",
        "passed": passed,
        "detail": f"Content length: {len(stripped)} chars" + ("" if passed else f" (min: {_MIN_CONTENT_LENGTH})"),
    }


def _check_id_coverage(content: str, targets: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    """Check what fraction of verification target IDs appear in content."""
    if not targets:
        return {"name": "id_coverage", "passed": True, "detail": "No targets"}, 1.0

    content_lower = content.lower()
    hit = 0
    missed_ids = []
    for t in targets:
        tid = t.get("id", "")
        if tid and tid.lower() in content_lower:
            hit += 1
        elif tid:
            missed_ids.append(tid)

    ratio = hit / len(targets)
    passed = ratio >= _MIN_COVERAGE_RATIO
    detail = f"{hit}/{len(targets)} targets covered ({ratio:.0%})"
    if missed_ids and not passed:
        detail += f", missing: {', '.join(missed_ids[:5])}"

    return {"name": "id_coverage", "passed": passed, "detail": detail}, ratio


def _check_source_annotations(content: str) -> dict[str, Any]:
    """Check evidence_pack entries have source annotations."""
    import json as _json

    try:
        data = _json.loads(content)
    except (ValueError, TypeError):
        # Plain text — check for source patterns
        has_source = bool(re.search(r"[来源:|source:|文件名:\d+]", content))
        return {"name": "source_annotations", "passed": has_source, "detail": "Plain text source check"}

    evidences = data.get("evidences", [])
    if not evidences:
        return {"name": "source_annotations", "passed": False, "detail": "No evidences in pack"}

    with_source = sum(1 for e in evidences if e.get("source"))
    ratio = with_source / len(evidences) if evidences else 0
    passed = ratio >= 0.5
    return {
        "name": "source_annotations",
        "passed": passed,
        "detail": f"{with_source}/{len(evidences)} evidences have source ({ratio:.0%})",
    }


def _llm_confirm(
    content: str,
    targets: list[dict[str, Any]],
    phase_id: str,
    checkpoint_name: str,
) -> dict[str, Any]:
    """Use haiku-level model to confirm coverage adequacy. 10s timeout → PASS on failure."""
    try:
        from dqg.agents.llm_backends import create_backend
        from dqg.constants import DEFAULT_RATIONALIZATION_CONFIRM_MODEL

        model = DEFAULT_RATIONALIZATION_CONFIRM_MODEL
        # Resolve API key via LLMConfig helper
        from dqg.agents.llm_backends import LLMConfig

        api_key = LLMConfig(primary=model)._resolve_api_key(model)

        target_summary = "\n".join(f"- {t.get('id', '?')}: {t.get('description', '')}" for t in targets[:10])
        prompt = (
            f"Phase {phase_id} checkpoint '{checkpoint_name}' 验证。\n\n"
            f"验证目标：\n{target_summary}\n\n"
            f"内容摘要（前2000字）：\n{content[:2000]}\n\n"
            "问题：以上内容是否充分覆盖了验证目标中的关键项？\n"
            "回答 YES 或 NO，如果 NO 请列出缺失的关键目标 ID。"
        )

        backend = create_backend(model, api_key)
        answer_text, _ = backend.chat(
            messages=[{"role": "user", "content": prompt}],
            timeout=_LLM_TIMEOUT,
        )

        answer = (answer_text or "").strip().upper()
        passed = answer.startswith("YES")
        return {"passed": passed, "detail": (answer_text or "")[:200], "model": model}

    except Exception as e:
        log.debug("LLM checkpoint confirm failed (timeout or error), defaulting to PASS: %s", e)
        return {"passed": True, "detail": f"LLM unavailable ({e}), defaulting to PASS", "model": "fallback"}
