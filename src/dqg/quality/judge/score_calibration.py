"""DeepEval 评分校准层：Judge 评分一致性检测 + 趋势监控.

不替代 DQG 的 Judge，而是给 Judge 加一个质量保障层：
1. 一致性检测：同一产物用 DeepEval 独立打分，与 DQG Judge 对比
2. 趋势监控：跟踪每个 Phase 的评分趋势，检测通胀/通缩
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

# 评分偏差阈值
SCORE_DRIFT_THRESHOLD = 1.0
TREND_WINDOW = 5
TREND_INFLATION_THRESHOLD = 0.5


def check_score_consistency(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """用 DeepEval 独立评分，与 DQG Judge 结果对比.

    Returns:
        校准结果 dict，或 None
    """
    from .judge import load_judge_result

    judge_result = load_judge_result(output_dir, project_id, phase_id)
    if not judge_result:
        return None

    dqg_score = judge_result.get("overall_score", 0.0)

    from dqg.constants import REPORT_MAP
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    report_file = REPORT_MAP.get(phase_id)
    if not report_file or not (pd / report_file).exists():
        return None

    report_text = (pd / report_file).read_text(encoding="utf-8")
    if len(report_text) > 8000:
        report_text = report_text[:8000] + "\n...(truncated)"

    deepeval_score = _run_deepeval_scoring(phase_id, report_text)
    if deepeval_score is None:
        return None

    drift = abs(dqg_score - deepeval_score)
    consistent = drift <= SCORE_DRIFT_THRESHOLD

    result = {
        "dqg_score": dqg_score,
        "deepeval_score": deepeval_score,
        "drift": round(drift, 2),
        "consistent": consistent,
        "phase_id": phase_id,
        "checked_at": datetime.now().isoformat(),
    }

    if not consistent:
        log.warning(
            "Score drift: Phase %s DQG=%.1f DeepEval=%.1f drift=%.1f",
            phase_id,
            dqg_score,
            deepeval_score,
            drift,
        )

    _save_calibration_result(output_dir, project_id, phase_id, result)
    return result


def check_score_trend(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """检测评分趋势（通胀/通缩）."""
    history = _load_score_history(output_dir, project_id, phase_id)
    if len(history) < TREND_WINDOW * 2:
        return {
            "phase_id": phase_id,
            "recent_scores": [h["score"] for h in history],
            "trend": "insufficient_data",
            "message": f"Need {TREND_WINDOW * 2} scores, have {len(history)}",
        }

    recent = history[-TREND_WINDOW:]
    previous = history[-TREND_WINDOW * 2 : -TREND_WINDOW]

    avg_recent = sum(h["score"] for h in recent) / len(recent)
    avg_previous = sum(h["score"] for h in previous) / len(previous)
    delta = avg_recent - avg_previous

    if delta > TREND_INFLATION_THRESHOLD:
        trend = "inflation"
    elif delta < -TREND_INFLATION_THRESHOLD:
        trend = "deflation"
    else:
        trend = "stable"

    result = {
        "phase_id": phase_id,
        "recent_scores": [round(h["score"], 1) for h in recent],
        "trend": trend,
        "avg_recent": round(avg_recent, 2),
        "avg_previous": round(avg_previous, 2),
        "delta": round(delta, 2),
    }

    if trend != "stable":
        log.warning("Score %s: Phase %s avg %.1f->%.1f", trend, phase_id, avg_previous, avg_recent)

    return result


def _run_deepeval_scoring(phase_id: str, report_text: str) -> float | None:
    """DeepEval 评分已禁用，DQG 内置 Judge/Critique 评审链已足够."""
    return None


def _get_phase_criteria(phase_id: str) -> str:
    """Phase 对应的 DeepEval 评估标准."""
    criteria_map = {
        "Q01": (
            "Check requirement structuring: "
            "1) REQ/BR with specific details 2) SE explicit and verifiable "
            "3) Gaps identified with risk levels 4) No fabricated content"
        ),
        "Q04": (
            "Check coverage audit: "
            "1) COVERED/PARTIAL/MISSING accurately assigned "
            "2) Missing requirements identified 3) Reverse audit done "
            "4) Evidence cited for each judgment"
        ),
        "Q03": (
            "Check quality review: "
            "1) Issues are real with evidence 2) Failure mode analysis done "
            "3) Exception categories reviewed 4) No false positives"
        ),
        "Q05": (
            "Check test generation: "
            "1) EUT covers all SE 2) Strong assertions used "
            "3) Exception paths tested 4) Code compilable"
        ),
        "Q06": (
            "Check test audit: "
            "1) Classifications accurate 2) Weak assertions identified "
            "3) Exception branches covered 4) Realistic test data"
        ),
        "Q07": (
            "Check code review: "
            "1) Findings have evidence 2) Severity appropriate "
            "3) Req-code alignment verified 4) Call chain traced"
        ),
    }
    return criteria_map.get(phase_id, "Assess overall quality, completeness, and accuracy.")


def _save_calibration_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    result: dict[str, Any],
) -> None:
    """保存校准结果."""
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import internal_dir as _internal_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)
    save_json(int_dir / "_score_calibration.json", result)
    _append_score_history(output_dir, project_id, phase_id, result.get("dqg_score", 0))


def _append_score_history(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    score: float,
) -> None:
    """追加评分到历史记录."""
    history_path = output_dir / project_id / "_score_history.json"
    history: dict[str, list] = {}
    if history_path.exists():
        data = load_json(history_path)
        if isinstance(data, dict):
            history = data

    if phase_id not in history:
        history[phase_id] = []

    history[phase_id].append(
        {
            "score": score,
            "timestamp": datetime.now().isoformat(),
        }
    )
    history[phase_id] = history[phase_id][-20:]
    save_json(history_path, history)


def _load_score_history(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, Any]]:
    """加载评分历史."""
    history_path = output_dir / project_id / "_score_history.json"
    if not history_path.exists():
        return []
    data = load_json(history_path)
    if not isinstance(data, dict):
        return []
    return data.get(phase_id, [])
