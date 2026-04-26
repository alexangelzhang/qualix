"""Phase 状态机：管理 Phase 生命周期.

借鉴 VAF 的三步执行模式：
  execute  → 启动 Phase，状态 not_started → in_progress
  finalize → 校验产物，状态 in_progress → pending_review
  approve  → 人工确认，状态 pending_review → approved

状态持久化到 output/<project_id>/state.json。

注意：PHASE_DEFS / PHASE_ORDER 定义在 core/phase_registry.py（Domain 层），
本模块通过 import 引用并 re-export 保持向后兼容。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, Field

from dqg.constants import LEGACY_PHASE_ID_MAP

# Domain 层 Phase 定义（re-export 保持向后兼容）
from dqg.core.phase_registry import PHASE_DEFS, PHASE_ORDER
from dqg.json_utils import load_json_strict, save_json


class PhaseStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SKIPPED = "skipped"


class PhaseState(BaseModel):
    """单个 Phase 的状态."""

    status: PhaseStatus = PhaseStatus.NOT_STARTED
    run_status: str | None = None  # RunStatus value: ok/timeout/adapter_crashed/parse_failed/tainted
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    duration_seconds: float | None = None
    comment: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    # Judge 评审结果
    judge_score: float | None = None
    judge_dimensions: dict[str, float] = Field(default_factory=dict)
    judge_passed: bool | None = None
    judged_at: str | None = None


class ProjectState(BaseModel):
    """项目级状态，持久化到 JSON."""

    version: str = "1.0"
    project_id: str
    profile_id: str = "java-ddd-tmf"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    phases: dict[str, PhaseState] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """确保所有 Phase 都有状态条目."""
        for phase_id in PHASE_ORDER:
            if phase_id not in self.phases:
                self.phases[phase_id] = PhaseState()


def phase_dir(output_dir: Path, project_id: str, phase_def: dict) -> Path:
    """统一构造 Phase 输出目录: output/<project_id>/<dir_suffix>/."""
    return output_dir / project_id / phase_def["dir_suffix"]


def phase_dir_by_id(output_dir: Path, project_id: str, phase_id: str) -> Path:
    """按 phase_id 构造 Phase 输出目录."""
    pd = PHASE_DEFS.get(phase_id)
    if not pd:
        raise ValueError(f"未知的 Phase: {phase_id}")
    return phase_dir(output_dir, project_id, pd)


def ingest_dir(output_dir: Path, project_id: str, phase_def: dict) -> Path:
    """飞书 ingest 产物子目录: output/<project_id>/<dir_suffix>/ingest/."""
    return phase_dir(output_dir, project_id, phase_def) / "ingest"


def internal_dir(output_dir: Path, project_id: str, phase_def: dict) -> Path:
    """过程文件子目录: output/<project_id>/<dir_suffix>/_internal/."""
    return phase_dir(output_dir, project_id, phase_def) / "_internal"


def _state_path(output_dir: Path, project_id: str) -> Path:
    return output_dir / project_id / "state.json"


def load_state(output_dir: Path, project_id: str) -> ProjectState:
    """加载项目状态，不存在则创建.

    自动迁移旧 Phase ID（A/A.3/A.5/A.6/B/C/D → Q01-Q07）。
    """
    path = _state_path(output_dir, project_id)
    if path.exists():
        data = load_json_strict(path)
        # 向后兼容：迁移旧 Phase ID
        phases = data.get("phases", {})
        migrated = False
        for old_id, new_id in LEGACY_PHASE_ID_MAP.items():
            if old_id in phases and new_id not in phases:
                phases[new_id] = phases.pop(old_id)
                migrated = True
        if migrated:
            data["phases"] = phases
        return ProjectState.model_validate(data)
    return ProjectState(project_id=project_id)


def save_state(output_dir: Path, state: ProjectState) -> Path:
    """持久化项目状态."""
    state.updated_at = datetime.now().isoformat()
    path = _state_path(output_dir, state.project_id)
    save_json(path, state.model_dump())
    return path


def check_gate(state: ProjectState, phase_id: str) -> list[str]:
    """检查 Phase 的前置依赖是否满足.

    Returns:
        []: gate 通过
        ["error1", ...]: 未满足的依赖
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return [f"未知的 Phase: {phase_id}"]

    errors: list[str] = []
    for dep_id in phase_def["depends_on"]:
        dep_state = state.phases.get(dep_id)
        if not dep_state or dep_state.status not in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED):
            errors.append(f"前置 Phase {dep_id} 未完成（当前状态: {dep_state.status if dep_state else 'missing'}）")

    current = state.phases.get(phase_id)
    if current and current.status == PhaseStatus.APPROVED:
        errors.append(f"Phase {phase_id} 已经 approved，无需重复执行")

    return errors


