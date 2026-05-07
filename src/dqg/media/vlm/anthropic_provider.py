"""Anthropic Claude vision provider — 纯 urllib，零 SDK 依赖。"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dqg.media.vlm.provider import image_to_base64

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"


def _api_url() -> str:
    base = os.getenv("ANTHROPIC_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}/v1/messages"
    return _DEFAULT_API_URL


@dataclass
class AnthropicProvider:
    api_key: str
    model: str = "claude-sonnet-4-6-20250514"
    timeout: int = 120
    backend_name: str = field(default="vlm:anthropic", init=False)

    def analyze_image(self, image_path: Path, prompt: str) -> str:
        b64, mime = image_to_base64(image_path)

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime, "data": b64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        req = urllib.request.Request(
            _api_url(),
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise RuntimeError(f"Anthropic API {exc.code}: {body}") from exc

        content = data.get("content", [])
        texts = [block["text"] for block in content if block.get("type") == "text" and block.get("text")]
        if not texts:
            raise RuntimeError("Anthropic API 返回内容为空")
        return "\n".join(texts).strip()
