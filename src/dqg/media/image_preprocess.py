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

from dqg.json_utils import load_json


def compress_images(assets_dir: Path, max_width: int = 800) -> dict[str, Any]:
    """压缩图片到指定宽度，返回压缩统计.

    压缩后的图片存到 assets_dir/_compressed/ 目录。
    """
    compressed_dir = assets_dir / "_compressed"
    compressed_dir.mkdir(exist_ok=True)

    stats = {"total": 0, "compressed": 0, "skipped": 0, "saved_kb": 0}

    try:
        from PIL import Image
    except ImportError:
        # Pillow 不可用时跳过压缩
        stats["skipped_reason"] = "Pillow not installed"
        return stats

    for img_path in sorted(assets_dir.glob("*.png")):
        stats["total"] += 1
        try:
            with Image.open(img_path) as img:
                w, h = img.size
                if w <= max_width:
                    stats["skipped"] += 1
                    continue

                ratio = max_width / w
                new_size = (max_width, int(h * ratio))
                resized = img.resize(new_size, Image.LANCZOS)

                out_path = compressed_dir / img_path.name
                resized.save(out_path, "PNG", optimize=True)

                original_kb = img_path.stat().st_size / 1024
                compressed_kb = out_path.stat().st_size / 1024
                stats["saved_kb"] += original_kb - compressed_kb
                stats["compressed"] += 1
        except Exception:
            stats["skipped"] += 1

    return stats


def classify_images(assets_dir: Path) -> dict[str, list[str]]:
    """将图片分为 board（深度解析）和 image（浅度解析）."""
    boards = []
    images = []
    for f in sorted(assets_dir.glob("*.png")):
        if f.name.startswith("board_"):
            boards.append(f.name)
        elif f.name.startswith("image_"):
            images.append(f.name)
    return {"board": boards, "image": images}


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
        description = f"{section + ' - ' if section else ''}{ctx}" if ctx else f"页面原型（位置: segment {seg.get('seq', i)}）"

        results.append({
            "filename": filename,
            "kind": "image",
            "description": description,
            "related_reqs": [],
            "section_context": section or ctx,
        })

    return results


def get_compressed_path(assets_dir: Path, filename: str) -> Path:
    """获取压缩后的图片路径（不存在则返回原图路径）."""
    compressed = assets_dir / "_compressed" / filename
    if compressed.exists():
        return compressed
    return assets_dir / filename
