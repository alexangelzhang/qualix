"""Shared contracts for optional code-intelligence providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SymbolKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    FIELD = "field"
    VARIABLE = "variable"


@dataclass(frozen=True)
class Location:
    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: SymbolKind
    location: Location
    language: str
    container: str = ""
    signature: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodeDiagnostic:
    message: str
    location: Location
    severity: str = "warning"
    code: str = ""
    source: str = ""


class CodeIntelligenceProvider(ABC):
    """Optional source-code intelligence abstraction.

    This is intentionally smaller than LSP. It gives Qualix a common surface for
    symbols, diagnostics, and future definition/reference lookups without making
    any language server a hard dependency.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider id, e.g. tree-sitter."""

    @abstractmethod
    def is_available(self, language_id: str) -> bool:
        """Whether this provider can serve a language in the current environment."""

    @abstractmethod
    def symbols_for_file(self, file_path: Path, language_id: str | None = None) -> list[CodeSymbol]:
        """Return top-level symbols for one file."""

    def diagnostics_for_file(self, file_path: Path, language_id: str | None = None) -> list[CodeDiagnostic]:
        """Return parse diagnostics if supported. Default: no diagnostics."""
        return []

    def definitions(self, file_path: Path, symbol_name: str, language_id: str | None = None) -> list[Location]:
        """Return known definition locations. Tree-sitter implementation is file-local."""
        return [symbol.location for symbol in self.symbols_for_file(file_path, language_id) if symbol.name == symbol_name]

    def references(self, file_path: Path, symbol_name: str, language_id: str | None = None) -> list[Location]:
        """Return known references. Default providers may leave this empty."""
        return []

