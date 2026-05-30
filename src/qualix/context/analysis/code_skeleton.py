"""TREEFRAG 代码骨架压缩：AST 层级裁剪 + Oracle 标注按需展开.

基于 tree-sitter Java AST，提取类签名 + 方法签名 + 字段声明 + 注解，
省略方法体。Oracle（SE→Code 映射）标记的相关方法展开完整实现。

典型压缩比 10:1 ~ 18:1（论文 2601.19929 报告 239k → 11k）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


@dataclass
class SkeletonMethod:
    """方法骨架."""

    name: str
    signature: str  # 完整签名行（含注解、修饰符、返回类型、参数）
    body: str  # 完整方法体（含大括号）
    line_start: int  # 1-based
    line_end: int  # 1-based
    is_expanded: bool = False  # Oracle 标记展开


@dataclass
class SkeletonClass:
    """类骨架."""

    name: str
    signature: str  # class/interface 声明行
    package: str = ""
    imports: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    methods: list[SkeletonMethod] = field(default_factory=list)
    inner_classes: list[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


@dataclass
class SkeletonResult:
    """骨架提取结果."""

    skeleton_text: str
    full_text: str
    classes: list[SkeletonClass] = field(default_factory=list)
    total_lines: int = 0
    skeleton_lines: int = 0
    expanded_methods: list[str] = field(default_factory=list)
    compression_ratio: float = 0.0


# ---------------------------------------------------------------------------
# tree-sitter 骨架提取
# ---------------------------------------------------------------------------


def extract_skeleton_ts(
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult | None:
    """用 tree-sitter 提取 Java 代码骨架.

    Args:
        source: Java 源码文本
        expand_methods: Oracle 标记需要展开的方法名集合

    Returns:
        SkeletonResult 或 None（tree-sitter 不可用时）
    """
    from .java_ast_analyzer import _ensure_parser, _parser

    if not _ensure_parser() or _parser is None:
        return None

    expand = expand_methods or set()
    source_bytes = source.encode("utf-8")
    tree = _parser.parse(source_bytes)
    root = tree.root_node

    classes: list[SkeletonClass] = []
    skeleton_parts: list[str] = []
    expanded: list[str] = []

    # 提取 package
    package = ""
    for node in root.children:
        if node.type == "package_declaration":
            package = _node_text(node, source_bytes)
            skeleton_parts.append(package)
            break

    # 提取 imports
    imports: list[str] = []
    for node in root.children:
        if node.type == "import_declaration":
            imp = _node_text(node, source_bytes)
            imports.append(imp)
    if imports:
        skeleton_parts.append("\n".join(imports))

    # 提取类/接口
    for node in root.children:
        if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            cls = _extract_class_skeleton(node, source_bytes, expand)
            classes.append(cls)
            cls_text, cls_expanded = _render_class_skeleton(cls)
            skeleton_parts.append(cls_text)
            expanded.extend(cls_expanded)

    skeleton_text = "\n\n".join(skeleton_parts)
    total_lines = len(source.splitlines())
    skeleton_lines = len(skeleton_text.splitlines())

    return SkeletonResult(
        skeleton_text=skeleton_text,
        full_text=source,
        classes=classes,
        total_lines=total_lines,
        skeleton_lines=skeleton_lines,
        expanded_methods=expanded,
        compression_ratio=round(total_lines / max(skeleton_lines, 1), 1),
    )


def _extract_class_skeleton(
    node: Any,
    source: bytes,
    expand: set[str],
) -> SkeletonClass:
    """从 class_declaration 节点提取骨架."""
    # 类签名：从节点开始到 { 之前
    body_node = None
    for child in node.children:
        if child.type in ("class_body", "interface_body", "enum_body"):
            body_node = child
            break

    sig_end = body_node.start_byte if body_node else node.end_byte
    signature = source[node.start_byte : sig_end].decode("utf-8", errors="replace").strip()

    # 类名
    name = ""
    for child in node.children:
        if child.type == "identifier":
            name = _node_text(child, source)
            break

    cls = SkeletonClass(
        name=name,
        signature=signature,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
    )

    if not body_node:
        return cls

    for child in body_node.children:
        if child.type == "field_declaration":
            cls.fields.append(_node_text(child, source))
        elif child.type == "method_declaration" or child.type == "constructor_declaration":
            method = _extract_method_skeleton(child, source, expand)
            cls.methods.append(method)
        elif child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            # 内部类只保留签名
            inner_sig = _extract_inner_class_signature(child, source)
            cls.inner_classes.append(inner_sig)

    return cls


def _extract_method_skeleton(
    node: Any,
    source: bytes,
    expand: set[str],
) -> SkeletonMethod:
    """从 method_declaration 节点提取方法骨架."""
    name = ""
    for child in node.children:
        if child.type == "identifier":
            name = _node_text(child, source)
            break

    # 签名：从方法开始到方法体 { 之前
    body_node = None
    for child in node.children:
        if child.type == "block" or child.type == "constructor_body":
            body_node = child
            break

    sig_end = body_node.start_byte if body_node else node.end_byte
    signature = source[node.start_byte : sig_end].decode("utf-8", errors="replace").strip()

    body = ""
    if body_node:
        body = source[body_node.start_byte : body_node.end_byte].decode("utf-8", errors="replace")

    should_expand = name in expand or any(name.lower() == e.lower() for e in expand)

    return SkeletonMethod(
        name=name,
        signature=signature,
        body=body,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        is_expanded=should_expand,
    )


def _extract_inner_class_signature(node: Any, source: bytes) -> str:
    """提取内部类的签名（不含 body）."""
    for child in node.children:
        if child.type in ("class_body", "interface_body", "enum_body"):
            return source[node.start_byte : child.start_byte].decode("utf-8", errors="replace").strip() + " { ... }"
    return _node_text(node, source)


def _render_class_skeleton(cls: SkeletonClass) -> tuple[str, list[str]]:
    """渲染类骨架为文本.

    Returns:
        (skeleton_text, expanded_method_names)
    """
    lines: list[str] = [cls.signature + " {"]
    expanded: list[str] = []

    # 字段
    for f in cls.fields:
        lines.append(f"    {f}")
    if cls.fields:
        lines.append("")

    # 方法
    for m in cls.methods:
        if m.is_expanded:
            lines.append(f"    {m.signature} {m.body}")
            expanded.append(m.name)
        else:
            lines.append(f"    {m.signature} {{ ... }}")
    if cls.methods:
        lines.append("")

    # 内部类
    for ic in cls.inner_classes:
        lines.append(f"    {ic}")

    lines.append("}")
    return "\n".join(lines), expanded


def _node_text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Regex fallback（tree-sitter 不可用时）
# ---------------------------------------------------------------------------

# 方法签名正则
_METHOD_RE = re.compile(
    r"^(\s*)"  # 缩进
    r"((?:@\w+(?:\([^)]*\))?\s+)*)"  # 注解
    r"((?:public|private|protected|static|final|abstract|synchronized|native|default)\s+)*"
    r"([\w<>\[\],\s?]+?)\s+"  # 返回类型
    r"(\w+)\s*\([^)]*\)\s*"  # 方法名+参数
    r"(?:throws\s+[\w,\s]+)?\s*\{",  # throws
    re.MULTILINE,
)


def extract_skeleton_regex(
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult:
    """正则 fallback：提取方法签名，省略方法体.

    不如 tree-sitter 精确，但零依赖。
    """
    expand = expand_methods or set()
    lines = source.splitlines()
    result_lines: list[str] = []
    expanded: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _METHOD_RE.match(line)
        if m:
            method_name = m.group(5)
            should_expand = method_name in expand or any(method_name.lower() == e.lower() for e in expand)

            if should_expand:
                # 展开：保留完整方法体
                result_lines.append(line)
                expanded.append(method_name)
                brace_depth = line.count("{") - line.count("}")
                i += 1
                while i < len(lines) and brace_depth > 0:
                    result_lines.append(lines[i])
                    brace_depth += lines[i].count("{") - lines[i].count("}")
                    i += 1
                continue
            else:
                # 骨架：签名 + { ... }
                sig = line.rstrip().rstrip("{").rstrip()
                result_lines.append(f"{sig} {{ ... }}")
                # 跳过方法体
                brace_depth = line.count("{") - line.count("}")
                i += 1
                while i < len(lines) and brace_depth > 0:
                    brace_depth += lines[i].count("{") - lines[i].count("}")
                    i += 1
                continue
        else:
            result_lines.append(line)
        i += 1

    skeleton_text = "\n".join(result_lines)
    total = len(lines)
    skel = len(result_lines)

    return SkeletonResult(
        skeleton_text=skeleton_text,
        full_text=source,
        total_lines=total,
        skeleton_lines=skel,
        expanded_methods=expanded,
        compression_ratio=round(total / max(skel, 1), 1),
    )


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def extract_skeleton(
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult:
    """提取 Java 代码骨架（tree-sitter 优先，regex fallback）.

    Args:
        source: Java 源码文本
        expand_methods: Oracle 标记需要展开完整实现的方法名集合
    """
    result = extract_skeleton_ts(source, expand_methods)
    if result is not None:
        return result
    return extract_skeleton_regex(source, expand_methods)


def extract_skeleton_for_files(
    file_paths: list[Path],
    se_code_mapping: dict[str, list[str]] | None = None,
) -> dict[str, SkeletonResult]:
    """批量提取多个文件的骨架.

    Args:
        file_paths: Java 文件路径列表
        se_code_mapping: {file_path_str: [method_name, ...]} Oracle 映射

    Returns:
        {file_path_str: SkeletonResult}
    """
    mapping = se_code_mapping or {}
    results: dict[str, SkeletonResult] = {}

    for fp in file_paths:
        try:
            source = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        expand = set(mapping.get(str(fp), []))
        results[str(fp)] = extract_skeleton(source, expand)

    if results:
        total_orig = sum(r.total_lines for r in results.values())
        total_skel = sum(r.skeleton_lines for r in results.values())
        total_expanded = sum(len(r.expanded_methods) for r in results.values())
        log.info(
            "TREEFRAG: %d files, %d→%d lines (%.1fx), %d methods expanded",
            len(results),
            total_orig,
            total_skel,
            total_orig / max(total_skel, 1),
            total_expanded,
        )

    return results
