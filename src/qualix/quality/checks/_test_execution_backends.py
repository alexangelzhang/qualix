"""Language-specific backend implementations for the Q05b test execution gate.

Each ``_run_*_gate`` function handles one language family and returns a list
of BLOCKED error strings (empty = pass).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from qualix.log import get_logger

log = get_logger(__name__)


def _run_java_gate(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
    *,
    _discover_fn=None,
    _group_fn=None,
    _run_check_fn=None,
) -> list[str]:
    """Java/Maven 路径：与原逻辑完全一致（verbatim extract）.

    The keyword-only ``_discover_fn``, ``_group_fn``, and ``_run_check_fn``
    arguments are injection points for unit-testing.  In production they are
    always ``None`` and the real helpers are imported lazily.
    """
    from qualix.quality.checks.test_execution_gate import (
        _discover_new_test_classes,
        _group_by_module,
        run_test_check,
    )

    discover = _discover_fn or _discover_new_test_classes
    group = _group_fn or _group_by_module
    run_check = _run_check_fn or run_test_check

    errors: list[str] = []
    total_tested = 0

    for repo_str in code_repos:
        repo_path = Path(repo_str).expanduser().resolve()
        if not repo_path.is_dir():
            errors.append(f"BLOCKED: 代码仓库路径不存在: {repo_path}")
            continue

        test_files = discover(repo_path)
        if not test_files:
            log.info("仓库 %s 无新增测试文件，跳过", repo_path.name)
            continue

        # 按语言分组：TS 文件整批执行，Java 文件按 Maven 模块分组
        ts_files = [tf for tf in test_files if tf.get("language") == "typescript"]
        java_files = [tf for tf in test_files if tf.get("language") != "typescript"]

        if ts_files:
            ts_paths = [tf["path"] for tf in ts_files]
            log.info("测试验证(TS): %s — %d 个测试文件", repo_path.name, len(ts_paths))
            result = run_check(repo_path, ts_paths, language="typescript")
            total_tested += len(ts_paths)
            if not result["passed"]:
                errors.append(f"BLOCKED: {repo_path.name} TS 测试失败 ({len(ts_paths)} 个文件)")
                if result["error_summary"]:
                    errors.append(f"  错误摘要:\n{result['error_summary']}")

        by_module = group(java_files)
        for module, classes in by_module.items():
            mod_arg = module if module else None
            log.info(
                "测试验证: %s [%s] — %d 个测试类",
                repo_path.name,
                module or "root",
                len(classes),
            )
            result = run_check(repo_path, classes, mod_arg)
            total_tested += len(classes)

            if not result["passed"]:
                phase = result["phase"]
                phase_label = "编译" if phase == "compile" else "运行"
                errors.append(
                    f"BLOCKED: {repo_path.name}/{module or 'root'} 测试{phase_label}失败 ({len(classes)} 个测试类)"
                )
                if result["error_summary"]:
                    errors.append(f"  错误摘要:\n{result['error_summary']}")

    if total_tested == 0 and not errors:
        errors.append("BLOCKED: Q05b 未在任何业务仓库中发现新增测试文件")

    return errors


def _run_ts_gate(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
) -> list[str]:
    """TypeScript 路径：对每个 repo 调用 TypeScriptProvider.run_tests()."""
    from qualix.languages.typescript.provider import TypeScriptProvider
    from qualix.quality.checks.ts_coverage_parser import parse_coverage_summary

    errors: list[str] = []
    for repo_str in code_repos:
        repo_path = Path(repo_str).expanduser().resolve()
        if not repo_path.is_dir():
            errors.append(f"BLOCKED: 代码仓库路径不存在: {repo_path}")
            continue

        log.info("Q05b TS gate: running tests in %s", repo_path.name)
        result = TypeScriptProvider().run_tests(repo_path)
        if not result["success"]:
            errors.append(
                "BLOCKED: Q05b test execution: TypeScript tests failed\n"
                + result["stdout"][:500]
            )
            continue

        # 可选：记录覆盖率信息（不阻断）
        coverage_path = repo_path / "coverage" / "coverage-summary.json"
        cov = parse_coverage_summary(coverage_path)
        if cov:
            log.info(
                "TS coverage: lines=%.1f%%, branches=%.1f%%",
                cov["lines_pct"],
                cov["branches_pct"],
            )

    return errors


def _run_go_gate(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
) -> list[str]:
    """Go 路径：compile_check + go test ./... -json."""
    import json as _json

    from qualix.languages.go.provider import GoProvider

    errors: list[str] = []
    for repo_str in code_repos:
        repo_path = Path(repo_str).expanduser().resolve()
        if not repo_path.is_dir():
            errors.append(f"BLOCKED: 代码仓库路径不存在: {repo_path}")
            continue

        log.info("Q05b Go gate: compile check in %s", repo_path.name)
        compile_result = GoProvider().compile_check(repo_path)
        if not compile_result.passed:
            errors.append(f"BLOCKED: Q05b compile: {compile_result.error_summary}")
            continue

        # go test ./... -json
        log.info("Q05b Go gate: running tests in %s", repo_path.name)
        try:
            proc = subprocess.run(
                ["go", "test", "./...", "-json", "-count=1", "-timeout=300s"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=330,
            )
        except FileNotFoundError:
            errors.append("BLOCKED: Q05b test execution: go not found")
            continue
        except subprocess.TimeoutExpired:
            errors.append("BLOCKED: Q05b test execution: Go tests timed out (>330s)")
            continue

        # 解析 JSON 行，收集失败测试名
        failing: list[str] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if entry.get("Action") == "fail" and entry.get("Test"):
                failing.append(entry["Test"])

        if failing:
            errors.append(
                "BLOCKED: Q05b test execution: Go tests failed — "
                + ", ".join(failing[:5])
            )

        if proc.returncode != 0 and not failing:
            errors.append(
                "BLOCKED: Q05b test execution: go test exited with code "
                + str(proc.returncode)
                + (f" — {proc.stderr[:200]}" if proc.stderr.strip() else "")
            )

    return errors
