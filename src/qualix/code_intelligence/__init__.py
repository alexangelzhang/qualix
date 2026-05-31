"""Code intelligence providers for optional source-code enrichment."""

from qualix.code_intelligence.base import (
    CodeDiagnostic,
    CodeIntelligenceProvider,
    CodeSymbol,
    Location,
    SymbolKind,
)
from qualix.code_intelligence.registry import CodeIntelligenceRegistry, get_code_intelligence_registry
from qualix.code_intelligence.tree_sitter_provider import TreeSitterCodeIntelligenceProvider

__all__ = [
    "CodeDiagnostic",
    "CodeIntelligenceProvider",
    "CodeIntelligenceRegistry",
    "CodeSymbol",
    "Location",
    "SymbolKind",
    "TreeSitterCodeIntelligenceProvider",
    "get_code_intelligence_registry",
]

