"""AutoHarness: 从 Pydantic schema + phase_registry 自动推导 finalize 校验.

自动生成的校验覆盖：
1. Schema 校验：JSON 产物是否符合 Pydantic 数据契约
2. 交叉引用校验：GAP/OPEN 的 related_ids 是否指向存在的 REQ/BR
3. 完整性校验：approve_checklist 中可自动验证的条目
4. 严重等级校验：GAP/Issue 是否标注了严重等级（当 schema 有 severity 字段时）
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from pydantic import ValidationError

from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger
from dqg.text_utils import STRUCTURED_JSON_MAP

log = get_logger(__name__)

# Phase → Pydantic 模型类（延迟导入避免循环）
_SCHEMA_MAP: Final = MappingProxyType({
    "Q01": "dqg.schemas.phase_a:PhaseAOutput",
    "Q02": "dqg.schemas.phase_a3:PhaseA3Output",
    "Q04": "dqg.schemas.phase_a5:PhaseA5Output",
    "Q03": "dqg.schemas.phase_a6:PhaseA6Output",
    "Q05": "dqg.schemas.phase_b:PhaseBOutput",
    "Q06": "dqg.schemas.phase_c:PhaseCOutput",
    "Q07": "dqg.schemas.phase_d:PhaseDOutput",
})


def _import_schema(phase_id: str):
    """动态导入 Phase 对应的 Pydantic 模型."""
    module_path = _SCHEMA_MAP.get(phase_id)
    if not module_path:
        return None
    module_name, class_name = module_path.rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_name)
    return getattr(mod, class_name, None)


def auto_derive_checks(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str]:
    """从 schema + registry 自动推导校验，返回错误列表.

    校验层次：
    1. Schema 合规性（Pydantic 校验）
    2. 交叉引用完整性（related_ids 指向存在的 ID）
    3. 严重等级标注（有 severity 字段的条目必须非空）
    4. 最小产物要求（deliverables 文件是否存在）
    """
    errors: list[str] = []
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return errors

    pd = _phase_dir(output_dir, project_id, phase_def)

    # --- 1. 交付物文件存在性检查 ---
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        json_path = pd / json_file
        if not json_path.exists():
            errors.append(f"MISSING: 结构化产物 {json_file} 不存在")
            return errors  # 没有 JSON 就无法做后续校验

        # --- 2. Schema 合规性校验 ---
        data = load_json(json_path)
        if data is None:
            errors.append(f"INVALID: {json_file} 无法解析为 JSON")
            return errors

        schema_cls = _import_schema(phase_id)
        if schema_cls:
            try:
                validated = schema_cls.model_validate(data)
            except ValidationError as e:
                for err in e.errors()[:5]:  # 最多报 5 个
                    loc = " → ".join(str(x) for x in err["loc"])
                    errors.append(f"SCHEMA: {loc}: {err['msg']}")
                return errors  # schema 不过就不做后续检查
            else:
                # --- 3. 交叉引用校验 ---
                errors.extend(_check_cross_references(validated, phase_id))
                # --- 4. 严重等级标注校验 ---
                errors.extend(_check_severity_annotations(validated, phase_id))

    # --- 5. RSM 覆盖率校验（跨 Phase，在 A.5/B/D finalize 时触发）---
    if phase_id in {"Q04", "Q05", "Q06", "Q07"}:
        errors.extend(_check_rsm_coverage(output_dir, project_id, phase_id))

    return errors


def _check_cross_references(validated: Any, phase_id: str) -> list[str]:
    """检查 related_ids 是否指向存在的 ID."""
    errors: list[str] = []

    if phase_id == "Q01":
        # 收集所有已定义的 ID
        all_ids: set[str] = set()
        for req in getattr(validated, "requirements", []):
            all_ids.add(req.req_id)
        for se in getattr(validated, "semantic_expectations", []):
            all_ids.add(se.se_id)

        # 检查 GAP 的 related_ids
        for gap in getattr(validated, "gaps", []):
            for ref_id in gap.related_ids:
                if ref_id and ref_id not in all_ids:
                    errors.append(
                        f"XREF: {gap.gap_id} 引用了不存在的 ID '{ref_id}'"
                    )

        # 检查 OPEN 的 related_ids
        for item in getattr(validated, "open_items", []):
            for ref_id in item.related_ids:
                if ref_id and ref_id not in all_ids:
                    errors.append(
                        f"XREF: {item.open_id} 引用了不存在的 ID '{ref_id}'"
                    )

    return errors


def _check_severity_annotations(validated: Any, phase_id: str) -> list[str]:
    """检查有 severity 字段的条目是否都标注了严重等级."""
    errors: list[str] = []

    if phase_id == "Q03":
        for issue in getattr(validated, "issues", []):
            if not issue.severity:
                errors.append(
                    f"SEVERITY: {issue.issue_id} 未标注严重等级"
                )
        # Failure Mode 必须有 status
        for fm in getattr(validated, "failure_modes", []):
            if not fm.failure_scenario:
                errors.append(
                    f"SEVERITY: failure_mode '{fm.business_path}' 缺少 failure_scenario"
                )

    if phase_id == "Q01":
        # GAP 应该有 required_clarification
        for gap in getattr(validated, "gaps", []):
            if not gap.required_clarification:
                errors.append(
                    f"INCOMPLETE: {gap.gap_id} 缺少 required_clarification（需要说明需要澄清什么）"
                )

    return errors


def _check_rsm_coverage(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """RSM 覆盖率校验：检查跨 Phase 的需求追踪完整性.

    发现缺口时自动生成补充任务文件（_coverage_gap_tasks.json），
    下游 Phase 可消费这些任务做定向补充。
    """
    errors: list[str] = []

    try:
        from dqg.schemas.rsm import compute_coverage, load_rsm
        lifecycle = load_rsm(output_dir, project_id)
        if not lifecycle:
            return errors  # Phase A 还没跑，无法计算

        coverage = compute_coverage(lifecycle, project_id)
    except Exception:
        return errors  # RSM 计算失败不阻断 finalize

    # 保存覆盖率快照（趋势追踪）
    try:
        from dqg.store.store_coverage import save_coverage_snapshot
        save_coverage_snapshot(output_dir, project_id, phase_id, coverage)
    except Exception:
        pass  # 快照保存失败不阻断

    gap_tasks: list[dict[str, Any]] = []

    if phase_id == "Q04":
        # A.5 finalize 时：REQ 覆盖率不应低于 80%
        if coverage.total_reqs > 0 and coverage.req_coverage_rate < 0.8:
            errors.append(
                f"RSM_COVERAGE: REQ 覆盖率 {coverage.req_coverage_rate:.0%} "
                f"低于阈值 80%（{coverage.reqs_covered}/{coverage.total_reqs}）"
            )
            # 收集未覆盖的 REQ，生成补充任务
            for item in lifecycle.values():
                if item.id_type == "REQ" and item.coverage_status not in ("COVERED", "IMPLICIT"):
                    gap_tasks.append({
                        "target_id": item.req_id,
                        "target_phase": "Q04",
                        "action": "补充技术方案覆盖",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": item.coverage_status or "UNKNOWN",
                    })
        # GAP 闭环率
        if coverage.total_gaps > 0 and coverage.gap_closure_rate < 0.5:
            errors.append(
                f"RSM_COVERAGE: GAP 闭环率 {coverage.gap_closure_rate:.0%} "
                f"低于阈值 50%（{coverage.gaps_closed}/{coverage.total_gaps}）"
            )
            for item in lifecycle.values():
                if item.id_type == "GAP" and item.closure_status != "已闭环":
                    gap_tasks.append({
                        "target_id": item.req_id,
                        "target_phase": "Q04",
                        "action": "闭环 GAP",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": item.closure_status or "未闭环",
                    })

    if phase_id in ("Q05", "Q06"):
        # B/C finalize 时：SE 应该有对应 EUT
        if coverage.total_ses > 0 and coverage.test_coverage_rate < 0.6:
            errors.append(
                f"RSM_COVERAGE: SE→EUT 测试覆盖率 {coverage.test_coverage_rate:.0%} "
                f"低于阈值 60%（{coverage.ses_with_eut}/{coverage.total_ses}）"
            )
            for item in lifecycle.values():
                if item.id_type == "SE" and not item.eut_ids:
                    gap_tasks.append({
                        "target_id": item.req_id,
                        "target_phase": "Q05",
                        "action": "补充 EUT",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": "NO_EUT",
                    })

    if phase_id == "Q07":
        # D finalize 时：REQ 应该有对应 finding
        if coverage.total_reqs > 0 and coverage.review_coverage_rate < 0.5:
            errors.append(
                f"RSM_COVERAGE: REQ→Finding 评审覆盖率 {coverage.review_coverage_rate:.0%} "
                f"低于阈值 50%（{coverage.reqs_with_finding}/{coverage.total_reqs}）"
            )
            for item in lifecycle.values():
                if item.id_type == "REQ" and not item.finding_ids:
                    gap_tasks.append({
                        "target_id": item.req_id,
                        "target_phase": "Q07",
                        "action": "补充代码评审",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": "NOT_REVIEWED",
                    })

    # 保存补充任务文件（供下游 Phase 或 Adaptive Loop 消费）
    if gap_tasks:
        _save_gap_tasks(output_dir, project_id, phase_id, gap_tasks)

    return errors


def _save_gap_tasks(
    output_dir: Path, project_id: str, phase_id: str, tasks: list[dict[str, Any]],
) -> None:
    """保存覆盖率缺口补充任务."""
    from dqg.json_utils import save_json
    from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_coverage_gap_tasks.json"
    save_json(path, {"phase_id": phase_id, "tasks": tasks})
