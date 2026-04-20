"""Preflight：adaptive/dag 每轮开始前的预检.

恢复 checkpoint → 读上轮 progress → 跑 smoke verifier → 确认可继续。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)


@dataclass
class PreflightResult:
    """预检结果."""
    can_continue: bool = True
    checks: list[dict[str, str]] = field(default_factory=list)
    resumed_from: str | None = None
    warnings: list[str] = field(default_factory=list)


def run_preflight(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> PreflightResult:
    """执行预检.

    1. 检查上轮 checkpoint 是否存在
    2. 检查产物文件完整性
    3. 检查 schema 合规性
    4. 确认环境可继续
    """
    result = PreflightResult()

    # 1. 检查 checkpoint
    checkpoint = _check_checkpoint(output_dir, project_id, phase_id)
    result.checks.append(checkpoint)
    if checkpoint["status"] == "RESUMED":
        result.resumed_from = checkpoint.get("detail", "")

    # 2. 检查产物文件存在性
    artifact_check = _check_artifacts(output_dir, project_id, phase_id)
    result.checks.append(artifact_check)

    # 3. 检查上游依赖已完成
    dep_check = _check_dependencies(output_dir, project_id, phase_id)
    result.checks.append(dep_check)
    if dep_check["status"] == "FAIL":
        result.can_continue = False

    # 4. 检查 Phase contract 存在
    contract_check = _check_contract(output_dir, project_id, phase_id)
    result.checks.append(contract_check)

    # 汇总
    fail_count = sum(1 for c in result.checks if c["status"] == "FAIL")
    if fail_count > 0:
        result.can_continue = False
        log.warning("Preflight FAIL: Phase %s has %d blocking issues", phase_id, fail_count)
    else:
        log.info("Preflight PASS: Phase %s ready to continue", phase_id)

    return result


def _check_checkpoint(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """检查是否有可恢复的 checkpoint."""
    from dqg.runtime.task_store import get_resumable_task

    task = get_resumable_task(output_dir, project_id=project_id, phase_id=phase_id)
    if task:
        return {
            "name": "checkpoint",
            "status": "RESUMED",
            "detail": f"Found checkpoint: task {task.get('task_id', '?')}, iteration {task.get('iteration', '?')}",
        }
    return {"name": "checkpoint", "status": "PASS", "detail": "No checkpoint (fresh start)"}


def _check_artifacts(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """检查关键产物文件存在性."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    phase_dir = output_dir / project_id / dir_suffix

    if not phase_dir.exists():
        return {"name": "artifacts", "status": "PASS", "detail": "Phase dir not yet created (first run)"}

    int_dir = phase_dir / "_internal"
    expected = ["_upstream_context.md", "_phase_contract.json"]
    missing = [f for f in expected if not (int_dir / f).exists()]

    if missing:
        return {"name": "artifacts", "status": "WARNING", "detail": f"Missing: {', '.join(missing)}"}
    return {"name": "artifacts", "status": "PASS", "detail": "All expected artifacts present"}


def _check_dependencies(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """检查上游依赖 Phase 已完成."""
    from dqg.core.phase_registry import PHASE_DEFS
    from dqg.core.state_machine import PhaseStatus, load_state

    phase_def = PHASE_DEFS.get(phase_id, {})
    deps = phase_def.get("depends_on", [])

    if not deps:
        return {"name": "dependencies", "status": "PASS", "detail": "No dependencies"}

    state = load_state(output_dir, project_id)
    not_done = []
    for dep in deps:
        ps = state.phases.get(dep)
        if ps and ps.status not in (PhaseStatus.APPROVED, PhaseStatus.SKIPPED):
            not_done.append(dep)

    if not_done:
        return {"name": "dependencies", "status": "FAIL", "detail": f"Upstream not done: {', '.join(not_done)}"}
    return {"name": "dependencies", "status": "PASS", "detail": f"All deps done: {', '.join(deps)}"}


def _check_contract(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """检查 Phase contract 是否存在."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    contract_path = output_dir / project_id / dir_suffix / "_internal" / "_phase_contract.json"

    if contract_path.exists():
        return {"name": "contract", "status": "PASS", "detail": "Phase contract exists"}
    return {"name": "contract", "status": "WARNING", "detail": "No phase contract (will be generated on execute)"}
