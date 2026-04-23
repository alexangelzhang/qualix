"""Phase B 编译验证 gate：生成的单测代码必须通过编译.

在 finalize 前调用，编译失败则返回 BLOCKED 错误。
支持 Java (Maven/Gradle) 和 Go 项目。
通过 LanguageProvider 可扩展到 TypeScript/Python/Rust 等。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# 编译超时（秒）
_COMPILE_TIMEOUT = 120


def detect_build_tool(code_repo: Path) -> str | None:
    """检测代码仓库的构建工具类型.

    Returns:
        "maven" | "gradle" | "go" | None
    """
    if (code_repo / "pom.xml").exists():
        return "maven"
    if (code_repo / "build.gradle").exists() or (code_repo / "build.gradle.kts").exists():
        return "gradle"
    if (code_repo / "go.mod").exists():
        return "go"
    return None


def run_compile_check(
    code_repo: Path,
    module: str | None = None,
) -> dict[str, Any]:
    """执行编译检查.

    Args:
        code_repo: 代码仓库根目录
        module: Maven 子模块名（可选，如 "service-impl"）

    Returns:
        {
            "passed": bool,
            "build_tool": str,
            "command": str,
            "stdout": str,
            "stderr": str,
            "error_summary": str  # 编译失败时的摘要
        }
    """
    build_tool = detect_build_tool(code_repo)
    if not build_tool:
        return {
            "passed": True,
            "build_tool": "unknown",
            "command": "",
            "stdout": "",
            "stderr": "",
            "error_summary": "未检测到构建工具，跳过编译检查",
        }

    cmd = _build_compile_command(build_tool, module)
    log.info("编译检查: %s (cwd=%s)", cmd, code_repo)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT,
            shell=True,
        )
        passed = result.returncode == 0
        error_summary = ""
        if not passed:
            error_summary = _extract_compile_errors(result.stderr + result.stdout, build_tool)

        return {
            "passed": passed,
            "build_tool": build_tool,
            "command": cmd,
            "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
            "error_summary": error_summary,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "build_tool": build_tool,
            "command": cmd,
            "stdout": "",
            "stderr": "",
            "error_summary": f"编译超时（>{_COMPILE_TIMEOUT}s）",
        }
    except Exception as exc:
        return {
            "passed": False,
            "build_tool": build_tool,
            "command": cmd,
            "stdout": "",
            "stderr": str(exc),
            "error_summary": f"编译执行异常: {exc}",
        }


def _build_compile_command(build_tool: str, module: str | None) -> str:
    """构建编译命令."""
    if build_tool == "maven":
        base = "mvn compile -q --batch-mode"
        if module:
            return f"{base} -pl {module} -am"
        return base
    if build_tool == "gradle":
        return "./gradlew compileJava -q --no-daemon"
    if build_tool == "go":
        return "go build ./..."
    return ""


def _extract_compile_errors(output: str, build_tool: str) -> str:
    """从编译输出中提取关键错误信息（最多 5 条）."""
    lines = output.splitlines()
    errors: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        if build_tool in ("maven", "gradle"):
            # Java 编译错误格式: [ERROR] /path/File.java:[line,col] error: ...
            if ("[ERROR]" in line_stripped and ".java:" in line_stripped) or (
                "error:" in line_stripped.lower() and ".java" in line_stripped
            ):
                errors.append(line_stripped)
        elif (
            build_tool == "go"
            and ".go:" in line_stripped
            and ("undefined" in line_stripped or "cannot" in line_stripped or "error" in line_stripped.lower())
        ):
            errors.append(line_stripped)

        if len(errors) >= 5:
            break

    if not errors:
        # fallback: 取最后几行非空内容
        tail = [line.strip() for line in lines[-10:] if line.strip()]
        errors = tail[-3:]

    return "\n".join(errors)


def check_phase_b_compilation(
    output_dir: Path,
    project_id: str,
    code_repo: str | None = None,
    language_provider: Any = None,
) -> list[str]:
    """Phase B finalize 时的编译验证 gate.

    Args:
        output_dir: DQG 输出目录
        project_id: 项目 ID
        code_repo: 代码仓库路径（可选，从 state 或环境推断）
        language_provider: LanguageProvider 实例（可选，优先使用）

    Returns:
        错误列表。BLOCKED 前缀的错误会阻断 finalize。
    """
    if not code_repo:
        return []  # 未指定代码仓库，跳过编译检查

    repo_path = Path(code_repo).expanduser().resolve()
    if not repo_path.is_dir():
        return [f"BLOCKED: 代码仓库路径不存在: {repo_path}"]

    # 优先使用 Provider
    if language_provider is not None:
        cr = language_provider.compile_check(repo_path)
        if cr.skipped:
            log.info("编译检查跳过: %s (%s)", language_provider.language_id, cr.error_summary)
            return []
        if cr.passed:
            log.info("编译检查通过: %s (%s)", language_provider.language_id, cr.build_tool)
            return []
        errors = [
            f"BLOCKED: 生成的代码编译失败（{cr.build_tool}）。请修复编译错误后重新 finalize。",
        ]
        if cr.error_summary:
            errors.append(f"编译错误摘要:\n{cr.error_summary}")
        return errors

    # Fallback: 原有逻辑
    result = run_compile_check(repo_path)
    if result["passed"]:
        log.info("编译检查通过: %s", result["build_tool"])
        return []

    errors = [
        f"BLOCKED: 生成的代码编译失败（{result['build_tool']}）。请修复编译错误后重新 finalize。",
    ]
    if result["error_summary"]:
        errors.append(f"编译错误摘要:\n{result['error_summary']}")

    return errors
