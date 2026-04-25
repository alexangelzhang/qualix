"""Multi-Judge voting logic for adaptive loop."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

from dqg.log import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


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


def _write_hard_block_result(output_dir: Path, vote: JudgeVote, guard_result: Any) -> None:
    """HARD_BLOCK 时写入 _judge_result.json，让 cmd_approve 能读到并拦截。"""
    from datetime import datetime

    from dqg.json_utils import save_json

    result = {
        "verdict": "HARD_BLOCK",
        "overall_score": vote.overall,
        "health": "GUARD_EXHAUSTED",
        "hard_blocked": True,
        "block_reason": "Anti-Rationalization Guard: 二次确认仍检测到放水行为，Judge 结果无效",
        "confirmed_rationalizations": guard_result.confirmed_rationalizations,
        "judged_at": datetime.now(UTC).isoformat(),
    }
    from pathlib import Path

    block_path = Path(output_dir) / "_hard_block_result.json"
    try:
        save_json(block_path, result)
        log.warning("HARD_BLOCK result written to %s", block_path)
    except Exception as e:
        log.error("Failed to write HARD_BLOCK result: %s", e)


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
        phase="",
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


def _run_secondary_fallback(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    secondary_models: list[str],
    fallback: str,
    pass_threshold: float,
    concerns_delta: float,
) -> VoteResult:
    """Collect votes from secondary models and compute consensus."""
    votes: list[JudgeVote] = []
    for model in secondary_models:
        vote = _run_single_judge(output_dir, report_path, rubric, model, fallback)
        if vote is not None:
            votes.append(vote)
    if not votes:
        return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["所有 Judge 执行失败"])
    avg_score = sum(v.overall for v in votes) / len(votes)
    verdicts = [v.verdict for v in votes]
    consensus = _compute_consensus(verdicts, avg_score, pass_threshold, concerns_delta)
    return VoteResult(votes=votes, consensus=consensus, avg_score=avg_score, disagreements=[])


def _compute_consensus(
    verdicts: list[str],
    avg_score: float,
    pass_threshold: float,
    concerns_delta: float,
) -> str:
    """从投票结果计算共识."""
    if all(v == "PASS" for v in verdicts):
        return "PASS"
    if all(v == "FAIL" for v in verdicts) or verdicts.count("FAIL") > len(verdicts) / 2:
        return "FAIL"
    if avg_score >= pass_threshold:
        return "PASS_WITH_CONCERNS"
    if avg_score >= pass_threshold - concerns_delta:
        return "PASS_WITH_CONCERNS"
    return "FAIL"


def multi_judge_vote(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    models: list[str],
    fallback: str = "deepseek-chat",
    force_secondary: bool = False,
) -> VoteResult:
    """Primary Judge + Secondary Validation 策略.

    1. 先用第一个模型（primary）独立评审
    2. 如果 primary 分数在边界区间（pass_threshold ± 0.5），启动 secondary 验证
    3. 如果 primary 分数明确 PASS 或 FAIL，直接采纳，不浪费 secondary 调用
    """
    from dqg.constants import JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA

    unique_models = list(dict.fromkeys(models))
    if not unique_models:
        return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["No judge models configured"])

    primary_model = unique_models[0]
    secondary_models = unique_models[1:]

    primary_vote = _run_single_judge(output_dir, report_path, rubric, primary_model, fallback)
    if primary_vote is None:
        log.warning("Primary judge %s failed, falling back to secondary models", primary_model)
        return _run_secondary_fallback(
            output_dir,
            report_path,
            rubric,
            secondary_models,
            fallback,
            JUDGE_PASS_THRESHOLD,
            JUDGE_PASS_WITH_CONCERNS_DELTA,
        )

    # Guard: Anti-Rationalization check on primary vote
    if primary_vote.raw_output:
        from dqg.quality.rationalization_guard import RationalizationGuard, format_rejudge_warning

        guard = RationalizationGuard()
        guard_result = guard.check(primary_vote.raw_output)

        if not guard_result.passed:
            log.warning("Guard detected rationalization in primary judge, re-judging")
            warning_text = format_rejudge_warning(guard_result)
            rejudged = _run_single_judge(
                output_dir,
                report_path,
                rubric,
                primary_model,
                fallback,
                warning_override=warning_text,
            )
            if rejudged is not None:
                guard_result_2 = guard.check(rejudged.raw_output)
                if not guard_result_2.passed:
                    log.warning("Guard HARD_BLOCK: rationalization persists after re-judge")
                    rejudged.health = "GUARD_EXHAUSTED"
                    rejudged.verdict = "HARD_BLOCK"
                    _write_hard_block_result(output_dir, rejudged, guard_result_2)
                    return None
                primary_vote = rejudged

    # Guard: Anti-Overcorrection check on primary vote
    if primary_vote and primary_vote.raw_output:
        from dqg.quality.rationalization_guard import OvercorrectionGuard, format_overcorrection_warning

        oc_guard = OvercorrectionGuard()
        oc_result = oc_guard.check(primary_vote.raw_output)

        if oc_result.has_overcorrection:
            log.warning(
                "Overcorrection detected: %d patterns, %d FAIL without evidence",
                len(oc_result.confirmed_overcorrections),
                len(oc_result.fail_without_evidence),
            )
            warning_text = format_overcorrection_warning(oc_result)
            rejudged = _run_single_judge(
                output_dir,
                report_path,
                rubric,
                primary_model,
                fallback,
                warning_override=warning_text,
            )
            if rejudged is not None:
                primary_vote = rejudged

    if primary_vote is None:
        log.warning("Primary judge excluded, falling back to secondary models")
        return _run_secondary_fallback(
            output_dir,
            report_path,
            rubric,
            secondary_models,
            fallback,
            JUDGE_PASS_THRESHOLD,
            JUDGE_PASS_WITH_CONCERNS_DELTA,
        )

    votes: list[JudgeVote] = [primary_vote]

    boundary_low = JUDGE_PASS_THRESHOLD - JUDGE_PASS_WITH_CONCERNS_DELTA
    boundary_high = JUDGE_PASS_THRESHOLD + JUDGE_PASS_WITH_CONCERNS_DELTA
    is_boundary = boundary_low <= primary_vote.overall <= boundary_high

    if (force_secondary or is_boundary) and secondary_models:
        log.info(
            "Primary judge %s score=%.1f in boundary [%.1f, %.1f], invoking secondary validation",
            primary_model,
            primary_vote.overall,
            boundary_low,
            boundary_high,
        )
        max_workers = max(1, len(secondary_models))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_single_judge, output_dir, report_path, rubric, model, fallback): model
                for model in secondary_models
            }
            for future in as_completed(futures):
                vote = future.result()
                if vote is not None:
                    votes.append(vote)
    elif not is_boundary and not force_secondary:
        log.info(
            "Primary judge %s score=%.1f clear %s, skipping secondary validation",
            primary_model,
            primary_vote.overall,
            "PASS" if primary_vote.overall >= JUDGE_PASS_THRESHOLD else "FAIL",
        )

    avg_score = sum(v.overall for v in votes) / len(votes)
    verdicts = [v.verdict for v in votes]
    consensus = _compute_consensus(verdicts, avg_score, JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA)

    disagreements = []
    if len(set(verdicts)) > 1:
        for v in votes:
            disagreements.append(f"{v.model}: {v.verdict} (score={v.overall:.1f})")

    return VoteResult(votes=votes, consensus=consensus, avg_score=avg_score, disagreements=disagreements)


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
