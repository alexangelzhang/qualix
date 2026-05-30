"""Preflight：adaptive/dag 每轮开始前的预检.

恢复 checkpoint → 读上轮 progress → 上游产物完整性 → 级联失败阻断 → 确认可继续。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

# 上游 run_status 中会级联阻断下游的值
_CASCADE_BLOCK_STATUSES = frozenset({"tainted", "parse_failed"})


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
    3. 检查上游依赖已完成
    4. 检查上游产物完整性（report + structured JSON 非空）
    5. 级联失败阻断（上游 run_status 为 tainted/parse_failed 时阻断）
    6. 检查 Phase contract 存在
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

    # 4. 上游产物完整性检查
    upstream_artifact_check = _check_upstream_artifacts(output_dir, project_id, phase_id)
    result.checks.append(upstream_artifact_check)
    if upstream_artifact_check["status"] == "FAIL":
        result.can_continue = False

    # 5. 级联失败阻断
    cascade_check = _check_cascade_failure(output_dir, project_id, phase_id)
    result.checks.append(cascade_check)
    if cascade_check["status"] == "FAIL":
        result.can_continue = False

    # 5.5. 上游内容质量检查
    quality_check = _check_upstream_quality(output_dir, project_id, phase_id)
    result.checks.append(quality_check)
    if quality_check["status"] == "FAIL":
        result.can_continue = False

    # 6. 检查 Phase contract 存在
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
    from qualix.runtime.task_store import get_resumable_task

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
    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.phase_registry import PHASE_DEFS

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
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import PhaseStatus, load_state

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
    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    contract_path = output_dir / project_id / dir_suffix / "_internal" / "_phase_contract.json"

    if contract_path.exists():
        return {"name": "contract", "status": "PASS", "detail": "Phase contract exists"}
    return {"name": "contract", "status": "WARNING", "detail": "No phase contract (will be generated on execute)"}


def _check_upstream_artifacts(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """检查上游 Phase 的核心产物（report + structured JSON）是否存在且非空."""
    from qualix.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import PhaseStatus, load_state

    phase_def = PHASE_DEFS.get(phase_id, {})
    deps = phase_def.get("depends_on", [])
    if not deps:
        return {"name": "upstream_artifacts", "status": "PASS", "detail": "No upstream dependencies"}

    state = load_state(output_dir, project_id)
    missing: list[str] = []

    for dep_id in deps:
        ps = state.phases.get(dep_id)
        if not ps or ps.status == PhaseStatus.SKIPPED:
            continue
        if ps.status not in (PhaseStatus.APPROVED, PhaseStatus.PENDING_REVIEW):
            continue

        dep_dir_suffix = PHASE_DIR_MAP.get(dep_id, "")
        dep_dir = output_dir / project_id / dep_dir_suffix

        # 检查 report
        report_file = REPORT_MAP.get(dep_id)
        if report_file:
            report_path = dep_dir / report_file
            if not report_path.exists():
                missing.append(f"{dep_id}/{report_file}")
            elif report_path.stat().st_size == 0:
                missing.append(f"{dep_id}/{report_file} (empty)")

        # 检查 structured JSON
        json_file = STRUCTURED_JSON_MAP.get(dep_id)
        if json_file:
            json_path = dep_dir / json_file
            if not json_path.exists():
                missing.append(f"{dep_id}/{json_file}")
            elif json_path.stat().st_size == 0:
                missing.append(f"{dep_id}/{json_file} (empty)")

    if missing:
        return {
            "name": "upstream_artifacts",
            "status": "FAIL",
            "detail": f"Upstream artifacts missing/empty: {', '.join(missing)}",
        }
    return {"name": "upstream_artifacts", "status": "PASS", "detail": "All upstream artifacts present"}


def _check_cascade_failure(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """级联失败阻断：上游 run_status 为 tainted/parse_failed 时阻断下游."""
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import PhaseStatus, load_state

    phase_def = PHASE_DEFS.get(phase_id, {})
    deps = phase_def.get("depends_on", [])
    if not deps:
        return {"name": "cascade_failure", "status": "PASS", "detail": "No upstream dependencies"}

    state = load_state(output_dir, project_id)
    tainted: list[str] = []

    for dep_id in deps:
        ps = state.phases.get(dep_id)
        if not ps or ps.status == PhaseStatus.SKIPPED:
            continue
        if ps.run_status in _CASCADE_BLOCK_STATUSES:
            tainted.append(f"{dep_id} [{ps.run_status}]")

    if tainted:
        return {
            "name": "cascade_failure",
            "status": "FAIL",
            "detail": f"Upstream tainted/failed: {', '.join(tainted)} — cascade blocked",
        }
    return {"name": "cascade_failure", "status": "PASS", "detail": "No upstream failures"}


def _check_upstream_quality(output_dir: Path, project_id: str, phase_id: str) -> dict[str, str]:
    """Check upstream Phase output content quality (not just file existence).

    Uses checkpoint_validator to verify ID coverage and content adequacy.
    """
    from qualix.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import PhaseStatus, load_state

    phase_def = PHASE_DEFS.get(phase_id, {})
    deps = phase_def.get("depends_on", [])
    if not deps:
        return {"name": "upstream_quality", "status": "PASS", "detail": "No upstream dependencies"}

    state = load_state(output_dir, project_id)
    issues: list[str] = []

    for dep_id in deps:
        ps = state.phases.get(dep_id)
        if not ps or ps.status in (PhaseStatus.SKIPPED,):
            continue
        if ps.status not in (PhaseStatus.APPROVED, PhaseStatus.PENDING_REVIEW):
            continue

        dep_dir = output_dir / project_id / PHASE_DIR_MAP.get(dep_id, "")
        int_dir = dep_dir / "_internal"

        # Load upstream contract for verification targets
        contract_path = int_dir / "_phase_contract.json"
        contract = {}
        if contract_path.exists():
            from qualix.json_utils import load_json

            contract = load_json(contract_path) or {}

        if not contract.get("verification_targets"):
            continue  # No contract → skip quality check for this dep

        # Check structured JSON content
        json_file = STRUCTURED_JSON_MAP.get(dep_id)
        if json_file:
            json_path = dep_dir / json_file
            if json_path.exists():
                import json

                from qualix.json_utils import load_json as _lj

                data = _lj(json_path)
                if data:
                    from qualix.quality.checkpoint_validator import validate_checkpoint

                    result = validate_checkpoint(
                        content=json.dumps(data, ensure_ascii=False),
                        contract=contract,
                        phase_id=dep_id,
                        checkpoint_name=f"upstream_{dep_id}_json",
                    )
                    if not result.passed:
                        issues.append(f"{dep_id}: {result.block_reason}")

        # Check report content
        report_file = REPORT_MAP.get(dep_id)
        if report_file:
            report_path = dep_dir / report_file
            if report_path.exists():
                try:
                    report_text = report_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    report_text = ""
                if report_text:
                    from qualix.quality.checkpoint_validator import validate_checkpoint as _vc

                    result = _vc(
                        content=report_text,
                        contract=contract,
                        phase_id=dep_id,
                        checkpoint_name=f"upstream_{dep_id}_report",
                    )
                    if not result.passed:
                        issues.append(f"{dep_id} report: {result.block_reason}")

    if issues:
        return {
            "name": "upstream_quality",
            "status": "FAIL",
            "detail": f"Upstream quality issues: {'; '.join(issues)}",
        }
    return {"name": "upstream_quality", "status": "PASS", "detail": "All upstream content quality checks passed"}
