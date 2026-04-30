"""VLM Provider 抽象接口 + 工厂函数。

所有 provider 用 urllib.request 发 HTTP，不依赖任何第三方 SDK。
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@runtime_checkable
class VlmProvider(Protocol):
    """VLM provider interface."""

    backend_name: str

    def analyze_image(self, image_path: Path, prompt: str) -> str:
        """分析图片，返回文本结果。失败时抛出 RuntimeError。"""
        ...


def image_to_base64(image_path: Path) -> tuple[str, str]:
    """读取图片并返回 (base64_data, mime_type)。"""
    mime = MIME_MAP.get(image_path.suffix.lower(), "image/png")
    data = image_path.read_bytes()
    return base64.b64encode(data).decode("ascii"), mime


def get_vlm_provider(
    backend: str = "auto",
    api_key: str = "",
    model: str = "",
    timeout: int = 120,
) -> VlmProvider | None:
    """工厂函数：根据 backend 名称返回对应 provider。

    backend: "anthropic" | "openai" | "dashscope" | "auto" | "none"
    auto: 按环境变量自动检测
    """
    if backend == "none":
        return None

    if backend == "auto":
        return _auto_detect(api_key, model, timeout)

    if backend == "dashscope":
        from dqg.media.vlm.dashscope_provider import DashScopeProvider

        key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        if not key:
            return None
        return DashScopeProvider(api_key=key, model=model or "qwen-vl-max", timeout=timeout)

    if backend == "anthropic":
        from dqg.media.vlm.anthropic_provider import AnthropicProvider

        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return None
        return AnthropicProvider(api_key=key, model=model or "claude-sonnet-4-6-20250514", timeout=timeout)

    if backend == "openai":
        from dqg.media.vlm.openai_provider import OpenAIProvider

        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            return None
        return OpenAIProvider(api_key=key, model=model or "gpt-4o", timeout=timeout)

    return None


def _auto_detect(api_key: str, model: str, timeout: int) -> VlmProvider | None:
    """按环境变量优先级自动检测可用 provider。"""
    for backend in ("anthropic", "openai", "dashscope"):
        provider = get_vlm_provider(backend=backend, api_key=api_key, model=model, timeout=timeout)
        if provider is not None:
            return provider
    return None
