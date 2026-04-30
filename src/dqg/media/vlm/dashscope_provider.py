"""DashScope VLM provider — 优先用 SDK（向后兼容），fallback 到 urllib HTTP。"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dqg.media.vlm.provider import image_to_base64

if TYPE_CHECKING:
    from pathlib import Path

DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


@dataclass
class DashScopeProvider:
    api_key: str
    model: str = "qwen-vl-max"
    timeout: int = 120
    backend_name: str = field(default="vlm:dashscope", init=False)

    def analyze_image(self, image_path: Path, prompt: str) -> str:
        sdk = _try_load_sdk(self.api_key)
        if sdk is not None:
            return _call_via_sdk(sdk, image_path, prompt, self.model, self.timeout)
        return _call_via_http(self.api_key, image_path, prompt, self.model, self.timeout)


def _try_load_sdk(api_key: str) -> object | None:
    try:
        import dashscope  # type: ignore[import-untyped]

        dashscope.api_key = api_key
        return dashscope
    except Exception:
        return None


def _call_via_sdk(dashscope: object, image_path: Path, prompt: str, model: str, timeout: int) -> str:
    """从 parse_images.py 迁移的 SDK 调用逻辑。"""
    response = dashscope.MultiModalConversation.call(  # type: ignore[attr-defined]
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"image": str(image_path)},
                    {"text": prompt},
                ],
            }
        ],
        timeout=timeout,
    )

    if getattr(response, "status_code", None) != 200:
        code = getattr(response, "code", "unknown")
        msg = getattr(response, "message", "unknown error")
        raise RuntimeError(f"DashScope SDK 调用失败: code={code}, message={msg}")

    output = response.output if hasattr(response, "output") else {}
    choices = output.get("choices", []) if isinstance(output, dict) else []
    if not choices:
        raise RuntimeError("DashScope SDK 返回内容为空")

    message = choices[0].get("message", {})
    content = message.get("content", [])
    if isinstance(content, list):
        text_parts = [str(item.get("text")) for item in content if isinstance(item, dict) and item.get("text")]
        result = "\n".join(text_parts).strip()
        if result:
            return result

    text = choices[0].get("text") or ""
    if text:
        return str(text)

    raise RuntimeError("无法解析 DashScope SDK 返回文本")


def _call_via_http(api_key: str, image_path: Path, prompt: str, model: str, timeout: int) -> str:
    """纯 HTTP fallback，不依赖 dashscope SDK。"""
    b64, mime = image_to_base64(image_path)

    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:{mime};base64,{b64}"},
                        {"text": prompt},
                    ],
                }
            ]
        },
    }

    req = urllib.request.Request(
        DASHSCOPE_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        raise RuntimeError(f"DashScope HTTP {exc.code}: {body}") from exc

    output = data.get("output", {})
    choices = output.get("choices", [])
    if not choices:
        raise RuntimeError("DashScope HTTP 返回内容为空")

    message = choices[0].get("message", {})
    content = message.get("content", [])
    if isinstance(content, list):
        text_parts = [str(item.get("text")) for item in content if isinstance(item, dict) and item.get("text")]
        result = "\n".join(text_parts).strip()
        if result:
            return result

    raise RuntimeError("无法解析 DashScope HTTP 返回文本")
