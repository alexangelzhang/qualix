"""Blast radius 分析：代码改动 → 受影响的 callers/dependents/tests.

基于 tree-sitter Java AST 构建调用图，结合 git diff 计算影响范围。
输出注入 Phase C 审计 prompt，让 Judge 知道"这次改动可能破坏哪些已有覆盖"。

调用图按文件 hash 缓存（.dqg/call_graph_cache.json），只对 git diff 涉及的文件重新计算。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from dqg.json_utils import save_json
from dqg.log import get_logger

log = get_logger(__name__)

_CALL_GRAPH_CACHE_FILE = ".dqg/call_graph_cache.json"


def _file_hash(path: Path) -> str:
    """Compute SHA256 of file content (first 64KB for speed)."""
    try:
        content = path.read_bytes()[:65536]
        return hashlib.sha256(content).hexdigest()[:16]
    except OSError:
        return ""


def _load_call_graph_cache(repo_path: Path) -> dict[str, Any]:
    """Load per-file call graph cache from .dqg/call_graph_cache.json."""
    cache_path = repo_path / _CALL_GRAPH_CACHE_FILE
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug("Failed to load call graph cache: %s", e)
        return {}


def _save_call_graph_cache(repo_path: Path, cache: dict[str, Any]) -> None:
    """Persist call graph cache."""
    cache_path = repo_path / _CALL_GRAPH_CACHE_FILE
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        save_json(cache_path, cache)
    except Exception as e:
        log.debug("Failed to save call graph cache: %s", e)


def get_changed_files(
    repo_path: Path,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
) -> list[str]:
    """获取两个分支间变更的 Java 文件列表."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...{feature_branch}", "--", "*.java"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception as e:
        log.debug("get_changed_files failed: %s", e)
        return []


