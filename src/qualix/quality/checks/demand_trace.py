"""Demand-driven 代码路径追踪：从需求出发定位需审查的代码集合.

与 blast_radius（bottom-up: 代码变更→受影响调用方）互补，
demand_trace 是 top-down: SE→入口方法→调用链→需审查代码。

结合 code_semantic_search 的 SE→Code 映射和 blast_radius 的调用图。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qualix.json_utils import load_json, save_json
from qualix.log import get_logger

log = get_logger(__name__)


def trace_downstream(
    call_graph: dict[str, dict[str, Any]],
    entry_methods: list[str],
    max_depth: int = 3,
) -> dict[str, Any]:
    """从入口方法向下 BFS 追踪被调用方.

    Args:
        call_graph: blast_radius.build_call_graph_regex() 的输出
        entry_methods: 入口方法列表（格式 "ClassName.methodName"）
        max_depth: 最大追踪深度

    Returns:
        {
            "entry_methods": [...],
            "traced_methods": [{"method": str, "depth": int, "file": str, "line": int}],
            "traced_files": [...],
            "depth_distribution": {0: N, 1: N, ...},
        }
    """
    traced: list[dict[str, Any]] = []
    visited: set[str] = set()
    depth_dist: dict[int, int] = {}
    queue: list[tuple[str, int]] = [(m, 0) for m in entry_methods]

    while queue:
        method, depth = queue.pop(0)
        if method in visited or depth > max_depth:
            continue
        visited.add(method)
        depth_dist[depth] = depth_dist.get(depth, 0) + 1

        node = call_graph.get(method)
        if node:
            traced.append(
                {
                    "method": method,
                    "depth": depth,
                    "file": node.get("file", ""),
                    "line": node.get("line", 0),
                }
            )
            # 向下追踪 calls
            for callee in node.get("calls", []):
                if callee not in visited and callee in call_graph:
                    queue.append((callee, depth + 1))

    traced_files = sorted({t["file"] for t in traced if t["file"]})

    return {
        "entry_methods": entry_methods,
        "traced_methods": traced,
        "traced_files": traced_files,
        "depth_distribution": depth_dist,
    }


def build_demand_trace(
    output_dir: Path,
    project_id: str,
    repo_path: str,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
    max_depth: int = 3,
) -> dict[str, Any] | None:
    """完整 demand-driven 追踪流程.

    1. 加载 SE→Code 映射获取入口方法
    2. 构建调用图
    3. 从入口方法向下 BFS
    4. 合并 blast_radius 结果（如果存在）

    Returns:
        完整追踪结果或 None
    """
    from qualix.constants import PHASE_DIR_MAP

    # 1. 加载 SE→Code 映射
    dir_suffix = PHASE_DIR_MAP.get("Q07", "phaseD")
    int_dir = output_dir / project_id / dir_suffix / "_internal"

    se_mapping_path = int_dir / "_se_code_mapping.json"
    if not se_mapping_path.exists():
        # 尝试从 Q06 目录加载
        dir_suffix_c = PHASE_DIR_MAP.get("Q06", "phaseC")
        se_mapping_path = output_dir / project_id / dir_suffix_c / "_internal" / "_se_code_mapping.json"

    se_data = load_json(se_mapping_path)
    if not se_data:
        log.info("Demand trace: no SE→Code mapping found, skipping")
        return None

    # 提取入口方法
    entry_methods = _extract_entry_methods(se_data)
    if not entry_methods:
        log.info("Demand trace: no entry methods extracted from SE mapping")
        return None

    # 2. 构建调用图
    from .blast_radius import build_call_graph_regex

    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return None

    # 获取所有 Java 文件
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "*.java"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        all_java = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        all_java = []

    if not all_java:
        return None

    call_graph = build_call_graph_regex(repo, all_java)

    # 3. 向下 BFS
    trace_result = trace_downstream(call_graph, entry_methods, max_depth)

    # 4. 合并 blast_radius（如果存在）
    blast_path = int_dir / "_blast_radius.json"
    if not blast_path.exists():
        dir_suffix_c = PHASE_DIR_MAP.get("Q06", "phaseC")
        blast_path = output_dir / project_id / dir_suffix_c / "_internal" / "_blast_radius.json"

    blast_data = load_json(blast_path)
    overlap = _compute_overlap(trace_result, blast_data) if blast_data else {}

    trace_result["blast_radius_overlap"] = overlap
    trace_result["se_mapping_source"] = str(se_mapping_path)

    log.info(
        "Demand trace: %d entry methods → %d traced methods across %d files",
        len(entry_methods),
        len(trace_result["traced_methods"]),
        len(trace_result["traced_files"]),
    )

    return trace_result


def _extract_entry_methods(se_data: dict[str, Any]) -> list[str]:
    """从 SE→Code 映射中提取入口方法名."""
    entries: list[str] = []
    seen: set[str] = set()

    for mapping in se_data.get("mappings", []):
        if mapping.get("coverage") != "FOUND":
            continue
        for match in mapping.get("code_matches", []):
            cls = match.get("class", "")
            method = match.get("method", "")
            if cls and method:
                key = f"{cls}.{method}"
                if key not in seen:
                    seen.add(key)
                    entries.append(key)

    return entries


def _compute_overlap(
    trace: dict[str, Any],
    blast: dict[str, Any],
) -> dict[str, Any]:
    """计算 demand trace 与 blast radius 的重叠."""
    trace_methods = {t["method"] for t in trace.get("traced_methods", [])}
    blast_changed = set(blast.get("changed_methods", []))
    blast_affected = set(blast.get("affected_callers", []))
    blast_all = blast_changed | blast_affected

    overlap = trace_methods & blast_all
    trace_only = trace_methods - blast_all
    blast_only = blast_all - trace_methods

    return {
        "overlap_count": len(overlap),
        "trace_only_count": len(trace_only),
        "blast_only_count": len(blast_only),
        "overlap_methods": sorted(overlap)[:20],
        "trace_only_methods": sorted(trace_only)[:20],
        "recommendation": (
            "HIGH_CONFIDENCE" if overlap else "COMPLEMENTARY" if trace_only and blast_only else "TRACE_ONLY"
        ),
    }


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def write_demand_trace(
    output_dir: Path,
    project_id: str,
    repo_path: str,
    base_branch: str = "master",
    feature_branch: str = "HEAD",
) -> Path | None:
    """计算并写入 demand trace 到 Phase D 目录."""
    trace = build_demand_trace(
        output_dir,
        project_id,
        repo_path,
        base_branch,
        feature_branch,
    )
    if not trace:
        return None

    from qualix.constants import PHASE_DIR_MAP

    dir_suffix = PHASE_DIR_MAP.get("Q07", "phaseD")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    json_path = int_dir / "_demand_trace.json"
    save_json(json_path, trace)

    md_path = int_dir / "_demand_trace.md"
    md_path.write_text(_render_trace_md(trace), encoding="utf-8")

    return json_path


def _render_trace_md(trace: dict[str, Any]) -> str:
    """渲染 demand trace 为 Markdown."""
    lines = [
        "## DEMAND_TRACE — 需求驱动代码路径追踪（自动分析）",
        "",
        f"**入口方法**: {len(trace.get('entry_methods', []))} 个（来自 SE→Code 映射）",
        f"**追踪到**: {len(trace.get('traced_methods', []))} 个方法，跨 {len(trace.get('traced_files', []))} 个文件",
        "",
    ]

    # 深度分布
    dist = trace.get("depth_distribution", {})
    if dist:
        lines.append("### 调用深度分布")
        for depth in sorted(dist.keys(), key=int):
            lines.append(f"- 深度 {depth}: {dist[depth]} 个方法")
        lines.append("")

    # 入口方法
    entries = trace.get("entry_methods", [])
    if entries:
        lines.append("### 入口方法（SE 关联）")
        for m in entries[:15]:
            lines.append(f"- `{m}`")
        lines.append("")

    # 追踪到的文件
    files = trace.get("traced_files", [])
    if files:
        lines.append("### 需审查文件")
        for f in files[:20]:
            lines.append(f"- `{f}`")
        lines.append("")

    # Blast radius 重叠
    overlap = trace.get("blast_radius_overlap", {})
    if overlap:
        lines.append("### 与 Blast Radius 交叉分析")
        lines.append(f"- 重叠: {overlap.get('overlap_count', 0)} 个方法")
        lines.append(f"- 仅 demand trace: {overlap.get('trace_only_count', 0)} 个方法")
        lines.append(f"- 仅 blast radius: {overlap.get('blast_only_count', 0)} 个方法")
        lines.append(f"- 置信度: **{overlap.get('recommendation', 'UNKNOWN')}**")

    return "\n".join(lines)
