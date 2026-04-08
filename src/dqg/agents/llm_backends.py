"""LLM Backend 抽象层: 模型配置 + 多后端实现."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# LLM Backend 抽象层
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """模型配置，支持主模型+备用模型."""
    primary: str = "claude-opus-4-6"
    fallback: str | None = "deepseek-chat"
    temperature: float = 0.0
    max_tokens: int = 8192
    timeout: int = 120

    # API 配置（从环境变量读取）
    _MODEL_KEY_MAP = {
        "claude": "ANTHROPIC_API_KEY",
        "opus": "ANTHROPIC_API_KEY",
        "sonnet": "ANTHROPIC_API_KEY",
        "haiku": "ANTHROPIC_API_KEY",
        "gpt": "OPENAI_API_KEY",
        "o1": "OPENAI_API_KEY",
        "o3": "OPENAI_API_KEY",
        "o4": "OPENAI_API_KEY",
        "codex": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "kimi": "MOONSHOT_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
    }

    def _resolve_api_key(self, model: str) -> str:
        for prefix, env_var in self._MODEL_KEY_MAP.items():
            if prefix in model.lower():
                return os.environ.get(env_var, "")
        return os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def primary_api_key(self) -> str:
        return self._resolve_api_key(self.primary)

    @property
    def fallback_api_key(self) -> str:
        if not self.fallback:
            return ""
        return self._resolve_api_key(self.fallback)


class LLMBackend(ABC):
    """LLM 后端抽象接口."""

    @abstractmethod
    def chat(self, messages: list[dict[str, Any]], **kwargs) -> tuple[str, dict[str, int]]:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class AnthropicBackend(LLMBackend):
    """Claude API 后端."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 8192):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, Any]], **kwargs) -> tuple[str, dict[str, int]]:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)
        system_blocks = []
        chat_msgs = []
        for m in messages:
            content = m.get("content", "")
            if m["role"] == "system":
                if len(content) > 500:
                    system_blocks.append({
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"}
                    })
                else:
                    system_blocks.append({
                        "type": "text",
                        "text": content
                    })
            else:
                cache_control = m.get("cache_control", False)
                if cache_control or len(content) > 2000:
                    chat_msgs.append({
                        "role": m["role"],
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })
                else:
                    chat_msgs.append(m)

        system_param = system_blocks if system_blocks else ""

        response = client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            system=system_param,
            messages=chat_msgs,
            extra_headers={"anthropic-beta": "prompt-caching-2024-09-02"}
        )

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        # Capture cache tokens if available
        if hasattr(response.usage, "cache_creation_input_tokens"):
            usage["cache_creation_input_tokens"] = response.usage.cache_creation_input_tokens
        if hasattr(response.usage, "cache_read_input_tokens"):
            usage["cache_read_input_tokens"] = response.usage.cache_read_input_tokens

        return response.content[0].text, usage

    def name(self) -> str:
        return f"anthropic:{self.model}"


class OpenAICompatibleBackend(LLMBackend):
    """OpenAI 兼容 API 后端（支持 GPT/Codex/DeepSeek/Qwen/Kimi/Moonshot）."""

    # 模型 → 默认 base_url
    _BASE_URLS = {
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "kimi": "https://api.moonshot.cn/v1",
        "moonshot": "https://api.moonshot.cn/v1",
    }

    def __init__(self, model: str, api_key: str, base_url: str | None = None, max_tokens: int = 8192):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or self._default_base_url(model)
        self.max_tokens = max_tokens

    def _default_base_url(self, model: str) -> str:
        for prefix, url in self._BASE_URLS.items():
            if prefix in model.lower():
                return url
        return "https://api.openai.com/v1"

    def chat(self, messages: list[dict[str, Any]], **kwargs) -> tuple[str, dict[str, int]]:
        try:
            import openai
        except ImportError:
            raise RuntimeError("pip install openai")

        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        # remove cache_control tags as openai doesn't support them in direct messages same way
        clean_msgs = []
        for m in messages:
            clean_msgs.append({"role": m["role"], "content": m["content"]})

        response = client.chat.completions.create(
            model=self.model,
            messages=clean_msgs,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", 0.0),
        )

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return response.choices[0].message.content, usage

    def name(self) -> str:
        return f"openai-compat:{self.model}"


class GeminiBackend(LLMBackend):
    """Google Gemini API 后端."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 8192):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, Any]], **kwargs) -> tuple[str, dict[str, int]]:
        try:
            import google.generativeai as genai
        except ImportError:
            # fallback: 用 OpenAI 兼容接口
            return self._chat_via_openai_compat(messages, **kwargs)

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)

        # 转换消息格式
        system = ""
        history = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "user":
                history.append({"role": "user", "parts": [m["content"]]})
            elif m["role"] == "assistant":
                history.append({"role": "model", "parts": [m["content"]]})

        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        prompt = history[-1]["parts"][0] if history else ""
        if system:
            prompt = f"{system}\n\n{prompt}"

        response = chat.send_message(prompt)
        # Gemini usage approximation
        usage = {}
        if hasattr(response, "usage_metadata"):
            usage = {
                "input_tokens": response.usage_metadata.prompt_token_count,
                "output_tokens": response.usage_metadata.candidates_token_count,
            }
        return response.text, usage

    def _chat_via_openai_compat(self, messages: list[dict[str, Any]], **kwargs) -> tuple[str, dict[str, int]]:
        """通过 OpenAI 兼容接口调用 Gemini."""
        try:
            import openai
        except ImportError:
            raise RuntimeError("pip install openai 或 pip install google-generativeai")

        client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        clean_msgs = []
        for m in messages:
            clean_msgs.append({"role": m["role"], "content": m["content"]})

        response = client.chat.completions.create(
            model=self.model,
            messages=clean_msgs,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", 0.0),
        )
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return response.choices[0].message.content, usage

    def name(self) -> str:
        return f"gemini:{self.model}"


def create_backend(model: str, api_key: str) -> LLMBackend:
    """根据模型名自动选择后端."""
    ml = model.lower()
    if any(k in ml for k in ("claude", "opus", "sonnet", "haiku")):
        return AnthropicBackend(model, api_key)
    elif "gemini" in ml:
        return GeminiBackend(model, api_key)
    else:
        # GPT/Codex/DeepSeek/Qwen/Kimi 都走 OpenAI 兼容
        return OpenAICompatibleBackend(model, api_key)
