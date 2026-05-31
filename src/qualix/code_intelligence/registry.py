"""Registry for optional code-intelligence providers."""

from __future__ import annotations

from qualix.code_intelligence.base import CodeIntelligenceProvider


class CodeIntelligenceRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, CodeIntelligenceProvider] = {}

    def register(self, provider: CodeIntelligenceProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> CodeIntelligenceProvider | None:
        return self._providers.get(provider_id)

    def best_for_language(self, language_id: str) -> CodeIntelligenceProvider | None:
        for provider in self._providers.values():
            if provider.is_available(language_id):
                return provider
        return None

    @property
    def registered_providers(self) -> list[str]:
        return list(self._providers.keys())


_global_registry: CodeIntelligenceRegistry | None = None


def get_code_intelligence_registry() -> CodeIntelligenceRegistry:
    global _global_registry
    if _global_registry is None:
        from qualix.code_intelligence.tree_sitter_provider import TreeSitterCodeIntelligenceProvider

        _global_registry = CodeIntelligenceRegistry()
        _global_registry.register(TreeSitterCodeIntelligenceProvider())
    return _global_registry

