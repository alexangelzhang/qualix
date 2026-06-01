"""Q05a CodeIntelligence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qualix.code_intelligence import get_code_intelligence_registry
from qualix.schemas.q05_target_modules import CodeSymbolTarget


def collect_symbols_for_diff_files(target_modules_data: dict[str, Any], code_repos: list[str]) -> list[CodeSymbolTarget]:
    """Collect Tree-sitter symbols for files listed in _q05_target_modules.json."""
    if not target_modules_data or target_modules_data.get("code_symbols"):
        return []
    diff_files = target_modules_data.get("git_diff_files", []) or []
    if not diff_files or not code_repos:
        return []

    registry = get_code_intelligence_registry()
    language_id = str(target_modules_data.get("language_id", "") or "") or None
    symbols: list[CodeSymbolTarget] = []
    for rel_file in diff_files:
        file_path = _resolve_diff_file(str(rel_file), code_repos)
        if not file_path or not file_path.is_file():
            continue
        provider = registry.best_for_language(language_id) if language_id else registry.best_for_language(_language_hint(file_path))
        if not provider:
            continue
        for symbol in provider.symbols_for_file(file_path, language_id=language_id):
            symbols.append(
                CodeSymbolTarget(
                    name=symbol.name,
                    kind=str(symbol.kind.value if hasattr(symbol.kind, "value") else symbol.kind),
                    file=str(file_path),
                    language=symbol.language,
                    container=symbol.container,
                )
            )
    return symbols


def _resolve_diff_file(path: str, code_repos: list[str]) -> Path | None:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    for repo in code_repos:
        resolved = Path(repo).expanduser().resolve() / path
        if resolved.exists():
            return resolved
    return None


def _language_hint(path: Path) -> str:
    return {
        ".java": "java",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".py": "python",
    }.get(path.suffix, "")

