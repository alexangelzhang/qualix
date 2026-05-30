"""LanguageRegistry — Provider 注册、语言检测、按 ID 获取."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from qualix.languages.base import LanguageProvider

log = get_logger(__name__)


class LanguageRegistry:
    """语言 Provider 注册表.

    用法::

        registry = LanguageRegistry()
        registry.register(JavaProvider())
        registry.register(TypeScriptProvider())

        # 自动检测
        provider = registry.detect(repo_root)

        # 按 ID 获取
        provider = registry.get("typescript")
    """

    def __init__(self) -> None:
        self._providers: dict[str, LanguageProvider] = {}

    def register(self, provider: LanguageProvider) -> None:
        """注册一个 Provider."""
        lang_id = provider.language_id
        if lang_id in self._providers:
            log.warning("覆盖已注册的 Provider: %s", lang_id)
        self._providers[lang_id] = provider
        log.debug("注册 LanguageProvider: %s", lang_id)

    def get(self, language_id: str) -> LanguageProvider | None:
        """按 language_id 获取 Provider."""
        return self._providers.get(language_id)

    def detect(self, repo_root: Path) -> LanguageProvider | None:
        """自动检测仓库主语言，返回置信度最高的 Provider.

        Returns:
            置信度最高的 Provider，全部为 0 则返回 None。
        """
        best: LanguageProvider | None = None
        best_score = 0.0

        for provider in self._providers.values():
            try:
                score = provider.detect(repo_root)
            except Exception:
                log.warning("Provider %s detect 异常", provider.language_id, exc_info=True)
                continue
            if score > best_score:
                best_score = score
                best = provider

        if best:
            log.info("检测到主语言: %s (置信度 %.2f)", best.language_id, best_score)
        else:
            log.info("未检测到已注册语言")
        return best

    def detect_all(self, repo_root: Path) -> list[tuple[LanguageProvider, float]]:
        """检测仓库中所有语言，返回 (Provider, 置信度) 列表，按置信度降序.

        用于 monorepo 多语言共存场景。
        """
        results: list[tuple[LanguageProvider, float]] = []
        for provider in self._providers.values():
            try:
                score = provider.detect(repo_root)
            except Exception:
                log.warning("Provider %s detect 异常", provider.language_id, exc_info=True)
                continue
            if score > 0:
                results.append((provider, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @property
    def registered_languages(self) -> list[str]:
        """已注册的语言 ID 列表."""
        return list(self._providers.keys())


# ---------------------------------------------------------------------------
# 全局 Registry 单例
# ---------------------------------------------------------------------------

_global_registry: LanguageRegistry | None = None


def get_registry() -> LanguageRegistry:
    """获取全局 Registry 单例.

    首次调用时自动创建并注册内置 Provider。
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = LanguageRegistry()
        _register_builtin_providers(_global_registry)
    return _global_registry


def _register_builtin_providers(registry: LanguageRegistry) -> None:
    """注册内置 Provider."""
    # Java Provider
    try:
        from qualix.languages.java.provider import JavaProvider

        registry.register(JavaProvider())
    except ImportError:
        log.debug("JavaProvider not available")

    # TypeScript Provider
    try:
        from qualix.languages.typescript.provider import TypeScriptProvider

        registry.register(TypeScriptProvider())
    except ImportError:
        log.debug("TypeScriptProvider not available")
