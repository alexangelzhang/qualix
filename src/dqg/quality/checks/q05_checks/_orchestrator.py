"""run_q05_structure_checks 编排器."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.constants import STRUCTURED_JSON_MAP
from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

from ._checks_concurrency import (
    _check_concurrency_eut_multithread,
    _check_concurrent_scope,
    _check_concurrent_se_no_eut,
)
from ._checks_coverage import (
    _check_branch_file_reality,
    _check_q05_git_diff_coverage,
    _check_target_modules_json,
    _check_uncovered_br_reasons,
)
from ._checks_eut_alignment import (
    _check_eut_code_alignment,
    _check_never_verify_in_code,
    _check_se_id_validity_in_traceability,
    _check_test_file_eut_reverse,
    _check_test_location_file_exists,
)
from ._checks_eut_basic import (
    _check_eut_missing_se,
    _check_mock_patterns,
    _check_multi_repo_coverage,
    _check_se_traceability,
    _check_wrong_directory,
)
from ._checks_eut_impl import (
    _check_eut_implementation_completeness,
)
from ._checks_production import check_eut_then_phantom_methods
from ._collect import _collect_new_test_files_from_repos, _collect_supplemental_files


def run_q05_structure_checks(output_dir: Path, project_id: str, phase_id: str = "Q05") -> list[str]:
    """对 Q05/Q05a phase_b_structured + supplemental_tests 做结构类校验."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_name = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_name:
        return []

    path = pd / json_name
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []

    # 提前加载 code_repos（同时供 mock patterns 检查和并发 scope 检查使用）
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs_data = load_json(int_dir / "_inputs.json") if (int_dir / "_inputs.json").is_file() else {}
    code_repos: list[str] = []
    if inputs_data and isinstance(inputs_data, dict):
        code_repos = inputs_data.get("code_repos") or []
        if not code_repos and inputs_data.get("code_repo"):
            code_repos = [inputs_data["code_repo"]]

    errors: list[str] = []
    errors.extend(_check_eut_missing_se(data))
    errors.extend(_check_wrong_directory(data))

    # mock 拼写/幽灵方法检查：有 code_repos 就扫业务仓库新增测试文件，否则 fallback 旧目录
    test_files = _collect_new_test_files_from_repos(code_repos) if code_repos else _collect_supplemental_files(pd)
    errors.extend(_check_mock_patterns(test_files))

    # Fix-3: SE/EUT 追溯标注（WARNING）
    errors.extend(_check_se_traceability(test_files))

    # Fix-4: 多仓库完整性
    errors.extend(_check_multi_repo_coverage(code_repos, test_files))

    # ── 并发/幂等/锁强管控 ────────────────────────────────────────────────────
    # 加载 Q01 产物（获取 SE 描述，用于关键词匹配）
    q01_def = PHASE_DEFS.get("Q01")
    q01_data: dict[str, Any] | None = None
    if q01_def:
        q01_json = STRUCTURED_JSON_MAP.get("Q01")
        if q01_json:
            q01_path = _phase_dir(output_dir, project_id, q01_def) / q01_json
            q01_data = load_json(q01_path) if q01_path.is_file() else None

    errors.extend(_check_concurrent_se_no_eut(data, q01_data))

    # Step 0.5 三层驱动产物验证（BLOCKED + 交叉验证）
    errors.extend(_check_target_modules_json(output_dir, project_id, phase_def, code_repos, test_files, q01_data))

    # uncovered BR 理由合理性（WARNING）
    errors.extend(_check_uncovered_br_reasons(output_dir, project_id, phase_def, q01_data))

    # Fix-5: 并发测试 CountDownLatch 多线程验证（BLOCKED）
    errors.extend(_check_concurrency_eut_multithread(data, test_files, q01_data))

    # Fix-6: 设计矩阵 branch 文件真实性（WARNING）
    errors.extend(_check_branch_file_reality(output_dir, project_id, phase_def, code_repos))

    # C1+C2: EUT when/then 与测试代码关键词交叉验证（WARNING）
    errors.extend(_check_eut_code_alignment(data, test_files, q01_data))

    # C4: never() 直接扫测试代码（补充 JSON then 字段检查的不足）
    errors.extend(_check_never_verify_in_code(data, test_files, q01_data))

    # C5: 追溯注释里的 SE ID 必须是 Q01 真实存在的（WARNING）
    errors.extend(_check_se_id_validity_in_traceability(test_files, q01_data))

    # C7: test_location.file 必须在磁盘上真实存在（WARNING）
    errors.extend(_check_test_location_file_exists(data, code_repos))

    # C8: 反向检查——@InjectMocks 类必须在 EUT 矩阵里有对应（WARNING）
    target_modules_data = (
        load_json(int_dir / "_q05_target_modules.json") if (int_dir / "_q05_target_modules.json").is_file() else None
    )
    errors.extend(_check_test_file_eut_reverse(data, test_files, target_modules_data))

    # C9: EUT 矩阵实现完整性——每条 EUT 的被测类必须有对应 @Test 文件（BLOCKED）
    errors.extend(_check_eut_implementation_completeness(data, test_files))

    # C10: git diff 变更的实现类必须有对应 EUT（BLOCKED）
    errors.extend(_check_q05_git_diff_coverage(data, target_modules_data))

    # C11: EUT then 字段的业务方法名必须在生产代码中真实存在（BLOCKED）
    # 防止 LLM 幻觉方法名（如 orderService.createOrder 但该服务不是被测类的依赖）进入矩阵
    if code_repos:
        errors.extend(check_eut_then_phantom_methods(data, code_repos))

    # concurrent_scope 是 WARNING 级别（不阻断 finalize）
    # 同时检测注解（@DistributedLocked 等）和代码级并发原语（ReentrantLock/synchronized/Atomic* 等）
    concurrent_warnings = _check_concurrent_scope(data, code_repos)
    if concurrent_warnings:
        log.warning("Q05 concurrent_scope: %d warning(s)", len(concurrent_warnings))
        errors.extend(concurrent_warnings)  # WARNING 前缀，approve guardrail 会区分

    if errors:
        log.info("Q05 structure checks: %d issue(s)", len(errors))
    return errors
