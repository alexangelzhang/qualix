"""Guard execution blocks extracted from `multi_judge_vote()`.

Isolates the Anti-Rationalization and Anti-Overcorrection guard logic
(including telemetry emission and re-judge budget handling) so that the
main voting flow stays legible and the file stays under the 400-line
module cap.

Each guard function:
- accepts the current primary vote + context
- may call JudgeRunner again for a re-judge
- returns the (possibly replaced) primary vote, or None when HARD_BLOCK
  is triggered (caller should then fall through to secondary validation)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from qualix.log import get_logger
from qualix.quality.judge.guard_telemetry import log_guard_event, save_guard_pair

if TYPE_CHECKING:
    from qualix.agents.judge_vote import JudgeVote

log = get_logger(__name__)

# Alias for the _run_single_judge callable to avoid circular import at module level.
# Accepts: (output_dir, report_path, rubric, model, fallback, warning_override) -> JudgeVote | None
JudgeRunnerFn = Callable[..., "JudgeVote | None"]


def apply_rationalization_guard(
    *,
    primary_vote: JudgeVote,
    run_single_judge: JudgeRunnerFn,
    write_hard_block_result: Callable[[Path, JudgeVote, object], None],
    output_dir: Path,
    report_path: Path,
    rubric: str,
    primary_model: str,
    fallback: str,
    internal_dir: Path,
    phase_id: str,
) -> JudgeVote | None:
    """Run RationalizationGuard, re-judge once if needed, emit telemetry.

    Returns:
        New primary_vote (possibly replaced by re-judge), or None when
        HARD_BLOCK was triggered (rationalization persists after re-judge).
    """
    if not primary_vote.raw_output:
        return primary_vote

    from qualix.quality.rationalization_guard import RationalizationGuard, format_rejudge_warning

    guard = RationalizationGuard()
    guard_result = guard.check(primary_vote.raw_output)
    if guard_result.passed:
        return primary_vote

    log.warning("Guard detected rationalization in primary judge, re-judging")
    log_guard_event(
        internal_dir,
        guard="rationalization",
        event="LAYER1_HIT",
        phase=phase_id,
        model=primary_model,
        detected_patterns=guard_result.detected_patterns,
        confirmed_items=guard_result.confirmed_rationalizations,
    )

    warning_text = format_rejudge_warning(guard_result)
    rejudged = run_single_judge(
        output_dir,
        report_path,
        rubric,
        primary_model,
        fallback,
        warning_override=warning_text,
    )
    if rejudged is None:
        return primary_vote

    guard_result_2 = guard.check(rejudged.raw_output)
    if not guard_result_2.passed:
        # Budget exhausted — HARD_BLOCK
        log.warning("Guard HARD_BLOCK: rationalization persists after re-judge")
        rejudged.health = "GUARD_EXHAUSTED"
        rejudged.verdict = "HARD_BLOCK"
        pair_ref = save_guard_pair(
            internal_dir,
            guard="rationalization",
            phase=phase_id,
            model=primary_model,
            before_vote=primary_vote,
            after_vote=rejudged,
            terminal_state="GUARD_EXHAUSTED",
            detected_patterns=guard_result_2.detected_patterns,
            confirmed_items=guard_result_2.confirmed_rationalizations,
        )
        log_guard_event(
            internal_dir,
            guard="rationalization",
            event="GUARD_EXHAUSTED",
            phase=phase_id,
            model=primary_model,
            detected_patterns=guard_result_2.detected_patterns,
            confirmed_items=guard_result_2.confirmed_rationalizations,
            pair_ref=pair_ref,
        )
        write_hard_block_result(output_dir, rejudged, guard_result_2)
        return None

    # Re-judge passed — replace primary vote
    pair_ref = save_guard_pair(
        internal_dir,
        guard="rationalization",
        phase=phase_id,
        model=primary_model,
        before_vote=primary_vote,
        after_vote=rejudged,
        terminal_state="REJUDGE_PASSED",
        detected_patterns=guard_result.detected_patterns,
        confirmed_items=guard_result.confirmed_rationalizations,
    )
    log_guard_event(
        internal_dir,
        guard="rationalization",
        event="REJUDGE_PASSED",
        phase=phase_id,
        model=primary_model,
        detected_patterns=guard_result.detected_patterns,
        confirmed_items=guard_result.confirmed_rationalizations,
        pair_ref=pair_ref,
    )
    return rejudged


def apply_overcorrection_guard(
    *,
    primary_vote: JudgeVote,
    run_single_judge: JudgeRunnerFn,
    output_dir: Path,
    report_path: Path,
    rubric: str,
    primary_model: str,
    fallback: str,
    internal_dir: Path,
    phase_id: str,
) -> JudgeVote:
    """Run OvercorrectionGuard, re-judge once if triggered, emit telemetry.

    Returns the (possibly replaced) primary_vote. Never produces HARD_BLOCK
    (overcorrection is prompt-softening, not a fail-safe fallback).
    """
    if not primary_vote.raw_output:
        return primary_vote

    from qualix.quality.rationalization_guard import OvercorrectionGuard, format_overcorrection_warning

    oc_guard = OvercorrectionGuard()
    oc_result = oc_guard.check(primary_vote.raw_output)
    if not oc_result.has_overcorrection:
        return primary_vote

    log.warning(
        "Overcorrection detected: %d patterns, %d FAIL without evidence",
        len(oc_result.confirmed_overcorrections),
        len(oc_result.fail_without_evidence),
    )
    confirmed_items = list(oc_result.confirmed_overcorrections) + list(oc_result.fail_without_evidence)
    log_guard_event(
        internal_dir,
        guard="overcorrection",
        event="LAYER1_HIT",
        phase=phase_id,
        model=primary_model,
        detected_patterns=oc_result.detected_patterns,
        confirmed_items=confirmed_items,
    )

    warning_text = format_overcorrection_warning(oc_result)
    rejudged = run_single_judge(
        output_dir,
        report_path,
        rubric,
        primary_model,
        fallback,
        warning_override=warning_text,
    )
    if rejudged is None:
        return primary_vote

    pair_ref = save_guard_pair(
        internal_dir,
        guard="overcorrection",
        phase=phase_id,
        model=primary_model,
        before_vote=primary_vote,
        after_vote=rejudged,
        terminal_state="REJUDGE_PASSED",
        detected_patterns=oc_result.detected_patterns,
        confirmed_items=confirmed_items,
    )
    log_guard_event(
        internal_dir,
        guard="overcorrection",
        event="REJUDGE_PASSED",
        phase=phase_id,
        model=primary_model,
        detected_patterns=oc_result.detected_patterns,
        confirmed_items=confirmed_items,
        pair_ref=pair_ref,
    )
    return rejudged


__all__ = ["apply_overcorrection_guard", "apply_rationalization_guard"]
