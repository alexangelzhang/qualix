"""Q05 单测编译+运行铁律 gate：生成的测试必须编译通过且运行无错误."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.log import get_logger

from .compile_check import _build_env_for_java, detect_build_tool

log = get_logger(__name__)

_TEST_TIMEOUT = 300


def _discover_new_test_classes(code_repo: Path) -> list[dict[str, str]]:
    """从 git diff 发现新增/修改的测试文件，返回 [{class_name, module, path}]."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(code_repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [line[3:].strip() for line in result.stdout.splitlines() if line.strip()]
        else:
            lines = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, OSError):
        return []

    test_files: list[dict[str, str]] = []
    for line in lines:
        line = line.strip()
        is_java_test = line.endswith("Test.java") and "src/test/" in line
        is_kotlin_test = line.endswith("Test.kt") and "src/test/" in line
        is_ts_test = any(line.endswith(ext) for ext in (".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
        if not (is_java_test or is_kotlin_test or is_ts_test):
            continue
        class_name = Path(line).stem
        module = line.split("/src/test/")[0] if "/src/test/" in line else ""
        test_files.append(
            {
                "class_name": class_name,
                "module": module,
                "path": line,
                "language": "typescript" if is_ts_test else "java",
            }
        )
    return test_files


def _group_by_module(test_files: list[dict[str, str]]) -> dict[str, list[str]]:
    """按 Maven 模块分组测试类名."""
    groups: dict[str, list[str]] = {}
    for tf in test_files:
        module = tf["module"]
        groups.setdefault(module, []).append(tf["class_name"])
    return groups


def run_test_check(
    code_repo: Path,
    test_classes: list[str],
    module: str | None = None,
    language: str = "java",
) -> dict[str, Any]:
    """编译+运行指定测试类，支持 Java（Maven）和 TypeScript（Jest/Vitest）.

    Returns:
        {passed, phase, build_tool, test_classes, error_summary}
    """
    build_tool = detect_build_tool(code_repo)

    # TypeScript 路径
    if language == "typescript":
        return _run_ts_test_check(code_repo, test_classes)

    # Java/Maven 路径（原有逻辑）
    if not build_tool or build_tool != "maven":
        return {
            "passed": True,
            "phase": "skip",
            "build_tool": build_tool or "unknown",
            "test_classes": test_classes,
            "error_summary": f"非 Maven 项目，跳过测试验证（{build_tool}）",
        }

    env = _build_env_for_java(code_repo)

    test_pattern = ",".join(test_classes)
    cmd = f"mvn test -q --batch-mode -Dtest={test_pattern} -Dsurefire.useFile=false -Dsurefire.failIfNoSpecifiedTests=false"
    if module:
        cmd += f" -pl {module} -am"

    try:
        tr = subprocess.run(
            cmd,
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
            shell=True,
            env=env,
        )
        if tr.returncode != 0:
            summary = _extract_errors(tr.stderr + tr.stdout)
            phase = "compile" if "Compilation failure" in (tr.stderr + tr.stdout) else "test"
            return {
                "passed": False,
                "phase": phase,
                "build_tool": build_tool,
                "test_classes": test_classes,
                "error_summary": summary or "测试失败",
            }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "phase": "test",
            "build_tool": build_tool,
            "test_classes": test_classes,
            "error_summary": f"测试超时（>{_TEST_TIMEOUT}s）",
        }

    return {
        "passed": True,
        "phase": "test",
        "build_tool": build_tool,
        "test_classes": test_classes,
        "error_summary": "",
    }


def _run_ts_test_check(code_repo: Path, test_files: list[str]) -> dict[str, Any]:
    """TypeScript 测试执行：用 TypeScriptProvider.run_tests()."""
    from dqg.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()

    # 无 package.json / tsconfig.json → skip（不 BLOCK）
    if not (code_repo / "package.json").exists() and not (code_repo / "tsconfig.json").exists():
        return {
            "passed": True,
            "phase": "skip",
            "build_tool": "npm",
            "test_classes": test_files,
            "error_summary": "无 package.json / tsconfig.json，跳过 TS 测试验证",
        }

    result = provider.run_tests(code_repo)
    if not result["success"]:
        summary = _extract_errors(result["stdout"] + result["stderr"])
        return {
            "passed": False,
            "phase": "test",
            "build_tool": "npm",
            "test_classes": test_files,
            "error_summary": summary or result["stderr"][:500] or "TS 测试失败",
        }
    return {
        "passed": True,
        "phase": "test",
        "build_tool": "npm",
        "test_classes": test_files,
        "error_summary": "",
    }


def _extract_errors(output: str) -> str:
    """提取编译/测试错误摘要（最多 5 行）."""
    lines = output.splitlines()
    errors: list[str] = []
    for line in lines:
        s = line.strip()
        if any(kw in s for kw in ("[ERROR]", "FAILURE", "Tests run:", "CompilationFailure")):
            errors.append(s)
        if len(errors) >= 5:
            break
    if not errors:
        tail = [line.strip() for line in lines[-10:] if line.strip()]
        errors = tail[-3:]
    return "\n".join(errors)


def check_q05_test_execution(
    output_dir: Path,
    project_id: str,
) -> list[str]:
    """Q05 铁律 gate：对每个业务仓库编译+运行新增测试.

    Returns:
        BLOCKED 错误列表。空列表 = 全部通过。
    """
    from dqg.core.phase_registry import PHASE_DEFS
    from dqg.core.state_machine import internal_dir as _internal_dir

    phase_def = PHASE_DEFS.get("Q05")
    if not phase_def:
        return []

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs_path = int_dir / "_inputs.json"
    if not inputs_path.exists():
        # _inputs.json 缺失意味着 Phase 未通过 dqg-run execute 启动（手动模式）
        # 无法确认测试已编译通过，返回 WARNING 而非静默跳过
        return ["WARNING: _inputs.json 不存在，测试执行 gate 已跳过（请确认单测代码已通过编译）"]

    inputs_data = load_json(inputs_path)
    if not inputs_data:
        return ["WARNING: _inputs.json 为空，测试执行 gate 已跳过"]

    code_repos: list[str] = inputs_data.get("code_repos", [])
    if not code_repos and inputs_data.get("code_repo"):
        code_repos = [inputs_data["code_repo"]]
    if not code_repos:
        return ["WARNING: _inputs.json 中未配置 code_repo，测试执行 gate 已跳过"]

    errors: list[str] = []
    total_tested = 0

    for repo_str in code_repos:
        repo_path = Path(repo_str).expanduser().resolve()
        if not repo_path.is_dir():
            errors.append(f"BLOCKED: 代码仓库路径不存在: {repo_path}")
            continue

        test_files = _discover_new_test_classes(repo_path)
        if not test_files:
            log.info("仓库 %s 无新增测试文件，跳过", repo_path.name)
            continue

        # 按语言分组：TS 文件整批执行，Java 文件按 Maven 模块分组
        ts_files = [tf for tf in test_files if tf.get("language") == "typescript"]
        java_files = [tf for tf in test_files if tf.get("language") != "typescript"]

        if ts_files:
            ts_paths = [tf["path"] for tf in ts_files]
            log.info("测试验证(TS): %s — %d 个测试文件", repo_path.name, len(ts_paths))
            result = run_test_check(repo_path, ts_paths, language="typescript")
            total_tested += len(ts_paths)
            if not result["passed"]:
                errors.append(f"BLOCKED: {repo_path.name} TS 测试失败 ({len(ts_paths)} 个文件)")
                if result["error_summary"]:
                    errors.append(f"  错误摘要:\n{result['error_summary']}")

        by_module = _group_by_module(java_files)
        for module, classes in by_module.items():
            mod_arg = module if module else None
            log.info(
                "测试验证: %s [%s] — %d 个测试类",
                repo_path.name,
                module or "root",
                len(classes),
            )
            result = run_test_check(repo_path, classes, mod_arg)
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
        errors.append("BLOCKED: Q05 未在任何业务仓库中发现新增测试文件")

    return errors
