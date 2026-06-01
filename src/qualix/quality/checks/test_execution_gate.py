"""Q05b 单测编译+运行铁律 gate：生成的测试必须编译通过且运行无错误."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from qualix.json_utils import load_json
from qualix.log import get_logger

from .compile_check import _build_env_for_java, detect_build_tool

log = get_logger(__name__)

_TEST_TIMEOUT = 300


def _discover_new_test_classes(code_repo: Path) -> list[dict[str, str]]:
    """从 git diff + git status 发现新增/修改的测试文件（含 untracked），返回 [{class_name, module, path}].

    三路来源取并集（兼容已提交和未提交两种场景）：
    1. git diff origin/master...HEAD：已提交但相对 master 新增（feature branch 主场景）
    2. git diff --name-only HEAD：staged 但未提交的修改
    3. git status --porcelain：untracked 新文件
    """
    all_paths: set[str] = set()
    try:
        # 路径 1：已提交相对 origin/master 的新增文件（feature branch 提交后的主要来源）
        r_branch = subprocess.run(
            ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r_branch.returncode == 0:
            all_paths.update(p.strip() for p in r_branch.stdout.splitlines() if p.strip())

        # 路径 2：staged + modified（相对 HEAD，含未提交的修改）
        r_diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r_diff.returncode == 0:
            all_paths.update(p.strip() for p in r_diff.stdout.splitlines() if p.strip())

        # 路径 3：untracked 新文件（?? 状态）和已 staged 新文件（A 状态）
        r_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r_status.returncode == 0:
            for line in r_status.stdout.splitlines():
                if len(line) < 4:
                    continue
                status = line[:2].strip()
                path_str = line[3:].strip()
                if status in ("??", "A", "AM", "M", "MM") and path_str:
                    all_paths.add(path_str)
    except (subprocess.TimeoutExpired, OSError):
        return []

    lines = list(all_paths)

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
    cmd = f"mvn test -q --batch-mode -o -Dtest={test_pattern} -Dsurefire.useFile=false -Dsurefire.failIfNoSpecifiedTests=false"
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
    from qualix.languages.typescript.provider import TypeScriptProvider

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


from ._test_execution_backends import _run_go_gate, _run_java_gate, _run_ts_gate

__all__ = [
    "_run_go_gate",
    "_run_java_gate",
    "_run_ts_gate",
]


def check_q05_test_execution(
    output_dir: Path,
    project_id: str,
    language_provider: Any = None,
) -> list[str]:
    """Q05b 铁律 gate：对每个业务仓库编译+运行新增测试.

    Args:
        output_dir: Qualix 输出目录
        project_id: 项目 ID
        language_provider: LanguageProvider 实例（可选）。传入时按语言路由到对应
            _run_ts_gate / _run_go_gate / _run_java_gate；省略时自动检测。

    Returns:
        BLOCKED 错误列表。空列表 = 全部通过。
    """
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import internal_dir as _internal_dir

    phase_def = PHASE_DEFS.get("Q05b")
    if not phase_def:
        return []

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs_path = int_dir / "_inputs.json"
    if not inputs_path.exists():
        # _inputs.json 缺失意味着 Phase 未通过 qualix-run execute 启动（手动模式）
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

    # 确定语言路由
    lang_id: str | None = None
    if language_provider is not None:
        lang_id = getattr(language_provider, "language_id", None)
    else:
        # 从 inputs 或第一个仓库自动检测
        lang_id = inputs_data.get("language_id")
        if not lang_id and code_repos:
            first_repo = Path(code_repos[0]).expanduser().resolve()
            if first_repo.is_dir():
                try:
                    from qualix.languages import get_registry

                    detected = get_registry().detect(first_repo)
                    if detected:
                        lang_id = detected.language_id
                except Exception:
                    pass

    if lang_id == "typescript":
        return _run_ts_gate(code_repos)
    if lang_id == "go":
        return _run_go_gate(code_repos)

    # Java 路径（默认，含 lang_id=None）
    return _run_java_gate(code_repos)


def check_q05b_coverage_increase(output_dir: Path, project_id: str) -> list[str]:
    """Q05b 覆盖率净增检查：新增测试后覆盖率不应下降。

    返回 SOFT 级警告（不阻断 finalize，无覆盖率报告时返回 []）。
    """
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json

    q05b_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q05b", "Q05b")
    inputs = load_json(q05b_dir / "_inputs.json") or {}
    coverage_report = inputs.get("coverage_report")
    if not coverage_report:
        return []

    from pathlib import Path as _Path
    report_path = _Path(coverage_report)
    if not report_path.exists():
        return [f"WARNING: coverage_report 路径不存在: {coverage_report}"]

    try:
        from qualix.quality.checks.coverage_gate import parse_jacoco_xml
        current = parse_jacoco_xml(report_path)
    except Exception as e:
        return [f"WARNING: 覆盖率报告解析失败: {e}"]

    if not current:
        return []

    try:
        from qualix.quality.checks.coverage_gate import compute_incremental_coverage
        blast_path = q05b_dir / "_internal" / "_blast_radius.json"
        blast = load_json(blast_path) or {}
        changed_files = blast.get("changed_files", [])
        if not changed_files:
            return []
        incremental = compute_incremental_coverage(report_path, changed_files)
        if incremental is None:
            return []
        line_delta = incremental.get("line_delta", 0)
        if line_delta < -0.02:
            return [
                f"WARNING: 新增测试后增量行覆盖率下降 {abs(line_delta) * 100:.1f}%，"
                "请检查新增测试是否覆盖到目标代码"
            ]
    except Exception:
        pass

    return []
