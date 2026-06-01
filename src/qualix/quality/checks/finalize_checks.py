"""Finalize 硬性校验：推理日志 + 重跑防回退.

在 finalize 时强制检查：
1. _reasoning_log.md 必须存在
2. 重跑时产物数量不得减少（REQ/BR/SE/GAP/OPEN）
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Final

from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json
from qualix.path_utils import resolve_internal_file
from qualix.text_utils import STRUCTURED_JSON_MAP, expand_eut_ids

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


# Q05b assertion_type 允许的实现范围：EUT 声明的类型 → 可接受的实现类型集合
_ASSERTION_ALLOWED_IMPL: Final = MappingProxyType(
    {
        "assertThrows": {"assertThrows"},  # 异常断言不得降级
        "assertEquals": {"assertEquals", "assertTrue", "expect", "pytest_assert", "go_assert", "state_check"},
        "assertTrue": {"assertTrue", "expect", "pytest_assert", "go_assert", "state_check"},
        "expect": {"expect", "state_check"},
        "pytest_assert": {"pytest_assert", "state_check"},
        "go_assert": {"go_assert", "state_check"},
        "verify": {"verify"},  # mock 调用验证不得降级
        "state_check": {"assertEquals", "assertTrue", "expect", "pytest_assert", "go_assert", "state_check"},
        "other": {
            "assertEquals",
            "assertTrue",
            "assertThrows",
            "expect",
            "pytest_assert",
            "go_assert",
            "verify",
            "state_check",
            "other",
        },
    }
)


def _check_assertion_type_consistency(
    eut_data: dict,
    code_status: dict,
) -> list[str]:
    """cross-field: EUT then_assertion_type vs EutTaskItem.assertion_type.

    当 Q05b 标记某条 EUT passes=True，实际使用的断言类型不得弱于 EUT 设计时声明的类型。
    """
    errors: list[str] = []
    eut_specs = {
        item["eut_id"]: item.get("then_assertion_type", "")
        for item in eut_data.get("eut_items", [])
        if isinstance(item, dict) and item.get("eut_id")
    }
    if not eut_specs:
        return errors

    for task in code_status.get("tasks", []):
        if not isinstance(task, dict) or not task.get("passes"):
            continue
        eut_id = task.get("eut_id", "")
        impl_type = task.get("assertion_type", "")
        spec_type = eut_specs.get(eut_id, "")
        if not spec_type or not impl_type:
            continue
        allowed = _ASSERTION_ALLOWED_IMPL.get(spec_type, set())
        if impl_type not in allowed:
            errors.append(
                f"BLOCKED: {eut_id} 断言类型降级——EUT 设计声明 {spec_type}，"
                f"实现时使用了 {impl_type}（不在允许范围 {sorted(allowed)} 内）。"
                "弱断言是铁律：实现必须达到或超过 EUT 规格声明的断言强度。"
            )
    return errors


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
            f"请在 {int_dir}/_reasoning_log.md 或 {pd}/_reasoning_log.md 中记录执行过程后重新 finalize。"
        )
    else:
        # 检查内容不为空且有实质内容
        content = log_path.read_text(encoding="utf-8").strip()
        if len(content) < 100:
            errors.append(
                f"BLOCKED: _reasoning_log.md 内容过少（{len(content)} 字符）。"
                f"推理日志必须记录每个 Step 的决策过程、依据、发现。"
            )

    # B: 手动模式 Step 0.5 守卫——检查 _bootstrap_context.md 是否已读取
    # adaptive 模式有 _adaptive_summary.json（framework 自动注入 context），跳过此检查
    if not errors:
        adaptive_summary = pd / "_adaptive_summary.json"
        if not adaptive_summary.exists():
            sentinel = int_dir / ".bootstrap_context_read"
            if not sentinel.exists():
                errors.append(
                    f"BLOCKED: Step 0.5 未完成——未发现 _bootstrap_context.md 已读取的证据。"
                    f"手动模式执行 {phase_id} 前必须先读取 {int_dir}/_bootstrap_context.md，"
                    f"以确保产物包含所有必填内容（PROFILE_CONTEXT/decision_owner/GAP P级等）。"
                    f"读取后 sentinel 自动创建，"
                    f"再重新生成产物并 finalize。"
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


def check_se_based_pattern(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """检测 Q05a/Q06 产物是否使用了被禁止的 SE-based 汇总模式.

    铁律：Q05a（EUT矩阵设计）和 Q06（单测覆盖审计）必须使用 EUT 逐条模式：
    每条 audit_item/eut_item 必须对应一个独立的 eut_id，不允许按 SE 汇总。

    SE-based 模式的判定条件（满足任一即判定违规）：
    1. eut_id 字段以 SE- 开头（明确的 SE 级别 ID）
    2. 多条条目共享相同 eut_id（汇总特征）
    3. Q06 audit_items 数量 << Q01 SE 数量（比值 < 0.5 且 SE ≥ 3，WARNING 级别）

    Returns:
        错误列表，有 BLOCKED 前缀的错误会阻断 finalize。
    """
    if phase_id not in ("Q05a", "Q06"):
        return []

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []

    json_path = pd / json_file
    if not json_path.exists():
        return []

    data = load_json(json_path)
    if not data:
        return []

    errors: list[str] = []

    if phase_id == "Q05a":
        eut_items = data.get("eut_items", [])
        if not eut_items:
            return []

        # 判定1：eut_id 以 SE- 开头（明确 SE-based）
        se_format_ids = [
            item.get("eut_id", "") for item in eut_items
            if isinstance(item, dict) and item.get("eut_id", "").startswith("SE-")
        ]
        if se_format_ids:
            errors.append(
                f"BLOCKED: Q05a 使用了 SE-based 模式——发现 {len(se_format_ids)} 条 eut_item 的 eut_id "
                f"以 SE- 开头（如 {se_format_ids[0]!r}）。"
                "EUT 矩阵设计必须使用 EUT 逐条模式：每条 eut_item 必须有独立的 EUT-NNN 格式 eut_id。"
                "按 SE 汇总会掩盖单个测试方法的骨架/弱断言问题，导致覆盖率虚高。"
            )

        # 判定2：重复 eut_id（汇总特征）
        from collections import Counter

        eut_id_counts = Counter(
            item.get("eut_id", "") for item in eut_items
            if isinstance(item, dict) and item.get("eut_id", "")
        )
        duplicates = {eid: cnt for eid, cnt in eut_id_counts.items() if cnt > 1}
        if duplicates:
            dup_sample = list(duplicates.items())[:3]
            errors.append(
                f"BLOCKED: Q05a 发现重复 eut_id——{dup_sample}。"
                "EUT 逐条模式要求每个 eut_id 唯一，重复出现说明多条 EUT 被汇总进了同一条目。"
            )

    elif phase_id == "Q06":
        audit_items = data.get("audit_items", [])
        if not audit_items:
            return []

        # 判定1：eut_id 以 SE- 开头
        se_level_items = [
            item for item in audit_items
            if isinstance(item, dict) and item.get("eut_id", "").startswith("SE-")
        ]
        if se_level_items:
            errors.append(
                f"BLOCKED: Q06 使用了 SE-based 模式——发现 {len(se_level_items)} 条 audit_item 的 eut_id "
                f"以 SE- 开头（如 {se_level_items[0].get('eut_id')!r}）。"
                "Q06 单测覆盖审计必须使用 EUT 逐条模式：每条 audit_item 对应一个 EUT-NNN。"
                "按 SE 汇总粒度过粗，会掩盖单个测试方法的覆盖问题。"
            )

        # 判定2（WARNING）：audit_items 数量 << Q01 SE 数量（比率检查，仅在无明确 SE-based 特征时）
        q01_phase_def = PHASE_DEFS.get("Q01")
        if q01_phase_def and not se_level_items:
            q01_json_file = STRUCTURED_JSON_MAP.get("Q01")
            if q01_json_file:
                q01_path = _phase_dir(output_dir, project_id, q01_phase_def) / q01_json_file
                if q01_path.exists():
                    q01_data = load_json(q01_path) or {}
                    se_count = len(q01_data.get("semantic_expectations", []))
                    audit_count = len(audit_items)
                    if se_count >= 3 and audit_count < se_count * 0.5:
                        errors.append(
                            f"WARNING: Q06 audit_items 数量（{audit_count}）远少于 Q01 SE 数量（{se_count}），"
                            f"比值 {audit_count / se_count:.1%} < 50%。"
                            "请确认是否为 EUT 逐条模式。如果确实逐条，忽略此 WARNING。"
                        )

    return errors


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

    # SE-based 模式检测（Q05a/Q06 铁律）
    errors.extend(check_se_based_pattern(output_dir, project_id, phase_id))

    # Phase B: 结构合规（EUT/路径/Mock 启发式）先于编译执行
    if phase_id == "Q05a":
        from .q05_structure_checks import run_q05_structure_checks

        errors.extend(run_q05_structure_checks(output_dir, project_id, phase_id=phase_id))

    # Q05a: EUT → SE.code_target 可追溯性检查（始终 WARNING，TDD 兼容）
    if phase_id == "Q05a":
        from .evidence_contract import check_eut_code_target_traceability

        phase_def_q05a = PHASE_DEFS.get("Q05a")
        if phase_def_q05a:
            int_dir_q05a = _internal_dir(output_dir, project_id, phase_def_q05a)
            inputs_q05a = load_json(int_dir_q05a / "_inputs.json") if (int_dir_q05a / "_inputs.json").is_file() else {}
            code_repos_q05a: list[str] = (inputs_q05a or {}).get("code_repos", [])
            if not code_repos_q05a and (inputs_q05a or {}).get("code_repo"):
                code_repos_q05a = [inputs_q05a["code_repo"]]
            errors.extend(check_eut_code_target_traceability(output_dir, project_id, code_repos_q05a))

    # Phase Q05b: C1+C2 then 字段对齐检查
    # Q05b Ralph Loop 只跑 C9+编译，不跑 C1+C2（then 关键词对齐）。
    # 补在 finalize gate 里：EUT then 描述的断言方法名/关键词必须出现在对应 @Test 方法体内。
    # 读 Q05a 的 EUT 矩阵（规格），检查 Q05b 生成的测试代码。
    if phase_id == "Q05b":
        from .q05_structure_checks import (
            _collect_new_test_files_from_repos,
            check_eut_method_alignment,
        )

        phase_def_q05a = PHASE_DEFS.get("Q05a")
        phase_def_q05b = PHASE_DEFS.get("Q05b")
        if phase_def_q05a and phase_def_q05b:
            from qualix.constants import STRUCTURED_JSON_MAP as _SJM

            eut_matrix_path = _phase_dir(output_dir, project_id, phase_def_q05a) / _SJM["Q05a"]
            eut_data = load_json(eut_matrix_path) if eut_matrix_path.is_file() else {}

            int_dir_q05b = _internal_dir(output_dir, project_id, phase_def_q05b)
            inputs_data_q05b = load_json(int_dir_q05b / "_inputs.json") or {}
            code_repos_q05b: list[str] = inputs_data_q05b.get("code_repos", [])
            if not code_repos_q05b and inputs_data_q05b.get("code_repo"):
                code_repos_q05b = [inputs_data_q05b["code_repo"]]

            if eut_data and code_repos_q05b:
                test_files = _collect_new_test_files_from_repos(code_repos_q05b)
                # 方法级 C1+C2：每个 // EUT-xxx 标注的 @Test 方法体必须含 then 业务关键词
                c12_errors = check_eut_method_alignment(eut_data, test_files)
                if c12_errors:
                    errors.extend(c12_errors)

            # Assertion type 一致性：EUT then_assertion_type vs EutTaskItem.assertion_type
            # phase_b_code_status.json 里 passes=True 的条目的 assertion_type 不得弱于
            # phase_b_structured.json 中对应 EUT 的 then_assertion_type
            if phase_def_q05b:
                from qualix.constants import STRUCTURED_JSON_MAP as _SJM2

                code_status_path = _phase_dir(output_dir, project_id, phase_def_q05b) / _SJM2["Q05b"]
                code_status = load_json(code_status_path) if code_status_path.is_file() else {}
                errors.extend(_check_assertion_type_consistency(eut_data or {}, code_status or {}))

    # Phase Q05b: 单测编译 gate（从 _inputs.json 读 code_repos，逐仓库检查）
    if phase_id == "Q05b":
        from .compile_check import check_phase_b_compilation

        phase_def_q05b = PHASE_DEFS.get(phase_id)
        if phase_def_q05b:
            int_dir_q05b = _internal_dir(output_dir, project_id, phase_def_q05b)
            inputs_data_q05b_compile = load_json(int_dir_q05b / "_inputs.json") or {}
            code_repos_q05b_compile: list[str] = inputs_data_q05b_compile.get("code_repos", [])
            if not code_repos_q05b_compile and inputs_data_q05b_compile.get("code_repo"):
                code_repos_q05b_compile = [inputs_data_q05b_compile["code_repo"]]
            for repo in code_repos_q05b_compile:
                errors.extend(check_phase_b_compilation(output_dir, project_id, repo))

    # Phase Q05b: 单测编译+运行铁律 gate（不可跳过）
    if phase_id == "Q05b":
        from .test_execution_gate import check_q05_test_execution

        errors.extend(check_q05_test_execution(output_dir, project_id))

    # Phase C: 结构合规（COVERED断言强度 / sidecar利用 / WRONG_TARGET验证）
    if phase_id == "Q06":
        from .q06_structure_checks import run_q06_structure_checks

        errors.extend(run_q06_structure_checks(output_dir, project_id))

    # Phase C: 覆盖率门禁（Change 4: coverage evidence 缺失时 BLOCKED，不再静默通过）
    if phase_id == "Q06":
        from .coverage_gate import check_phase_c_coverage, find_coverage_report

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

            if not code_repos:
                errors.append("NOT_APPLICABLE: Q06 coverage gate skipped — no code_repo configured in _inputs.json")
            else:
                _any_coverage = bool(coverage_report) or any(
                    (p := Path(r).expanduser().resolve()).is_dir() and find_coverage_report(p) for r in code_repos
                )
                if not _any_coverage:
                    errors.append(
                        "BLOCKED: Q06 coverage_evidence_missing — 配置了代码仓库但找不到 JaCoCo/Istanbul 覆盖率报告。"
                        "请先运行测试并生成覆盖率报告（mvn test jacoco:report 或 jest --coverage），"
                        "或通过 --coverage-report 参数指定报告路径。"
                    )
                else:
                    coverage_errors: list[str] = []
                    for repo in code_repos:
                        coverage_errors.extend(check_phase_c_coverage(output_dir, project_id, repo, coverage_report))

                    # 若 Q06 审计结论已是 FAIL，coverage BLOCKED → WARNING
                    # （FAIL IS the coverage gate result；已记录在 phase_c_structured.json，无需再阻断）
                    _conclusion = ""
                    if phase_def:
                        _json_file = STRUCTURED_JSON_MAP.get("Q06", "phase_c_structured.json")
                        _json_path = _phase_dir(output_dir, project_id, phase_def) / _json_file
                        if _json_path.is_file():
                            _c_data = load_json(_json_path) or {}
                            _conclusion = _c_data.get("conclusion", "") or _c_data.get("verdict", "")
                    if _conclusion == "FAIL":
                        coverage_errors = [e.replace("BLOCKED:", "WARNING(FAIL-expected):", 1) for e in coverage_errors]
                    errors.extend(coverage_errors)

    return errors
