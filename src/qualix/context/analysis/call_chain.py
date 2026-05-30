"""调用链深度分析：从 SE→Code 映射结果中提取 Domain 方法的实现和调用链.

解决"代码深读不够"问题：SE→Code mapping 给出 file:line 引用，但 AI 还需要
手动跟踪调用链才能发现隐藏复杂度（如 prev2Start 回溯、slot 聚合边界）。

本模块在 execute 阶段自动完成这一步：
1. 从 SE 映射中识别 Domain/App 层的主入口类（不是 Infrastructure Gateway）
2. 读取其主要方法的实现（前 2-3 层调用链）
3. 输出到 _code_call_chain.md，自动注入 bootstrap context
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

# 优先读取 Domain/App 层（领域逻辑在此；Infrastructure 只是外部调用）
_DOMAIN_LAYER_PATTERNS = [
    r"[/\\]domain[/\\]service[/\\]",
    r"[/\\]app[/\\]service[/\\]",
    r"[/\\]app[/\\]provider[/\\]",
    r"[/\\]domain[/\\]model[/\\]",
    r"[/\\]application[/\\]",
    r"[/\\]service[/\\]impl[/\\]",
]

# 跳过 Gateway/Infrastructure（外部调用，行为由下游决定）
_SKIP_LAYER_PATTERNS = [
    r"[/\\]infrastructure[/\\]gateway[/\\]",
    r"[/\\]gateway[/\\]impl[/\\]",
    r"[/\\]mapper[/\\]",
]

_MAX_METHOD_LINES = 60  # 每个方法最多输出多少行
_MAX_METHODS_PER_CLASS = 6  # 每个类最多输出多少方法
_MAX_CLASSES = 3  # 最多分析多少个类


def generate_call_chain_analysis(
    mapping: list[dict[str, Any]],
    repo_path: str,
) -> str:
    """从 SE→Code 映射生成调用链深度分析文档.

    Args:
        mapping: SE→Code 映射结果（来自 map_se_to_code）
        repo_path: 代码仓库根路径

    Returns:
        Markdown 格式的调用链分析文档
    """
    repo = Path(repo_path)
    if not repo.exists():
        return ""

    # 1. 从 mapping 中收集所有匹配的文件路径，按频次排序
    file_hits: dict[str, int] = defaultdict(int)
    for se_item in mapping:
        for match in se_item.get("matches", []):
            file_path = match.get("file_path", "")
            if file_path and _is_domain_layer(file_path):
                file_hits[file_path] += 1

    if not file_hits:
        log.debug("call_chain: no domain layer matches found, skipping")
        return ""

    # 2. 取频次最高的 top-N 文件
    top_files = sorted(file_hits.items(), key=lambda x: -x[1])[:_MAX_CLASSES]

    sections: list[str] = [
        "# 代码调用链深度分析",
        "",
        "> 自动从 SE→Code 映射结果中提取 Domain/App 层主要方法实现。",
        "> 目的：暴露隐藏的参数传递路径和分支条件，防止漏看关键逻辑。",
        "",
    ]

    analyzed = 0
    for rel_path, hit_count in top_files:
        abs_path = repo / rel_path
        if not abs_path.exists():
            # 尝试直接用相对路径的后半部分在 repo 下查找
            parts = rel_path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                candidate = repo / "/".join(parts[i:])
                if candidate.exists():
                    abs_path = candidate
                    break
            else:
                continue

        class_section = _analyze_java_file(abs_path, rel_path, hit_count)
        if class_section:
            sections.append(class_section)
            analyzed += 1

    if analyzed == 0:
        return ""

    sections += [
        "---",
        f"> 共分析 {analyzed} 个 Domain/App 层类文件。",
        "> Infrastructure Gateway 层已跳过（外部调用，行为由下游服务决定）。",
        "",
    ]
    return "\n".join(sections)


def _is_domain_layer(file_path: str) -> bool:
    """判断文件是否属于 Domain/App 层."""
    normalized = file_path.replace("\\", "/")
    for skip in _SKIP_LAYER_PATTERNS:
        if re.search(skip, normalized):
            return False
    return any(re.search(pattern, normalized) for pattern in _DOMAIN_LAYER_PATTERNS)


def _analyze_java_file(abs_path: Path, rel_path: str, hit_count: int) -> str:
    """分析单个 Java 文件，提取方法实现和调用链."""
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    class_name = _extract_class_name(content) or abs_path.stem
    methods = _extract_methods(content)

    if not methods:
        return ""

    # 优先选公共方法（entry points），再选私有方法（调用链）
    public_methods = [(n, b, s, e) for n, b, s, e in methods if not n.startswith("_")]
    private_methods = [(n, b, s, e) for n, b, s, e in methods if n.startswith("_")]
    selected = (public_methods + private_methods)[:_MAX_METHODS_PER_CLASS]

    lines: list[str] = [
        f"## `{class_name}` ({hit_count} SE 命中)",
        f"> 文件：`{rel_path}`",
        "",
    ]

    # 类级别调用关系总览
    call_map = _build_call_map(methods)
    if call_map:
        lines.append("### 方法调用关系")
        lines.append("```")
        for method, calls in list(call_map.items())[:8]:
            if calls:
                lines.append(f"{method}()")
                for callee in calls[:5]:
                    lines.append(f"  └─ {callee}()")
        lines.append("```")
        lines.append("")

    # 各方法实现（前 N 行）
    for method_name, body, start_line, _ in selected:
        truncated = body.splitlines()[:_MAX_METHOD_LINES]
        truncated_text = "\n".join(truncated)
        suffix = f"\n  ... (共 {len(body.splitlines())} 行)" if len(body.splitlines()) > _MAX_METHOD_LINES else ""

        # 提取该方法中的关键参数传递（含 filter/time/range 相关参数名）
        key_params = _extract_key_params(body)
        param_note = f"\n> ⚠️ 关键参数传递: {', '.join(key_params)}" if key_params else ""

        lines += [
            f"### `{method_name}()`  (L{start_line})",
            param_note,
            "```java",
            truncated_text + suffix,
            "```",
            "",
        ]

    return "\n".join(lines)


def _extract_class_name(content: str) -> str | None:
    """从 Java 文件内容中提取类名."""
    m = re.search(r"\bclass\s+(\w+)", content)
    return m.group(1) if m else None


def _extract_methods(content: str) -> list[tuple[str, str, int, int]]:
    """提取 Java 方法：返回 (方法名, 方法体, 起始行, 结束行) 列表."""
    lines = content.splitlines()
    results: list[tuple[str, str, int, int]] = []

    # 简单状态机：找方法声明，收集方法体
    method_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|static|final|synchronized)\s+)+"
        r"(?:\w[\w<>, \[\]]*\s+)"  # 返回类型
        r"(\w+)\s*\("  # 方法名
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        m = method_pattern.match(line)
        if m:
            method_name = m.group(1)
            # 跳过构造函数和 getter/setter（通常不含复杂逻辑）
            if method_name in ("get", "set", "is", "toString", "hashCode", "equals"):
                i += 1
                continue
            # 收集方法体（跟踪花括号）
            start_line = i + 1
            body_lines: list[str] = []
            depth = 0
            found_open = False
            j = i
            while j < len(lines) and j < i + 200:  # 最多向后 200 行
                cur = lines[j]
                body_lines.append(cur)
                depth += cur.count("{") - cur.count("}")
                if depth > 0:
                    found_open = True
                if found_open and depth <= 0:
                    results.append((method_name, "\n".join(body_lines), start_line, j + 1))
                    i = j
                    break
                j += 1
        i += 1

    return results


def _build_call_map(methods: list[tuple[str, str, int, int]]) -> dict[str, list[str]]:
    """构建方法间调用关系图."""
    method_names = {m[0] for m in methods}
    call_map: dict[str, list[str]] = {}

    for method_name, body, _, _ in methods:
        calls = []
        # 找 this.xxx() 或直接的 xxx() 调用
        for called in re.findall(r"\b(\w+)\s*\(", body):
            if called in method_names and called != method_name:
                calls.append(called)
        if calls:
            call_map[method_name] = list(dict.fromkeys(calls))  # 去重保序

    return call_map


def _extract_key_params(body: str) -> list[str]:
    """提取方法体中的关键参数传递（时间/过滤/范围相关）."""
    key_keywords = [
        "searchTime",
        "searchDate",
        "startTime",
        "endTime",
        "appointBeginTime",
        "appointEndTime",
        "prev2Start",
        "queryStartTime",
        "slot0",
        "slot1",
        "slot2",
        "slotAgg",
        "stNo",
        "null",
        "isEmpty",
        "isAllDay",
    ]
    found = []
    for kw in key_keywords:
        if kw in body:
            found.append(kw)
    return found[:6]  # 最多显示 6 个


def write_call_chain_analysis(
    output_dir: Path,
    project_id: str,
    repo_path: str,
    phase_id: str,
    mapping: list[dict[str, Any]],
) -> Path | None:
    """生成并写入 _code_call_chain.md，返回文件路径."""
    from qualix.constants import PHASE_DIR_MAP

    analysis = generate_call_chain_analysis(mapping, repo_path)
    if not analysis:
        return None

    dir_suffix = PHASE_DIR_MAP.get(phase_id, f"phase{phase_id}")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    path = int_dir / "_code_call_chain.md"
    path.write_text(analysis, encoding="utf-8")
    log.info("Code call chain analysis written: %s", path)
    return path
