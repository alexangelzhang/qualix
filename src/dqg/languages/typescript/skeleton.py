"""TypeScript TREEFRAG skeleton extraction using tree-sitter.

Extracts class/interface/function signatures, omits method bodies.
Oracle-marked methods are fully expanded.
"""

from __future__ import annotations

from typing import Any

from dqg.context.code_skeleton import SkeletonClass, SkeletonMethod, SkeletonResult
from dqg.log import get_logger

log = get_logger(__name__)


def extract_skeleton_ts(
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult | None:
    """Extract TypeScript code skeleton using tree-sitter.

    Returns None if tree-sitter-typescript is not available.
    """
    from dqg.languages.typescript.ast_analyzer import _ensure_parser, _parser

    if not _ensure_parser() or _parser is None:
        return None

    if not source.strip():
        return SkeletonResult(
            skeleton_text="",
            full_text=source,
            total_lines=0,
            skeleton_lines=0,
            compression_ratio=0.0,
        )

    expand = expand_methods or set()
    source_bytes = source.encode("utf-8")
    tree = _parser.parse(source_bytes)
    root = tree.root_node

    skeleton_parts: list[str] = []
    classes: list[SkeletonClass] = []
    expanded: list[str] = []

    # Collect imports
    imports: list[str] = []
    for node in root.children:
        if node.type == "import_statement":
            imports.append(_node_text(node, source_bytes))
    if imports:
        skeleton_parts.append("\n".join(imports))

    # Process top-level declarations
    for node in root.children:
        if node.type == "import_statement":
            continue
        elif node.type == "interface_declaration":
            skeleton_parts.append(_node_text(node, source_bytes))
        elif node.type in ("class_declaration", "abstract_class_declaration"):
            cls, cls_text, cls_expanded = _extract_class(node, source_bytes, expand)
            classes.append(cls)
            skeleton_parts.append(cls_text)
            expanded.extend(cls_expanded)
        elif node.type == "export_statement":
            _handle_export(node, source_bytes, expand, skeleton_parts, classes, expanded)
        elif node.type in ("function_declaration", "lexical_declaration"):
            text, fn_expanded = _extract_top_level_function(node, source_bytes, expand)
            skeleton_parts.append(text)
            expanded.extend(fn_expanded)

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


def _handle_export(
    node: Any,
    source_bytes: bytes,
    expand: set[str],
    skeleton_parts: list[str],
    classes: list[SkeletonClass],
    expanded: list[str],
) -> None:
    """Process export statement children."""
    for child in node.children:
        if child.type in ("class_declaration", "abstract_class_declaration"):
            decorators = _collect_decorators(node, source_bytes)
            cls, cls_text, cls_expanded = _extract_class(child, source_bytes, expand)
            classes.append(cls)
            prefix = "\n".join(decorators) + "\n" if decorators else ""
            skeleton_parts.append(prefix + "export " + cls_text)
            expanded.extend(cls_expanded)
        elif child.type == "interface_declaration":
            skeleton_parts.append("export " + _node_text(child, source_bytes))
        elif child.type in ("function_declaration", "lexical_declaration"):
            text, fn_expanded = _extract_top_level_function(child, source_bytes, expand)
            skeleton_parts.append("export " + text)
            expanded.extend(fn_expanded)


def _node_text(node: Any, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _collect_decorators(node: Any, source_bytes: bytes) -> list[str]:
    """Collect decorator nodes preceding a declaration."""
    return [_node_text(child, source_bytes) for child in node.children if child.type == "decorator"]


def _find_body(node: Any) -> Any | None:
    """Find the statement_block (body) child of a node."""
    for child in node.children:
        if child.type == "statement_block":
            return child
    return None


def _find_name(node: Any, source_bytes: bytes) -> str:
    """Extract identifier name from a declaration node."""
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier"):
            return _node_text(child, source_bytes)
    return ""


def _find_class_body(node: Any) -> Any | None:
    """Find the class_body child of a class declaration."""
    for child in node.children:
        if child.type == "class_body":
            return child
    return None


def _extract_class(
    node: Any,
    source_bytes: bytes,
    expand: set[str],
) -> tuple[SkeletonClass, str, list[str]]:
    """Extract class skeleton: signature + fields + method signatures."""
    name = _find_name(node, source_bytes)
    body = _find_class_body(node)

    if body:
        sig = source_bytes[node.start_byte : body.start_byte].decode("utf-8", errors="replace").strip()
    else:
        sig = _node_text(node, source_bytes)

    cls = SkeletonClass(
        name=name,
        signature=sig,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
    )

    lines: list[str] = [sig + " {"]
    expanded_names: list[str] = []

    if body:
        for child in body.children:
            if child.type == "method_definition":
                method = _extract_method(child, source_bytes, expand)
                cls.methods.append(method)
                if method.is_expanded:
                    lines.append(f"    {method.signature} {method.body}")
                    expanded_names.append(method.name)
                else:
                    lines.append(f"    {method.signature} {{ ... }}")
            elif child.type in ("public_field_definition", "property_definition"):
                field_text = _node_text(child, source_bytes)
                cls.fields.append(field_text)
                lines.append(f"    {field_text}")

    lines.append("}")
    return cls, "\n".join(lines), expanded_names


def _extract_method(node: Any, source_bytes: bytes, expand: set[str]) -> SkeletonMethod:
    """Extract method skeleton from a method_definition node."""
    name = _find_name(node, source_bytes)
    body = _find_body(node)

    if body:
        sig = source_bytes[node.start_byte : body.start_byte].decode("utf-8", errors="replace").strip()
        body_text = _node_text(body, source_bytes)
    else:
        sig = _node_text(node, source_bytes)
        body_text = ""

    should_expand = name in expand or any(name.lower() == e.lower() for e in expand)

    return SkeletonMethod(
        name=name,
        signature=sig,
        body=body_text,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        is_expanded=should_expand,
    )


def _extract_top_level_function(
    node: Any,
    source_bytes: bytes,
    expand: set[str],
) -> tuple[str, list[str]]:
    """Extract top-level function/const arrow function skeleton."""
    name = _find_name(node, source_bytes)
    body = _find_body(node)

    if not body:
        return _node_text(node, source_bytes), []

    sig = source_bytes[node.start_byte : body.start_byte].decode("utf-8", errors="replace").strip()
    should_expand = name in expand or any(name.lower() == e.lower() for e in expand)

    if should_expand:
        return f"{sig} {_node_text(body, source_bytes)}", [name]
    return f"{sig} {{ ... }}", []
