"""Phase 状态机：管理 Phase 生命周期.

借鉴 VAF 的三步执行模式：
  execute  → 启动 Phase，状态 not_started → in_progress
  finalize → 校验产物，状态 in_progress → pending_review
  approve  → 人工确认，状态 pending_review → approved

状态持久化到 output/<project_id>/state.json。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, Field

from dqg.json_utils import load_json_strict, save_json


class PhaseStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SKIPPED = "skipped"


# Phase 定义
PHASE_DEFS: dict[str, dict] = {
    "A": {
        "name": "需求结构化",
        "dir_suffix": "phaseA",
        "skill": "skills/requirement-structuring.md",
        "depends_on": [],
        "parallel_with": [],
        "required_inputs": [
            {"key": "prd", "label": "需求文档", "prompt": "PRD 路径或飞书链接", "required": True},
        ],
        "optional_inputs": [
            {"key": "images", "label": "补充图片目录", "prompt": "图片/原型图目录路径（没有直接回车跳过）"},
        ],
        "deliverables": [
            "phase_a_report.md — REQ/BR/SE + GAP + OPEN 结构化报告",
            "phase_a_structured.json — 机器可读的结构化产物",
        ],
        "approve_checklist": [
            "所有需求点已结构化为 REQ/BR",
            "关键语义已显式化为 SE",
            "缺口已记录为 GAP，待确认项已记录为 OPEN",
        ],
    },
    "A.3": {
        "name": "技术方案生成",
        "dir_suffix": "phaseA3",
        "skill": "skills/tech-design-generation.md",
        "depends_on": ["A"],
        "parallel_with": [],
        "skippable": True,
        "skip_condition": "已有技术方案文档时可跳过，直接进入 A.6 质量评审",
        "required_inputs": [],
        "optional_inputs": [
            {"key": "existing_tech_design", "label": "已有技术方案", "prompt": "如已有技术方案文档，提供路径或飞书链接（提供则跳过生成，直接进入评审）"},
            {"key": "code_repo", "label": "代码仓库", "prompt": "现有代码仓库路径，用于理解现有架构（没有直接回车跳过）"},
            {"key": "knowledge_base", "label": "架构规范/知识库", "prompt": "架构规范或知识库路径（没有直接回车跳过）"},
        ],
        "deliverables": [
            "tech_design.md — 技术方案文档（架构设计 + 接口设计 + 数据模型 + 异常处理）",
            "phase_a3_structured.json — 结构化技术方案",
        ],
        "approve_checklist": [
            "业务需求到技术方案的映射完整（每条 REQ/BR 有对应设计）",
            "架构设计符合 DDD + TMF 规范",
            "接口设计完整（含入参/出参/异常码/幂等性）",
            "数据模型设计合理（含索引/约束/扩展性）",
            "异常处理和边界条件已覆盖",
            "性能和扩展性已考虑",
        ],
    },
    "A.6": {
        "name": "技术方案质量评审",
        "dir_suffix": "phaseA6",
        "skill": "skills/tech-quality-review.md",
        "depends_on": ["A.3"],
        "parallel_with": [],
        "required_inputs": [
            {"key": "tech_design", "label": "技术方案文档", "prompt": "技术方案路径或飞书链接（A.3 跳过时必填）", "required": True},
        ],
        "optional_inputs": [
            {"key": "code_repo", "label": "代码仓库(feature分支)", "prompt": "代码仓库路径，用于追踪改动功能点的完整 TMF 链路（没有直接回车跳过）"},
            {"key": "feature_branch", "label": "feature 分支名", "prompt": "要分析的 feature 分支名（没有直接回车跳过）"},
        ],
        "deliverables": [
            "tech_design_quality_review.md — 质量评审报告（含调用链路图）",
            "phase_a6_structured.json — 结构化问题清单",
        ],
        "approve_checklist": [
            "架构/接口/数据/异常/性能五个维度已逐项检查",
            "改动功能点的完整 TMF 链路已梳理",
            "Failure Mode 分析已完成",
            "无 CRITICAL_GAP",
        ],
    },
    "A.5": {
        "name": "技术方案覆盖度审计",
        "dir_suffix": "phaseA5",
        "skill": "skills/tech-coverage-audit.md",
        "depends_on": ["A.6"],
        "parallel_with": [],
        "required_inputs": [
            {"key": "tech_design", "label": "技术方案文档", "prompt": "技术方案路径或飞书链接（多个用逗号分隔）", "required": True},
        ],
        "optional_inputs": [
            {"key": "code_repo", "label": "代码仓库(master分支)", "prompt": "代码仓库路径，用于扫描已有实现和 TMF 链路（没有直接回车跳过）"},
            {"key": "knowledge_base", "label": "知识库", "prompt": "知识库路径或飞书链接（没有直接回车跳过）"},
        ],
        "deliverables": [
            "tech_design_coverage_review.md — 覆盖度审计报告",
            "phase_a5_structured.json — 结构化覆盖矩阵",
        ],
        "approve_checklist": [
            "每条 REQ/SE 都已标注覆盖状态",
            "GAP/OPEN 闭环状态已检查",
            "反向审计已完成（NEW_DESIGN + NOT_IN_SCOPE）",
        ],
    },
    "B": {
        "name": "单测生成",
        "dir_suffix": "phaseB",
        "skill": "skills/unit-test-generation.md",
        "depends_on": ["A"],
        "parallel_with": [],
        "required_inputs": [
            {"key": "code_repo", "label": "代码仓库", "prompt": "代码仓库路径（本地路径或 Git URL）", "required": True},
            {"key": "target_modules", "label": "目标模块", "prompt": "要生成单测的模块/类路径（多个用逗号分隔）", "required": True},
        ],
        "optional_inputs": [],
        "deliverables": [
            "eut_matrix.md — EUT 测试大纲",
            "phase_b_structured.json — 结构化 EUT 矩阵",
            "生成的单测代码文件",
        ],
        "approve_checklist": [
            "EUT 矩阵覆盖了所有 REQ/BR/SE",
            "单测代码使用强断言（非仅执行流程）",
            "异常路径有对应测试",
        ],
    },
    "C": {
        "name": "单测覆盖审计",
        "dir_suffix": "phaseC",
        "skill": "skills/unit-test-audit.md",
        "depends_on": ["A"],
        "parallel_with": [],
        "required_inputs": [
            {"key": "code_repo", "label": "代码仓库", "prompt": "代码仓库路径（含单测代码）", "required": True},
            {"key": "coverage_report", "label": "覆盖率报告", "prompt": "JaCoCo/覆盖率报告路径（没有直接回车跳过）", "required": False},
        ],
        "optional_inputs": [],
        "deliverables": [
            "ut_audit_report.md — 单测审计报告",
            "phase_c_structured.json — 结构化审计结果",
        ],
        "approve_checklist": [
            "覆盖率门禁达标（line >= 80%, branch >= 80%）",
            "T1 核心异常分支 100% 覆盖",
            "无 WRONG_TARGET 问题",
        ],
    },
    "D": {
        "name": "代码评审",
        "dir_suffix": "phaseD",
        "skill": "skills/code-review.md",
        "depends_on": ["A"],
        "parallel_with": [],
        "required_inputs": [
            {"key": "code_repo", "label": "代码仓库", "prompt": "代码仓库路径", "required": True},
            {"key": "branch", "label": "评审分支", "prompt": "要评审的分支名（如 feature/xxx）", "required": True},
            {"key": "base_branch", "label": "基线分支", "prompt": "基线分支名（默认 master）", "required": False},
        ],
        "optional_inputs": [],
        "deliverables": [
            "review_report.md — 代码评审报告",
            "phase_d_structured.json — 结构化评审发现",
        ],
        "approve_checklist": [
            "所有 BLOCKER 级问题已修复",
            "REQ/BR/SEM → CODE/TEST 覆盖缺口已确认",
            "无未确认的自动修改",
        ],
    },
}

PHASE_ORDER = ["A", "A.3", "A.6", "A.5", "B", "C", "D"]


class PhaseState(BaseModel):
    """单个 Phase 的状态."""

    status: PhaseStatus = PhaseStatus.NOT_STARTED
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
    """加载项目状态，不存在则创建."""
    path = _state_path(output_dir, project_id)
    if path.exists():
        data = load_json_strict(path)
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

    Returns:
        []: 成功
        ["error1", ...]: 失败原因
    """
    phase_state = state.phases.get(phase_id)
    if not phase_state or phase_state.status != PhaseStatus.IN_PROGRESS:
        return [f"Phase {phase_id} 当前状态为 {phase_state.status if phase_state else 'missing'}，只能从 in_progress finalize"]

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
        return [f"Phase {phase_id} 当前状态为 {phase_state.status if phase_state else 'missing'}，只能从 pending_review approve"]

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
    """将 judge 评审结果写入 PhaseState."""
    phase_state = state.phases.get(phase_id)
    if not phase_state:
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
