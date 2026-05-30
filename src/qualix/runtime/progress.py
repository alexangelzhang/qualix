"""跨 session 进度文件：每个 Phase finalize 后自动生成 _progress.json.

记录执行摘要（做了什么、发现了什么、关键数字、下一步建议），
供下一个 session 快速 orient，解决"每个新 context window 零记忆"问题。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from qualix.core.state_machine import (
    PHASE_DEFS,
    PHASE_ORDER,
    PhaseStatus,
    ProjectState,
    load_state,
)
from qualix.core.state_machine import (
    internal_dir as _internal_dir,
)
from qualix.core.state_machine import (
    phase_dir as _phase_dir,
)
from qualix.json_utils import load_json, save_json
from qualix.log import get_logger
from qualix.text_utils import STRUCTURED_JSON_MAP

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


def generate_phase_progress(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """生成单个 Phase 的进度摘要.

    Returns:
        进度数据，包含执行摘要、关键发现、数字指标、下一步建议
    """
    state = load_state(output_dir, project_id)
    ps = state.phases.get(phase_id)
    if not ps:
        return {}

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return {}

    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)

    progress: dict[str, Any] = {
        "phase_id": phase_id,
        "phase_name": phase_def["name"],
        "status": ps.status.value,
        "started_at": ps.started_at,
        "finished_at": ps.finished_at,
        "duration_seconds": ps.duration_seconds,
        "generated_at": datetime.now().isoformat(),
    }

    # 关键数字：从结构化 JSON 提取
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        structured_path = pd / json_file
        if structured_path.exists():
            data = load_json(structured_path)
            if data:
                progress["artifact_counts"] = _count_artifacts(data, phase_id)

    # 校验问题
    if ps.validation_errors:
        progress["validation_issues"] = len(ps.validation_errors)
        progress["top_issues"] = ps.validation_errors[:3]

    # Judge 评分
    if ps.judge_score is not None:
        progress["judge_score"] = ps.judge_score
        progress["judge_passed"] = ps.judge_passed

    # 性能指标
    perf_path = int_dir / "_perf_metrics.json"
    if perf_path.exists():
        perf = load_json(perf_path)
        if perf:
            progress["token_estimate"] = perf.get("total_token_estimate")

    # 下一步建议
    progress["next_steps"] = _suggest_next_steps(state, phase_id)

    return progress


def write_phase_progress(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """生成并写入 Phase 进度文件.

    Returns:
        写入的文件路径
    """
    progress = generate_phase_progress(output_dir, project_id, phase_id)
    if not progress:
        return None

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)
    path = int_dir / "_progress.json"
    save_json(path, progress)
    return path


def generate_project_progress(
    output_dir: Path,
    project_id: str,
) -> dict[str, Any]:
    """生成项目级进度摘要，聚合所有 Phase.

    供 session startup 时快速了解全局状态。
    """
    state = load_state(output_dir, project_id)

    phases_summary: list[dict[str, Any]] = []
    for pid in PHASE_ORDER:
        ps = state.phases.get(pid)
        if not ps:
            continue
        entry: dict[str, Any] = {
            "phase_id": pid,
            "name": PHASE_DEFS[pid]["name"],
            "status": ps.status.value,
        }
        if ps.duration_seconds:
            entry["duration_seconds"] = ps.duration_seconds
        if ps.judge_score is not None:
            entry["judge_score"] = ps.judge_score
        phases_summary.append(entry)

    completed = [p for p in phases_summary if p["status"] in ("approved", "skipped")]
    in_progress = [p for p in phases_summary if p["status"] == "in_progress"]
    pending = [p for p in phases_summary if p["status"] in ("not_started", "pending_review")]

    return {
        "project_id": project_id,
        "profile_id": state.profile_id,
        "generated_at": datetime.now().isoformat(),
        "overall": {
            "total_phases": len(phases_summary),
            "completed": len(completed),
            "in_progress": len(in_progress),
            "pending": len(pending),
        },
        "phases": phases_summary,
        "next_actions": _suggest_project_next(state),
    }


def write_project_progress(output_dir: Path, project_id: str) -> Path:
    """写入项目级进度文件."""
    progress = generate_project_progress(output_dir, project_id)
    path = output_dir / project_id / "_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, progress)
    return path


def _count_artifacts(data: dict[str, Any], phase_id: str) -> dict[str, int]:
    """从结构化 JSON 统计关键产物数量."""
    counts: dict[str, int] = {}
    count_fields = {
        "Q01": ["requirements", "semantic_expectations", "gaps", "open_items"],
        "Q04": ["req_coverage", "se_coverage", "gap_closure"],
        "Q03": ["issues", "failure_modes"],
        "Q05": ["eut_items"],
        "Q05a": ["eut_items"],
        "Q05b": ["tasks"],
        "Q06": ["audit_items"],
        "Q07": ["findings"],
    }
    for field in count_fields.get(phase_id, []):
        items = data.get(field, [])
        if isinstance(items, list):
            counts[field] = len(items)
    return counts


def _suggest_next_steps(state: ProjectState, phase_id: str) -> list[str]:
    """根据当前 Phase 状态建议下一步."""
    ps = state.phases.get(phase_id)
    if not ps:
        return []

    steps: list[str] = []
    if ps.status == PhaseStatus.IN_PROGRESS:
        steps.append(f"Complete Phase {phase_id} execution and run finalize")
    elif ps.status == PhaseStatus.PENDING_REVIEW:
        if ps.judge_score is not None and not ps.judge_passed:
            steps.append(f"Phase {phase_id} Judge score {ps.judge_score:.1f}/5 below threshold, consider revision")
        steps.append(f"Review and approve Phase {phase_id}")
    elif ps.status == PhaseStatus.APPROVED:
        # 找下游 Phase
        for pid in PHASE_ORDER:
            dep_def = PHASE_DEFS.get(pid, {})
            if phase_id in dep_def.get("depends_on", []):
                dep_ps = state.phases.get(pid)
                if dep_ps and dep_ps.status == PhaseStatus.NOT_STARTED:
                    steps.append(f"Execute downstream Phase {pid}({PHASE_DEFS[pid]['name']})")
    return steps


def _suggest_project_next(state: ProjectState) -> list[str]:
    """项目级下一步建议."""
    from qualix.core.state_machine import get_available_phases

    available = get_available_phases(state)
    if not available:
        all_done = all(state.phases[pid].status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED) for pid in PHASE_ORDER)
        if all_done:
            return ["All phases completed. Project ready for final review."]
        return ["No phases available. Check blocked dependencies."]

    return [f"Execute Phase {pid}({PHASE_DEFS[pid]['name']})" for pid in available]
