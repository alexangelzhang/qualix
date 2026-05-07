"""OpenRouter vision provider — OpenAI 兼容接口，支持多模型。"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dqg.media.vlm.provider import image_to_base64

if TYPE_CHECKING:
    from pathlib import Path

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class OpenRouterProvider:
    api_key: str
    model: str = "anthropic/claude-sonnet-4-5"
    timeout: int = 120
    backend_name: str = field(default="vlm:openrouter", init=False)

    def analyze_image(self, image_path: Path, prompt: str) -> str:
        b64, mime = image_to_base64(image_path)

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "provider": {"order": ["Anthropic"], "allow_fallbacks": False},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        site_url = os.getenv("OPENROUTER_SITE_URL", "https://github.com/dev-quality-gate")
        req = urllib.request.Request(
            OPENROUTER_API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": site_url,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise RuntimeError(f"OpenRouter API {exc.code}: {body}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenRouter API 返回内容为空")
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise RuntimeError("OpenRouter API 返回文本为空")
        return text.strip()
