"""Multi-Judge voting logic for adaptive loop."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC
from typing import TYPE_CHECKING, Any

from qualix.agents.judge_types import IterationRecord, JudgeVote, VoteResult
from qualix.log import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

# Re-exported for backward compatibility
__all__ = ["JudgeVote", "VoteResult", "IterationRecord"]


def _write_hard_block_result(output_dir: Path, vote: JudgeVote, guard_result: Any) -> None:
    """HARD_BLOCK 时写入 _judge_result.json，让 cmd_approve 能读到并拦截。"""
    from datetime import datetime

    from qualix.json_utils import save_json

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


def _get_dynamic_dim_generator(phase_id: str):
    """返回该 Phase 的动态维度生成器，未注册则返回 None（懒加载避免循环依赖）。

    扩展方式：先对目标 Phase 做回归 audit（找"整体高分但某维度为零"的案例），
    确认存在加权平均稀释问题后，在此添加对应生成器。
    当前仅 Q01 已有回归证据。

    Future extension points（需先有 regression audit 证据才加）：
      "Q03"  -> generate_q03_dynamic_dimensions  (failure_mode 域分析)
      "Q05a" -> generate_q05a_dynamic_dimensions (断言强度域)
      "Q05b" -> generate_q05b_dynamic_dimensions (断言强度域)
      "Q06"  -> generate_q06_dynamic_dimensions  (COVERED 准确率域)
    """
    if phase_id == "Q01":
        from qualix.quality.judge.dynamic_rubric import generate_dynamic_dimensions

        return generate_dynamic_dimensions
    return None


def _run_single_judge(
    output_dir: Path,
    report_path: Path,
    rubric: str,
    model: str,
    fallback: str,
    warning_override: str | None = None,
) -> JudgeVote | None:
    """Thin wrapper: dispatches JudgeRunner in an isolated subprocess for context isolation.

    Runs judge_runner_subprocess as a child process so that Worker reasoning traces
    (e.g. <thinking> blocks) are never present in the Judge's memory space.

    自动从 report_path 推 project_id/phase_id，通过 subprocess 内部的
    _get_dynamic_dim_generator 注入动态维度，让门限机制生效。
    当前仅 Q01 注册了生成器；其他 Phase 待 regression audit 后按需扩展。
    """
    import json
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    internal_dir = Path(output_dir) / "_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)

    uid = uuid4().hex[:8]
    input_path = internal_dir / f"judge_input_{uid}.json"
    output_path = internal_dir / f"judge_output_{uid}.json"

    input_data: dict[str, Any] = {
        "report_path": str(report_path),
        "output_dir": str(output_dir),
        "model": model,
        "fallback": fallback,
        "rubric": rubric,
        "warning_override": warning_override,
        "rubric_dims": None,  # subprocess re-derives via _get_dynamic_dim_generator
    }

    try:
        input_path.write_text(json.dumps(input_data, ensure_ascii=False), encoding="utf-8")

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "qualix.agents.judge_runner_subprocess",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                timeout=120,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            log.error("Judge subprocess timed out for model=%s", model)
            raise TimeoutError("Judge subprocess timed out") from exc

        if proc.returncode != 0:
            log.error("Judge subprocess failed for model=%s: %s", model, proc.stderr[:400])
            raise RuntimeError(f"Judge subprocess failed: {proc.stderr[:200]}")

        try:
            raw = output_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.error(
                "Judge subprocess output file unreadable for model=%s (subprocess stderr: %s): %s",
                model, proc.stderr[:200], exc,
            )
            raise RuntimeError("Judge subprocess output file missing or unreadable") from exc

        try:
            result_dict: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error(
                "Judge subprocess wrote malformed JSON for model=%s (first 200 chars: %s)",
                model, raw[:200],
            )
            raise RuntimeError("Judge subprocess produced malformed JSON") from exc
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)

    if result_dict.get("health") == "INFRA_FAILURE":
        log.warning("JudgeRunner returned INFRA_FAILURE for model=%s", model)
        return None

    return JudgeVote(
        model=result_dict["model"],
        scores={d["id"]: d.get("score", 0) for d in result_dict.get("dimensions", [])},
        overall=result_dict["overall_score"],
        verdict=result_dict["verdict"],
        issues=result_dict.get("issues", []),
        duration=result_dict.get("duration", 0.0),
        raw_output=result_dict.get("raw_output", ""),
        health=result_dict.get("health", "HEALTHY"),
        token_usage=result_dict.get("token_usage", {}),
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
        try:
            vote = _run_single_judge(output_dir, report_path, rubric, model, fallback)
        except Exception as exc:
            log.warning("Secondary judge %s failed in fallback path: %s", model, exc)
            vote = None
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
    fallback: str | None = None,
    force_secondary: bool = False,
) -> VoteResult:
    """Primary Judge + Secondary Validation 策略.

    1. 先用第一个模型（primary）独立评审
    2. 如果 primary 分数在边界区间（pass_threshold ± 0.5），启动 secondary 验证
    3. 如果 primary 分数明确 PASS 或 FAIL，直接采纳，不浪费 secondary 调用
    """
    from qualix.agents.judge_vote_guards import apply_overcorrection_guard, apply_rationalization_guard
    from qualix.constants import JUDGE_PASS_THRESHOLD, JUDGE_PASS_WITH_CONCERNS_DELTA

    unique_models = list(dict.fromkeys(models))
    if not unique_models:
        return VoteResult(votes=[], consensus="FAIL", avg_score=0, disagreements=["No judge models configured"])

    primary_model = unique_models[0]
    secondary_models = unique_models[1:]

    # Guard telemetry 目标路径（与 phase 内部 _guardrail_results.json 同位）
    try:
        _tel_phase_id = report_path.parent.name
    except (AttributeError, IndexError):
        _tel_phase_id = ""
    from pathlib import Path as _Path

    _tel_internal_dir = _Path(output_dir) / "_internal"

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
    rat_result = apply_rationalization_guard(
        primary_vote=primary_vote,
        run_single_judge=_run_single_judge,
        write_hard_block_result=_write_hard_block_result,
        output_dir=output_dir,
        report_path=report_path,
        rubric=rubric,
        primary_model=primary_model,
        fallback=fallback,
        internal_dir=_tel_internal_dir,
        phase_id=_tel_phase_id,
    )
    if rat_result is None:
        # HARD_BLOCK: _write_hard_block_result already persisted the block payload
        return None
    primary_vote = rat_result

    # Guard: Anti-Overcorrection check on primary vote
    primary_vote = apply_overcorrection_guard(
        primary_vote=primary_vote,
        run_single_judge=_run_single_judge,
        output_dir=output_dir,
        report_path=report_path,
        rubric=rubric,
        primary_model=primary_model,
        fallback=fallback,
        internal_dir=_tel_internal_dir,
        phase_id=_tel_phase_id,
    )

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
                model_name = futures[future]
                try:
                    vote = future.result()
                except Exception as exc:
                    log.warning("Secondary judge %s failed (subprocess): %s", model_name, exc)
                    vote = None
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