def execute_phase(state: ProjectState, phase_id: str) -> list[str]:
    """启动 Phase：not_started → in_progress.

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    gate_errors = check_gate(state, phase_id)
    if gate_errors:
        return gate_errors

    phase_state = state.phases[phase_id]
    if phase_state.status not in (PhaseStatus.NOT_STARTED, PhaseStatus.SKIPPED):
        return [f"Phase {phase_id} 当前状态为 {phase_state.status}，只能从 not_started 启动"]

    phase_state.status = PhaseStatus.IN_PROGRESS
    phase_state.started_at = datetime.now().isoformat()
    phase_state.validation_errors = []
    return []


def finalize_phase(
    state: ProjectState,
    phase_id: str,
    validation_errors: list[str] | None = None,
) -> list[str]:
    """完成 Phase 执行，校验产物：in_progress → pending_review.

    Also allows re-finalize from pending_review (e.g. after fixing missing
    artifacts like _critique.json).  Re-finalize resets the phase back to
    in_progress first so that gate_verdict is regenerated.

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state or phase_state.status not in (PhaseStatus.IN_PROGRESS, PhaseStatus.PENDING_REVIEW):
        return [
            f"Phase {phase_id} 当前状态为 {phase_state.status if phase_state else 'missing'}，只能从 in_progress 或 pending_review finalize"
        ]

    # Re-finalize: 从 pending_review 回退到 in_progress 再走正常流程
    if phase_state.status == PhaseStatus.PENDING_REVIEW:
        phase_state.status = PhaseStatus.IN_PROGRESS

    phase_state.finished_at = datetime.now().isoformat()

    if phase_state.started_at:
        start = datetime.fromisoformat(phase_state.started_at)
        end = datetime.fromisoformat(phase_state.finished_at)
        phase_state.duration_seconds = (end - start).total_seconds()

    if validation_errors:
        phase_state.validation_errors = validation_errors
        # 有校验错误仍然可以进入 pending_review，但会标记
    phase_state.status = PhaseStatus.PENDING_REVIEW
    return []


def approve_phase(state: ProjectState, phase_id: str, comment: str = "") -> list[str]:
    """人工确认：pending_review → approved.

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state or phase_state.status != PhaseStatus.PENDING_REVIEW:
        return [
            f"Phase {phase_id} 当前状态为 {phase_state.status if phase_state else 'missing'}，只能从 pending_review approve"
        ]

    phase_state.status = PhaseStatus.APPROVED
    phase_state.approved_at = datetime.now().isoformat()
    phase_state.comment = comment
    return []


def skip_phase(state: ProjectState, phase_id: str, comment: str = "") -> list[str]:
    """跳过 Phase.

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state:
        return [f"未知的 Phase: {phase_id}"]
    if phase_state.status == PhaseStatus.APPROVED:
        return [f"Phase {phase_id} 已 approved，无法跳过"]

    phase_state.status = PhaseStatus.SKIPPED
    phase_state.comment = comment
    return []


def reset_phase(state: ProjectState, phase_id: str) -> list[str]:
    """重置 Phase 到 not_started 状态（允许重新执行）.

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state:
        return [f"未知的 Phase: {phase_id}"]
    if phase_state.status == PhaseStatus.NOT_STARTED:
        return [f"Phase {phase_id} 已经是 not_started 状态"]

    phase_state.status = PhaseStatus.NOT_STARTED
    phase_state.started_at = None
    phase_state.finished_at = None
    phase_state.validation_errors = []
    phase_state.comment = ""
    return []


def get_available_phases(state: ProjectState) -> list[str]:
    """获取当前可执行的 Phase 列表（gate 通过 + 未完成）."""
    available = []
    for phase_id in PHASE_ORDER:
        phase_state = state.phases.get(phase_id)
        if not phase_state or phase_state.status in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED):
            continue
        if not check_gate(state, phase_id):
            available.append(phase_id)
    return available


def record_judge_score(
    state: ProjectState,
    phase_id: str,
    overall_score: float,
    dimension_scores: dict[str, float],
    pass_threshold: float = 3.5,
    judged_at: str | None = None,
) -> None:
    """将 judge 评审结果写入 PhaseState.

    如果 run_status 为 infra failure（timeout/adapter_crashed），
    跳过评分记录，避免 infra 故障污染质量指标。
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state:
        return
    # infra failure 不计入质量评分
    if phase_state.run_status in ("timeout", "adapter_crashed"):
        return
    phase_state.judge_score = overall_score
    phase_state.judge_dimensions = dimension_scores
    phase_state.judge_passed = overall_score >= pass_threshold
    phase_state.judged_at = judged_at or datetime.now().isoformat()


def get_parallel_groups(state: ProjectState) -> list[list[str]]:
    """获取可并行执行的 Phase 分组."""
    available = get_available_phases(state)
    if not available:
        return []

    groups: list[list[str]] = []
    used: set[str] = set()

    for phase_id in available:
        if phase_id in used:
            continue
        phase_def = PHASE_DEFS[phase_id]
        group = [phase_id]
        used.add(phase_id)

        for parallel_id in phase_def["parallel_with"]:
            if parallel_id in available and parallel_id not in used:
                group.append(parallel_id)
                used.add(parallel_id)

        groups.append(group)

    return groups
