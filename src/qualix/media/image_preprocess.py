"""图片预处理：压缩 + 分级解析，降低 token 消耗.

策略：
1. 所有图片压缩到 max 800px 宽（token 减半）
2. Board 类深度解析（状态机/流程图 → Mermaid）
3. Image 类浅度解析（只记录"这是XX页面原型"）
4. 解析结果存入 SQLite 缓存，后续不再读图片
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qualix.json_utils import load_json


def crop_whitespace(image_path: Path, padding: int = 20) -> bytes | None:
    """裁剪图片四周空白，返回裁剪后的 PNG bytes。

    适用于飞书 board 导出图片：有效内容只占画布一小角，大面积空白
    会导致 VLM 在压缩/采样后丢失内容。

    返回 None 表示 Pillow 不可用或裁剪无意义（内容已占满画布）。
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        import io

        img = Image.open(image_path).convert("RGB")
        w, h = img.size

        inverted = ImageOps.invert(img.convert("L"))
        bbox = inverted.getbbox()
        if not bbox:
            return None

        # 内容已占满画布（留 10% 余量），不裁剪
        content_ratio = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (w * h)
        if content_ratio > 0.9:
            return None

        x1 = max(0, bbox[0] - padding)
        y1 = max(0, bbox[1] - padding)
        x2 = min(w, bbox[2] + padding)
        y2 = min(h, bbox[3] + padding)
        cropped = img.crop((x1, y1, x2, y2))

        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def build_shallow_descriptions(
    assets_dir: Path,
    ingest_json_path: Path,
) -> list[dict[str, Any]]:
    """从 ingest.json 的上下文信息为 image 类图片生成浅度描述（不读图片）."""
    if not ingest_json_path.exists():
        return []

    data = load_json(ingest_json_path)
    if data is None:
        return []

    segments = data.get("segments", [])
    results = []

    for i, seg in enumerate(segments):
        media = seg.get("media")
        if not media:
            continue

        kind = media.get("kind", "image")
        token = media.get("token", "")
        filename = f"{kind}_{token}.png"

        # 只处理 image 类（board 类需要深度解析）
        if kind != "image":
            continue

        # 从前面的 segment 获取上下文
        ctx = ""
        for j in range(i - 1, max(i - 5, 0), -1):
            t = segments[j].get("text", "").strip()
            if t and len(t) > 3:
                ctx = t[:80]
                break

        section = seg.get("section_path", "")
        description = (
            f"{section + ' - ' if section else ''}{ctx}" if ctx else f"页面原型（位置: segment {seg.get('seq', i)}）"
        )

        results.append(
            {
                "filename": filename,
                "kind": "image",
                "description": description,
                "related_reqs": [],
                "section_context": section or ctx,
            }
        )

    return results


def get_compressed_path(assets_dir: Path, filename: str) -> Path:
    """获取压缩后的图片路径（不存在则返回原图路径）."""
    compressed = assets_dir / "_compressed" / filename
    if compressed.exists():
        return compressed
    return assets_dir / filename
