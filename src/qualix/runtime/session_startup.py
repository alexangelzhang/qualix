"""Session startup protocol：标准化的跨 session 启动序列.

解决"每个新 context window 零记忆"问题。
启动时自动读取 state/progress/reasoning log，输出 orientation summary。
"""

from __future__ import annotations

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
from qualix.json_utils import load_json
from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


def session_startup(
    output_dir: Path,
    project_id: str,
) -> dict[str, Any]:
    """标准化启动序列：读 state → 读 progress → 读上次 reasoning log → 输出 orientation.

    Returns:
        Orientation summary，包含项目状态、最近进展、下一步建议
    """
    state = load_state(output_dir, project_id)

    orientation: dict[str, Any] = {
        "project_id": project_id,
        "profile_id": state.profile_id,
    }

    # 1. 项目级进度
    project_progress_path = output_dir / project_id / "_progress.json"
    if project_progress_path.exists():
        orientation["project_progress"] = load_json(project_progress_path)
    else:
        # 没有 progress 文件，从 state 构建基本信息
        orientation["project_progress"] = _build_basic_progress(state)

    # 2. 最近完成的 Phase 的进度详情
    last_phase = _find_last_active_phase(state)
    if last_phase:
        orientation["last_phase"] = last_phase
        phase_def = PHASE_DEFS.get(last_phase)
        if phase_def:
            int_dir = _internal_dir(output_dir, project_id, phase_def)
            # 读 Phase 级 progress
            phase_progress_path = int_dir / "_progress.json"
            if phase_progress_path.exists():
                orientation["last_phase_progress"] = load_json(phase_progress_path)
            # 读最近的 reasoning log 摘要（前 500 字符）
            reasoning_path = int_dir / "_reasoning_log.md"
            if not reasoning_path.exists():
                reasoning_path = _phase_dir(output_dir, project_id, phase_def) / "_reasoning_log.md"
            if reasoning_path.exists():
                text = reasoning_path.read_text(encoding="utf-8").strip()
                orientation["last_reasoning_excerpt"] = text[:500] + ("..." if len(text) > 500 else "")

    # 3. 下一步建议
    orientation["next_actions"] = _compute_next_actions(state)

    # 4. 未完成的 task（如果有 task store）
    orientation["resumable_tasks"] = _find_resumable_tasks(output_dir, project_id)

    return orientation


def format_orientation(orientation: dict[str, Any]) -> str:
    """将 orientation 格式化为人类可读的 Markdown."""
    lines: list[str] = []
    lines.append(f"# Session Startup — {orientation['project_id']}")
    lines.append(f"Profile: {orientation.get('profile_id', 'unknown')}")
    lines.append("")

    # 项目进度
    progress = orientation.get("project_progress", {})
    overall = progress.get("overall", {})
    if overall:
        total = overall.get("total_phases", 0)
        completed = overall.get("completed", 0)
        lines.append(f"## Progress: {completed}/{total} phases completed")
        lines.append("")

    phases = progress.get("phases", [])
    if phases:
        for p in phases:
            status_icon = {
                "approved": "+",
                "skipped": "~",
                "in_progress": ">",
                "pending_review": "?",
                "not_started": " ",
            }.get(p["status"], " ")
            score_str = f" (Judge: {p['judge_score']:.1f})" if "judge_score" in p else ""
            lines.append(f"  [{status_icon}] {p['phase_id']} {p['name']}: {p['status']}{score_str}")
        lines.append("")

    # 最近进展
    last_progress = orientation.get("last_phase_progress")
    if last_progress:
        lines.append(f"## Last Phase: {last_progress.get('phase_id', '')} ({last_progress.get('phase_name', '')})")
        counts = last_progress.get("artifact_counts", {})
        if counts:
            lines.append(f"  Artifacts: {counts}")
        if last_progress.get("judge_score") is not None:
            lines.append(f"  Judge: {last_progress['judge_score']:.1f}/5")
        lines.append("")

    # Reasoning 摘要
    excerpt = orientation.get("last_reasoning_excerpt")
    if excerpt:
        lines.append("## Last Reasoning (excerpt)")
        lines.append(excerpt)
        lines.append("")

    # 可恢复任务
    resumable = orientation.get("resumable_tasks", [])
    if resumable:
        lines.append(f"## Resumable Tasks: {len(resumable)}")
        for t in resumable:
            lines.append(f"  - {t['task_id']} ({t['task_type']}) phase={t.get('phase_id', '')}")
        lines.append("")

    # 下一步
    actions = orientation.get("next_actions", [])
    if actions:
        lines.append("## Next Actions")
        for a in actions:
            lines.append(f"  - {a}")

    return "\n".join(lines)


def _build_basic_progress(state: ProjectState) -> dict[str, Any]:
    """从 state 构建基本进度信息（没有 _progress.json 时的 fallback）."""
    phases = []
    for pid in PHASE_ORDER:
        ps = state.phases.get(pid)
        if ps:
            entry: dict[str, Any] = {
                "phase_id": pid,
                "name": PHASE_DEFS[pid]["name"],
                "status": ps.status.value,
            }
            if ps.judge_score is not None:
                entry["judge_score"] = ps.judge_score
            phases.append(entry)

    completed = sum(1 for p in phases if p["status"] in ("approved", "skipped"))
    return {
        "overall": {
            "total_phases": len(phases),
            "completed": completed,
            "in_progress": sum(1 for p in phases if p["status"] == "in_progress"),
            "pending": sum(1 for p in phases if p["status"] in ("not_started", "pending_review")),
        },
        "phases": phases,
    }


def _find_last_active_phase(state: ProjectState) -> str | None:
    """找到最近活跃的 Phase（按时间倒序）."""
    candidates: list[tuple[str, str]] = []
    for pid in PHASE_ORDER:
        ps = state.phases.get(pid)
        if not ps:
            continue
        ts = ps.finished_at or ps.started_at
        if ts and ps.status != PhaseStatus.NOT_STARTED:
            candidates.append((ts, pid))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _compute_next_actions(state: ProjectState) -> list[str]:
    """计算下一步建议."""
    from qualix.core.state_machine import get_available_phases

    actions: list[str] = []

    # 检查是否有 pending_review 的 Phase
    for pid in PHASE_ORDER:
        ps = state.phases.get(pid)
        if ps and ps.status == PhaseStatus.PENDING_REVIEW:
            actions.append(f"Review and approve Phase {pid}({PHASE_DEFS[pid]['name']})")

    # 检查可执行的 Phase
    available = get_available_phases(state)
    for pid in available:
        if state.phases[pid].status == PhaseStatus.NOT_STARTED:
            actions.append(f"Execute Phase {pid}({PHASE_DEFS[pid]['name']})")

    if not actions:
        all_done = all(state.phases[pid].status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED) for pid in PHASE_ORDER)
        if all_done:
            actions.append("All phases completed. Ready for final project review.")

    return actions


def _find_resumable_tasks(output_dir: Path, project_id: str) -> list[dict[str, Any]]:
    """查找可恢复的 task."""
    try:
        from qualix.runtime.task_store import list_task_runs

        return list_task_runs(output_dir, project_id=project_id, status="running", limit=5)
    except Exception:
        log.warning("Failed to find resumable tasks", exc_info=True)
        return []
