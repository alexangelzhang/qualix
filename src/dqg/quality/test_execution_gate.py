"""Q05 单测编译+运行铁律 gate：生成的测试必须编译通过且运行无错误."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.log import get_logger
from dqg.quality.compile_check import _build_env_for_java, detect_build_tool

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
        if not line.endswith("Test.java") or "src/test/" not in line:
            continue
        class_name = Path(line).stem
        module = line.split("/src/test/")[0] if "/src/test/" in line else ""
        test_files.append(
            {
                "class_name": class_name,
                "module": module,
                "path": line,
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
) -> dict[str, Any]:
    """编译+运行指定测试类.

    Returns:
        {passed, phase, build_tool, test_classes, error_summary}
    """
    build_tool = detect_build_tool(code_repo)
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
        return []

    inputs_data = load_json(inputs_path)
    if not inputs_data:
        return []

    code_repos: list[str] = inputs_data.get("code_repos", [])
    if not code_repos and inputs_data.get("code_repo"):
        code_repos = [inputs_data["code_repo"]]
    if not code_repos:
        return []

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

        by_module = _group_by_module(test_files)
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