def get_changed_methods(
    repo_path: Path,
    file_path: str,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
) -> list[str]:
    """获取文件中变更的方法名（通过 git diff -U0 解析 @@ 行）."""
    try:
        result = subprocess.run(
            ["git", "diff", "-U0", f"{base_branch}...{feature_branch}", "--", file_path],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        methods: list[str] = []
        # 从 @@ 行提取函数名（git diff 的 -p 格式会在 @@ 后显示函数签名）
        for line in result.stdout.splitlines():
            m = re.match(r"@@.*@@\s+.*?(\w+)\s*\(", line)
            if m:
                methods.append(m.group(1))
        return list(dict.fromkeys(methods))  # 去重保序
    except Exception as e:
        log.debug("get_changed_methods failed for %s: %s", file_path, e)
        return []


def build_call_graph_regex(
    repo_path: Path,
    java_files: list[str],
) -> dict[str, dict[str, Any]]:
    """用正则构建简化调用图（tree-sitter 不可用时的 fallback）.

    按文件 hash 缓存，只对内容变化的文件重新计算。

    Returns:
        {
            "ClassName.methodName": {
                "file": "path/to/File.java",
                "line": 42,
                "calls": ["OtherClass.otherMethod", ...],
                "called_by": [],  # 后续填充
            }
        }
    """
    cache = _load_call_graph_cache(repo_path)
    graph: dict[str, dict[str, Any]] = {}
    cache_updated = False

    # 方法定义正则
    method_def_re = re.compile(
        r"(?:public|private|protected|static|\s)+\s+"
        r"(?:\w+(?:<[^>]+>)?)\s+"
        r"(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+(?:\s*,\s*\w+)*)?\s*\{",
    )
    # 方法调用正则
    method_call_re = re.compile(r"(\w+)\.(\w+)\s*\(")

    for rel_path in java_files:
        full_path = repo_path / rel_path
        if not full_path.exists():
            continue

        fhash = _file_hash(full_path)
        cache_key = f"{rel_path}:{fhash}"
        if cache_key in cache:
            for method, info in cache[cache_key].items():
                graph[method] = {**info, "called_by": []}
            continue

        try:
            source = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 提取类名
        class_match = re.search(r"class\s+(\w+)", source)
        class_name = class_match.group(1) if class_match else Path(rel_path).stem

        lines = source.splitlines()
        current_method: str | None = None
        brace_depth = 0

        for i, line in enumerate(lines):
            # 检测方法定义
            m = method_def_re.search(line)
            if m and brace_depth <= 1:
                current_method = f"{class_name}.{m.group(1)}"
                if current_method not in graph:
                    graph[current_method] = {
                        "file": rel_path,
                        "line": i + 1,
                        "calls": [],
                        "called_by": [],
                    }

            # 跟踪大括号深度
            brace_depth += line.count("{") - line.count("}")

            # 提取方法调用
            if current_method:
                for call_match in method_call_re.finditer(line):
                    callee = f"{call_match.group(1)}.{call_match.group(2)}"
                    if callee != current_method:
                        graph[current_method]["calls"].append(callee)

        # 存入缓存（不含 called_by，后续填充）
        file_methods = {k: v for k, v in graph.items() if v.get("file") == rel_path}
        if file_methods:
            cache[cache_key] = file_methods
            cache_updated = True

    # 填充 called_by（反向索引）
    for caller, info in graph.items():
        for callee in info["calls"]:
            if callee in graph:
                graph[callee]["called_by"].append(caller)

    # 去重
    for info in graph.values():
        info["calls"] = list(dict.fromkeys(info["calls"]))
        info["called_by"] = list(dict.fromkeys(info["called_by"]))

    if cache_updated:
        _save_call_graph_cache(repo_path, cache)

    return graph


def compute_blast_radius(
    repo_path: Path,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
) -> dict[str, Any]:
    """计算代码改动的影响范围.

    Returns:
        {
            "changed_files": [...],
            "changed_methods": [...],
            "affected_callers": [...],
            "affected_tests": [...],
            "risk_summary": "..."
        }
    """
    from concurrent.futures import ThreadPoolExecutor

    changed_files = get_changed_files(repo_path, base_branch, feature_branch)
    if not changed_files:
        return {"changed_files": [], "changed_methods": [], "affected_callers": [], "affected_tests": [], "risk_summary": "No Java changes detected"}

    # 并行：收集变更方法 + 列出所有 Java 文件
    def _collect_changed_methods():
        methods: list[str] = []
        # 每个文件的 git diff 也并行
        with ThreadPoolExecutor(max_workers=min(len(changed_files), 4)) as inner_pool:
            futures = {
                inner_pool.submit(get_changed_methods, repo_path, f, base_branch, feature_branch): f
                for f in changed_files
            }
            for fut in futures:
                f = futures[fut]
                class_name = Path(f).stem
                methods.extend(f"{class_name}.{m}" for m in fut.result())
        return methods

    def _list_all_java():
        try:
            result = subprocess.run(
                ["git", "ls-files", "*.java"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.splitlines() if f.strip()]
        except Exception as e:
            log.debug("_list_all_java failed: %s", e)
        return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_methods = pool.submit(_collect_changed_methods)
        fut_java = pool.submit(_list_all_java)
        changed_methods = fut_methods.result()
        all_java = fut_java.result()

    if not all_java:
        return {
            "changed_files": changed_files,
            "changed_methods": changed_methods,
            "affected_callers": [],
            "affected_tests": [],
            "risk_summary": f"{len(changed_files)} files changed, call graph unavailable",
        }

    graph = build_call_graph_regex(repo_path, all_java)

    # 从变更方法出发，BFS 找受影响的 callers（最多 2 层）
    affected: set[str] = set()
    queue = list(changed_methods)
    depth_map: dict[str, int] = {m: 0 for m in changed_methods}

    while queue:
        current = queue.pop(0)
        current_depth = depth_map.get(current, 0)
        if current_depth >= 2:
            continue
        node = graph.get(current)
        if not node:
            continue
        for caller in node["called_by"]:
            if caller not in affected and caller not in changed_methods:
                affected.add(caller)
                depth_map[caller] = current_depth + 1
                queue.append(caller)

    # 分离测试和非测试
    affected_tests = [m for m in affected if "Test" in m or "test" in m.split(".")[-1]]
    affected_callers = [m for m in affected if m not in affected_tests]

    risk_summary = (
        f"{len(changed_files)} files, {len(changed_methods)} methods changed; "
        f"{len(affected_callers)} callers, {len(affected_tests)} tests potentially affected"
    )

    return {
        "changed_files": changed_files,
        "changed_methods": changed_methods[:50],
        "affected_callers": affected_callers[:30],
        "affected_tests": affected_tests[:30],
        "risk_summary": risk_summary,
    }


def write_blast_radius(
    output_dir: Path,
    project_id: str,
    code_repo: str,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
) -> Path | None:
    """计算并写入影响范围分析到 Phase C 目录."""
    repo_path = Path(code_repo).expanduser().resolve()
    if not repo_path.is_dir():
        return None

    radius = compute_blast_radius(repo_path, base_branch, feature_branch)
    if not radius.get("changed_files"):
        return None

    from dqg.constants import PHASE_DIR_MAP
    dir_suffix = PHASE_DIR_MAP.get("Q06", "phaseC")
    phase_c_dir = output_dir / project_id / dir_suffix
    phase_c_dir.mkdir(parents=True, exist_ok=True)
    int_dir = phase_c_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    json_path = int_dir / "_blast_radius.json"
    save_json(json_path, radius)

    md_path = int_dir / "_blast_radius.md"
    md_path.write_text(_render_blast_radius_md(radius), encoding="utf-8")

    log.info("Blast radius: %s", radius["risk_summary"])
    return json_path


def _render_blast_radius_md(radius: dict[str, Any]) -> str:
    """渲染影响范围为 Markdown."""
    lines = [
        "## BLAST_RADIUS — 代码改动影响范围（自动分析）",
        "",
        f"**摘要**: {radius['risk_summary']}",
        "",
    ]

    if radius.get("changed_methods"):
        lines.append("### 变更方法")
        for m in radius["changed_methods"][:20]:
            lines.append(f"- `{m}`")
        lines.append("")

    if radius.get("affected_callers"):
        lines.append("### 受影响的调用方（可能被破坏）")
        for m in radius["affected_callers"][:15]:
            lines.append(f"- `{m}`")
        lines.append("")

    if radius.get("affected_tests"):
        lines.append("### 受影响的测试（需要验证）")
        for m in radius["affected_tests"][:15]:
            lines.append(f"- `{m}`")
        lines.append("")

    if not radius.get("affected_callers") and not radius.get("affected_tests"):
        lines.append("*未检测到受影响的调用方或测试*")

    return "\n".join(lines)
