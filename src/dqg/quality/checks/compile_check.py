"""Phase B 编译验证 gate：生成的单测代码必须通过编译.

在 finalize 前调用，编译失败则返回 BLOCKED 错误。
支持 Java (Maven/Gradle) 和 Go 项目。
通过 LanguageProvider 可扩展到 TypeScript/Python/Rust 等。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
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


def _detect_java_version(code_repo: Path) -> str | None:
    """从 pom.xml 检测目标 Java 版本.

    Returns:
        版本字符串如 "1.8", "11", "17", "21"，未检测到返回 None
    """
    pom = code_repo / "pom.xml"
    if not pom.exists():
        return None
    try:
        content = pom.read_text(encoding="utf-8")
        for pattern in [
            r"<maven\.compiler\.source>\s*(\S+?)\s*</maven\.compiler\.source>",
            r"<java\.version>\s*(\S+?)\s*</java\.version>",
            r"<source>\s*(\S+?)\s*</source>",
        ]:
            m = re.search(pattern, content)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None


def _resolve_java_home(target_version: str) -> str | None:
    """通过 /usr/libexec/java_home 查找匹配的 JDK 路径（macOS）.

    对 "1.8" 等短版本号，优先尝试 "1.8.0" 以避免匹配到 JavaAppletPlugin。

    Returns:
        JAVA_HOME 路径，找不到返回 None
    """
    if sys.platform != "darwin":
        return None

    # 尝试的版本号列表：精确版本优先
    candidates = [target_version]
    if target_version == "1.8":
        candidates = ["1.8.0", "1.8"]

    for ver in candidates:
        try:
            result = subprocess.run(
                ["/usr/libexec/java_home", "-v", ver],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                java_home = result.stdout.strip()
                # 排除 JavaAppletPlugin（不是完整 JDK）
                if java_home and Path(java_home).is_dir() and "JavaAppletPlugin" not in java_home:
                    return java_home
        except (subprocess.TimeoutExpired, OSError):
            pass
    return None


def _build_env_for_java(code_repo: Path) -> dict[str, str] | None:
    """为 Java 项目构建正确的 JAVA_HOME 环境.

    Returns:
        环境变量字典，无需调整时返回 None
    """
    target = _detect_java_version(code_repo)
    if not target:
        return None

    java_home = _resolve_java_home(target)
    if not java_home:
        log.warning("未找到 JDK %s，使用系统默认 JDK", target)
        return None

    current = os.environ.get("JAVA_HOME", "")
    if current and Path(current).resolve() == Path(java_home).resolve():
        return None

    log.info("JDK 版本切换: %s → %s (目标: %s)", current or "default", java_home, target)
    env = os.environ.copy()
    env["JAVA_HOME"] = java_home
    env["PATH"] = f"{java_home}/bin:{env.get('PATH', '')}"
    return env


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

    # Java 项目自动检测并切换 JDK 版本
    env = None
    if build_tool in ("maven", "gradle"):
        env = _build_env_for_java(code_repo)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(code_repo),
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT,
            shell=True,
            env=env,
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
        base = "mvn compile -q --batch-mode -o"
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
