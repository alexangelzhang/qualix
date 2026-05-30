"""OpenAI GPT-4V vision provider — 纯 urllib，零 SDK 依赖。"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qualix.media.vlm.provider import image_to_base64

if TYPE_CHECKING:
    from pathlib import Path

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class OpenAIProvider:
    api_key: str
    model: str = "gpt-4o"
    timeout: int = 120
    backend_name: str = field(default="vlm:openai", init=False)

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
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise RuntimeError(f"OpenAI API {exc.code}: {body}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenAI API 返回内容为空")
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise RuntimeError("OpenAI API 返回文本为空")
        return text.strip()
