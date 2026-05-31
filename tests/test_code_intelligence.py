from __future__ import annotations

from pathlib import Path

import pytest

from qualix.code_intelligence import SymbolKind, TreeSitterCodeIntelligenceProvider, get_code_intelligence_registry


def _require_language(provider: TreeSitterCodeIntelligenceProvider, language_id: str) -> None:
    if not provider.is_available(language_id):
        pytest.skip(f"tree-sitter grammar for {language_id} is not installed")


def test_code_intelligence_registry_registers_tree_sitter() -> None:
    registry = get_code_intelligence_registry()
    assert "tree-sitter" in registry.registered_providers
    provider = registry.best_for_language("python")
    assert provider is None or provider.provider_id == "tree-sitter"


def test_tree_sitter_extracts_python_symbols(tmp_path: Path) -> None:
    provider = TreeSitterCodeIntelligenceProvider()
    _require_language(provider, "python")

    source = tmp_path / "expense_policy.py"
    source.write_text(
        """
class ApprovalService:
    def approve(self, request):
        return True

def parse_total(value):
    return int(value)
""".strip(),
        encoding="utf-8",
    )

    symbols = provider.symbols_for_file(source)
    by_name = {symbol.name: symbol for symbol in symbols}

    assert by_name["ApprovalService"].kind == SymbolKind.CLASS
    assert by_name["approve"].kind == SymbolKind.METHOD
    assert by_name["approve"].container == "ApprovalService"
    assert by_name["parse_total"].kind == SymbolKind.FUNCTION
    assert provider.definitions(source, "parse_total")[0].line_start == 5


def test_tree_sitter_extracts_go_symbols(tmp_path: Path) -> None:
    provider = TreeSitterCodeIntelligenceProvider()
    _require_language(provider, "go")

    source = tmp_path / "expense_policy.go"
    source.write_text(
        """
package policy

type Request struct { Amount int }
type Rule interface { Matches(Request) bool }

func Approve(r Request) bool { return true }
func (s Service) Decide() bool { return true }
""".strip(),
        encoding="utf-8",
    )

    symbols = provider.symbols_for_file(source)
    by_name = {symbol.name: symbol for symbol in symbols}

    assert by_name["Request"].kind == SymbolKind.STRUCT
    assert by_name["Rule"].kind == SymbolKind.INTERFACE
    assert by_name["Approve"].kind == SymbolKind.FUNCTION
    assert by_name["Decide"].kind == SymbolKind.METHOD
    assert by_name["Decide"].container == "Service"


def test_tree_sitter_extracts_typescript_symbols(tmp_path: Path) -> None:
    provider = TreeSitterCodeIntelligenceProvider()
    _require_language(provider, "typescript")

    source = tmp_path / "expensePolicy.ts"
    source.write_text(
        """
export interface Request { amount: number }
export class ApprovalService {
  approve(request: Request): boolean { return true }
}
export function parseTotal(value: string): number { return Number(value) }
const helper = () => true
""".strip(),
        encoding="utf-8",
    )

    symbols = provider.symbols_for_file(source)
    by_name = {symbol.name: symbol for symbol in symbols}

    assert by_name["Request"].kind == SymbolKind.INTERFACE
    assert by_name["ApprovalService"].kind == SymbolKind.CLASS
    assert by_name["approve"].kind == SymbolKind.METHOD
    assert by_name["approve"].container == "ApprovalService"
    assert by_name["parseTotal"].kind == SymbolKind.FUNCTION
    assert by_name["helper"].kind == SymbolKind.FUNCTION


def test_tree_sitter_extracts_java_symbols(tmp_path: Path) -> None:
    provider = TreeSitterCodeIntelligenceProvider()
    _require_language(provider, "java")

    source = tmp_path / "ApprovalService.java"
    source.write_text(
        """
package demo;

public class ApprovalService {
  private int count;
  public boolean approve(Request request) { return true; }
}

interface Rule {
  boolean matches(Request request);
}
""".strip(),
        encoding="utf-8",
    )

    symbols = provider.symbols_for_file(source)
    by_name = {symbol.name: symbol for symbol in symbols}

    assert by_name["ApprovalService"].kind == SymbolKind.CLASS
    assert by_name["count"].kind == SymbolKind.FIELD
    assert by_name["count"].container == "ApprovalService"
    assert by_name["approve"].kind == SymbolKind.METHOD
    assert by_name["Rule"].kind == SymbolKind.INTERFACE
    assert by_name["matches"].container == "Rule"


def test_tree_sitter_reports_parse_diagnostics(tmp_path: Path) -> None:
    provider = TreeSitterCodeIntelligenceProvider()
    _require_language(provider, "python")

    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n    return True\n", encoding="utf-8")

    diagnostics = provider.diagnostics_for_file(source)

    assert diagnostics
    assert diagnostics[0].code == "TREE_SITTER_PARSE_ERROR"
    assert diagnostics[0].severity == "error"

