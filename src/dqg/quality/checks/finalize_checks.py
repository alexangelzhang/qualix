"""Finalize 硬性校验：推理日志 + 重跑防回退.

在 finalize 时强制检查：
1. _reasoning_log.md 必须存在
2. 重跑时产物数量不得减少（REQ/BR/SE/GAP/OPEN）
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Final

from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json, save_json
from dqg.path_utils import resolve_internal_file
from dqg.text_utils import STRUCTURED_JSON_MAP, expand_eut_ids

# Phase → 需要检查数量的字段
_COUNT_FIELDS: Final = MappingProxyType(
    {
        "Q01": ["requirements", "semantic_expectations", "gaps", "open_items"],
        "Q04": ["req_coverage", "se_coverage", "gap_closure", "open_closure"],
        "Q03": ["issues", "failure_modes"],
        "Q06": ["audit_items"],
        "Q07": ["findings"],
    }
)


def check_reasoning_log(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """检查 _reasoning_log.md 是否存在.

    Returns:
        错误列表，空表示通过
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    log_path = resolve_internal_file(pd, "_reasoning_log.md")

    errors = []
    if not log_path.exists():
        errors.append(
            f"BLOCKED: _reasoning_log.md 不存在。"
            f"推理日志是必须交付物，记录每步决策过程。"
            f"请在 {int_dir}/_reasoning_log.md 中记录执行过程后重新 finalize。"
        )
    else:
        # 检查内容不为空且有实质内容
        content = log_path.read_text(encoding="utf-8").strip()
        if len(content) < 100:
            errors.append(
                f"BLOCKED: _reasoning_log.md 内容过少（{len(content)} 字符）。"
                f"推理日志必须记录每个 Step 的决策过程、依据、发现。"
            )

    return errors


def check_no_regression(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """检查重跑时产物数量不减少.

    通过对比 telemetry 中的历史记录判断是否是重跑。
    如果是重跑，对比当前产物和上一次的产物数量。

    Returns:
        错误列表，空表示通过
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []

    current_path = pd / json_file
    if not current_path.exists():
        return []

    # 检查是否有历史快照（上次 finalize 时保存的数量）
    snapshot_path = resolve_internal_file(pd, "_prev_counts.json")
    if not snapshot_path.exists():
        # 首次执行，保存当前数量作为基线
        int_dir.mkdir(parents=True, exist_ok=True)
        _save_counts_snapshot(current_path, int_dir / "_prev_counts.json", phase_id)
        return []

    # 有历史快照 → 这是重跑，检查数量不减少
    errors = []
    try:
        prev_counts = load_json(snapshot_path)
        if prev_counts is None:
            return []
        current_counts = _count_items(current_path, phase_id)

        for field, prev_count in prev_counts.items():
            curr_count = current_counts.get(field, 0)
            if curr_count < prev_count:
                errors.append(
                    f"REGRESSION: {field} 数量从 {prev_count} 减少到 {curr_count}。"
                    f"重跑时产物数量不得减少，新版必须是旧版超集。"
                    f"请检查是否遗漏了旧版中的内容。"
                )

        if not errors:
            # 通过检查，更新快照（始终写入 _internal/）
            int_dir.mkdir(parents=True, exist_ok=True)
            _save_counts_snapshot(current_path, int_dir / "_prev_counts.json", phase_id)

    except OSError:
        pass  # 快照损坏不阻断

    return errors


def _count_items(json_path: Path, phase_id: str) -> dict[str, int]:
    """统计结构化 JSON 中各字段的数量."""
    data = load_json(json_path)
    if data is None:
        return {}

    counts: dict[str, int] = {}
    fields = _COUNT_FIELDS.get(phase_id, [])

    for field in fields:
        items = data.get(field, [])
        if isinstance(items, list):
            counts[field] = len(items)

    # Phase A 特殊处理：分别统计 REQ 和 BR
    if phase_id == "Q01":
        reqs = data.get("requirements", [])
        counts["req_count"] = len([r for r in reqs if r.get("req_id", "").startswith("REQ-")])
        counts["br_count"] = len([r for r in reqs if r.get("req_id", "").startswith("BR-")])

    # Q06: SE-based 模式下按展开后的 EUT 数量计数，兼容旧版逐条模式
    if phase_id == "Q06" and "audit_items" in counts:
        items = data.get("audit_items", [])
        if items and items[0].get("se_id"):
            all_euts: set[str] = set()
            for item in items:
                all_euts |= expand_eut_ids(item.get("eut_id") or "")
            counts["audit_items"] = len(all_euts)

    return counts


def _save_counts_snapshot(json_path: Path, snapshot_path: Path, phase_id: str) -> None:
    """保存当前产物数量快照."""
    counts = _count_items(json_path, phase_id)
    if counts:
        save_json(snapshot_path, counts)


def run_finalize_checks(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """运行所有 finalize 硬性校验.

    Returns:
        错误列表。有 BLOCKED 前缀的错误会阻断 finalize。
    """
    errors = []
    errors.extend(check_reasoning_log(output_dir, project_id, phase_id))
    errors.extend(check_no_regression(output_dir, project_id, phase_id))

    # AutoHarness: 从 schema + registry 自动推导校验
    from .auto_checks import auto_derive_checks

    errors.extend(auto_derive_checks(output_dir, project_id, phase_id))

    # Phase B: 结构合规（EUT/路径/Mock 启发式）先于编译执行
    if phase_id == "Q05":
        from .q05_structure_checks import run_q05_structure_checks

        errors.extend(run_q05_structure_checks(output_dir, project_id))

    # Phase B: 单测编译 gate（从 _inputs.json 读 code_repos，逐仓库检查）
    if phase_id == "Q05":
        from .compile_check import check_phase_b_compilation

        phase_def_q05 = PHASE_DEFS.get("Q05")
        if phase_def_q05:
            int_dir_q05 = _internal_dir(output_dir, project_id, phase_def_q05)
            inputs_data_q05 = load_json(int_dir_q05 / "_inputs.json") or {}
            code_repos_q05: list[str] = inputs_data_q05.get("code_repos", [])
            if not code_repos_q05 and inputs_data_q05.get("code_repo"):
                code_repos_q05 = [inputs_data_q05["code_repo"]]
            for repo in code_repos_q05:
                errors.extend(check_phase_b_compilation(output_dir, project_id, repo))

    # Phase B: 单测编译+运行铁律 gate（不可跳过）
    if phase_id == "Q05":
        from .test_execution_gate import check_q05_test_execution

        errors.extend(check_q05_test_execution(output_dir, project_id))

    # Phase C: 覆盖率门禁（解析 JaCoCo XML，支持多 repo）
    if phase_id == "Q06":
        from .coverage_gate import check_phase_c_coverage

        phase_def = PHASE_DEFS.get(phase_id)
        if phase_def:
            int_dir = _internal_dir(output_dir, project_id, phase_def)
            inputs_path = int_dir / "_inputs.json"
            code_repos = []
            coverage_report = None
            if inputs_path.exists():
                inputs_data = load_json(inputs_path)
                if inputs_data:
                    code_repos = inputs_data.get("code_repos", [])
                    if not code_repos and inputs_data.get("code_repo"):
                        code_repos = [inputs_data["code_repo"]]
                    coverage_report = inputs_data.get("coverage_report")
            for repo in code_repos:
                errors.extend(check_phase_c_coverage(output_dir, project_id, repo, coverage_report))
            if not code_repos:
                errors.extend(check_phase_c_coverage(output_dir, project_id, None, coverage_report))

    return errors
