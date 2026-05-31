"""Tree-sitter based code-intelligence provider.

The provider is deliberately optional. Missing parser packages make a language
unavailable instead of blocking the rest of the Qualix workflow.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from qualix.code_intelligence.base import CodeDiagnostic, CodeIntelligenceProvider, CodeSymbol, Location, SymbolKind
from qualix.log import get_logger

log = get_logger(__name__)


_LANGUAGE_ALIASES = {
    "java": "java",
    "typescript": "typescript",
    "ts": "typescript",
    "tsx": "typescript",
    "go": "go",
    "golang": "go",
    "python": "python",
    "py": "python",
}

_SUFFIX_LANGUAGES = {
    ".java": "java",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".py": "python",
}

_GRAMMARS = {
    "java": ("tree_sitter_java", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "go": ("tree_sitter_go", "language"),
    "python": ("tree_sitter_python", "language"),
}


class TreeSitterCodeIntelligenceProvider(CodeIntelligenceProvider):
    """File-local symbol and parse-diagnostic provider backed by Tree-sitter."""

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}
        self._unavailable: set[str] = set()

    @property
    def provider_id(self) -> str:
        return "tree-sitter"

    def is_available(self, language_id: str) -> bool:
        language = _normalize_language(language_id)
        return bool(language and self._parser_for(language))

    def symbols_for_file(self, file_path: Path, language_id: str | None = None) -> list[CodeSymbol]:
        language = self._resolve_language(file_path, language_id)
        if not language:
            return []
        root, source = self._parse(file_path, language)
        if root is None:
            return []
        if language == "java":
            return _extract_java_symbols(root, source, file_path)
        if language == "typescript":
            return _extract_typescript_symbols(root, source, file_path)
        if language == "go":
            return _extract_go_symbols(root, source, file_path)
        if language == "python":
            return _extract_python_symbols(root, source, file_path)
        return []

    def diagnostics_for_file(self, file_path: Path, language_id: str | None = None) -> list[CodeDiagnostic]:
        language = self._resolve_language(file_path, language_id)
        if not language:
            return []
        root, _source = self._parse(file_path, language)
        if root is None or not getattr(root, "has_error", False):
            return []

        diagnostics = [
            CodeDiagnostic(
                message=f"Parse error in {language} source",
                location=_location(node, file_path),
                severity="error",
                code="TREE_SITTER_PARSE_ERROR",
                source=self.provider_id,
            )
            for node in _iter_parse_error_nodes(root)
        ]
        if diagnostics:
            return diagnostics

        return [
            CodeDiagnostic(
                message=f"Parse error in {language} source",
                location=_location(root, file_path),
                severity="error",
                code="TREE_SITTER_PARSE_ERROR",
                source=self.provider_id,
            )
        ]

    def _resolve_language(self, file_path: Path, language_id: str | None) -> str | None:
        language = _normalize_language(language_id) if language_id else _SUFFIX_LANGUAGES.get(file_path.suffix)
        if not language or not self._parser_for(language):
            return None
        return language

    def _parse(self, file_path: Path, language_id: str) -> tuple[Any | None, bytes]:
        parser = self._parser_for(language_id)
        if not parser:
            return None, b""
        source = file_path.read_bytes()
        tree = parser.parse(source)
        return tree.root_node, source

    def _parser_for(self, language_id: str) -> Any | None:
        language = _normalize_language(language_id)
        if not language or language in self._unavailable:
            return None
        if language in self._parsers:
            return self._parsers[language]

        grammar = _GRAMMARS.get(language)
        if not grammar:
            self._unavailable.add(language)
            return None

        module_name, function_name = grammar
        try:
            from tree_sitter import Language, Parser

            grammar_module = import_module(module_name)
            grammar_capsule = getattr(grammar_module, function_name)()
            tree_sitter_language = Language(grammar_capsule)
            parser = _build_parser(Parser, tree_sitter_language)
        except Exception as exc:  # optional integration: keep the main workflow alive
            self._unavailable.add(language)
            log.debug("Tree-sitter parser unavailable for %s: %s", language, exc)
            return None

        self._parsers[language] = parser
        return parser


def _build_parser(parser_cls: Any, language: Any) -> Any:
    try:
        return parser_cls(language)
    except TypeError:
        parser = parser_cls()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        else:
            parser.language = language
        return parser


def _normalize_language(language_id: str | None) -> str | None:
    if not language_id:
        return None
    return _LANGUAGE_ALIASES.get(language_id.lower())


def _extract_java_symbols(root: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for node in _walk(root):
        if node.type == "class_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "java", SymbolKind.CLASS))
            continue
        if node.type == "interface_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "java", SymbolKind.INTERFACE))
            continue
        if node.type == "method_declaration":
            symbols.append(
                _symbol_from_node(
                    node,
                    source,
                    file_path,
                    "java",
                    SymbolKind.METHOD,
                    container=_nearest_named_container(node, source),
                )
            )
            continue
        if node.type == "field_declaration":
            for declarator in _direct_children(node, "variable_declarator"):
                symbols.append(
                    _symbol_from_node(
                        declarator,
                        source,
                        file_path,
                        "java",
                        SymbolKind.FIELD,
                        container=_nearest_named_container(node, source),
                    )
                )
    return [symbol for symbol in symbols if symbol.name]


def _extract_typescript_symbols(root: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for node in _walk(root):
        if node.type == "class_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "typescript", SymbolKind.CLASS))
            continue
        if node.type == "interface_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "typescript", SymbolKind.INTERFACE))
            continue
        if node.type == "function_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "typescript", SymbolKind.FUNCTION))
            continue
        if node.type == "method_definition":
            symbols.append(
                _symbol_from_node(
                    node,
                    source,
                    file_path,
                    "typescript",
                    SymbolKind.METHOD,
                    container=_nearest_named_container(node, source),
                )
            )
            continue
        if node.type == "lexical_declaration":
            symbols.extend(_extract_typescript_lexical_symbols(node, source, file_path))
    return [symbol for symbol in symbols if symbol.name]


def _extract_typescript_lexical_symbols(node: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for declarator in _direct_children(node, "variable_declarator"):
        value = declarator.child_by_field_name("value")
        kind = SymbolKind.FUNCTION if value and value.type in ("arrow_function", "function_expression") else SymbolKind.VARIABLE
        symbols.append(_symbol_from_node(declarator, source, file_path, "typescript", kind))
    return symbols


def _extract_go_symbols(root: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for node in _walk(root):
        if node.type == "function_declaration":
            symbols.append(_symbol_from_node(node, source, file_path, "go", SymbolKind.FUNCTION))
            continue
        if node.type == "method_declaration":
            symbols.append(
                _symbol_from_node(
                    node,
                    source,
                    file_path,
                    "go",
                    SymbolKind.METHOD,
                    container=_go_receiver_container(node, source),
                )
            )
            continue
        if node.type == "type_declaration":
            symbols.extend(_extract_go_type_symbols(node, source, file_path))
    return [symbol for symbol in symbols if symbol.name]


def _extract_go_type_symbols(node: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for spec in _direct_children(node, "type_spec"):
        type_node = spec.child_by_field_name("type")
        kind = SymbolKind.STRUCT
        if type_node and type_node.type == "interface_type":
            kind = SymbolKind.INTERFACE
        symbols.append(_symbol_from_node(spec, source, file_path, "go", kind))
    return symbols


def _extract_python_symbols(root: Any, source: bytes, file_path: Path) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for node in root.children:
        if node.type == "class_definition":
            symbols.append(_symbol_from_node(node, source, file_path, "python", SymbolKind.CLASS))
            class_name = _node_name(node, source)
            body = _first_child(node, "block")
            if body:
                for child in body.children:
                    if child.type == "function_definition":
                        symbols.append(
                            _symbol_from_node(
                                child,
                                source,
                                file_path,
                                "python",
                                SymbolKind.METHOD,
                                container=class_name,
                            )
                        )
            continue
        if node.type == "function_definition":
            symbols.append(_symbol_from_node(node, source, file_path, "python", SymbolKind.FUNCTION))
    return [symbol for symbol in symbols if symbol.name]


def _symbol_from_node(
    node: Any,
    source: bytes,
    file_path: Path,
    language: str,
    kind: SymbolKind,
    container: str = "",
) -> CodeSymbol:
    return CodeSymbol(
        name=_node_name(node, source),
        kind=kind,
        location=_location(node, file_path),
        language=language,
        container=container,
        signature=_signature(node, source),
        metadata={"provider": "tree-sitter"},
    )


def _node_name(node: Any, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _text(name_node, source)
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "field_identifier", "property_identifier"):
            return _text(child, source)
    return ""


def _nearest_named_container(node: Any, source: bytes) -> str:
    parent = getattr(node, "parent", None)
    while parent:
        if parent.type in ("class_declaration", "interface_declaration"):
            return _node_name(parent, source)
        parent = getattr(parent, "parent", None)
    return ""


def _go_receiver_container(node: Any, source: bytes) -> str:
    receiver = node.child_by_field_name("receiver") or _first_child(node, "parameter_list")
    if not receiver:
        return ""
    names = [_text(child, source).lstrip("*") for child in _walk(receiver) if child.type == "type_identifier"]
    return names[-1] if names else ""


def _location(node: Any, file_path: Path) -> Location:
    return Location(
        file_path=str(file_path),
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        column_start=node.start_point[1],
        column_end=node.end_point[1],
    )


def _signature(node: Any, source: bytes) -> str:
    text = _text(node, source).strip()
    first_line = text.splitlines()[0].strip() if text else ""
    if len(first_line) > 160:
        return f"{first_line[:157]}..."
    return first_line


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _direct_children(node: Any, node_type: str) -> list[Any]:
    return [child for child in node.children if child.type == node_type]


def _first_child(node: Any, node_type: str) -> Any | None:
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _walk(node: Any):
    yield node
    for child in node.children:
        yield from _walk(child)


def _iter_parse_error_nodes(root: Any):
    for node in _walk(root):
        if node.type == "ERROR" or getattr(node, "is_missing", False):
            yield node
