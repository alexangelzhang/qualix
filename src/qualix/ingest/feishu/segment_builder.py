"""Build document segments and media assets from parsed Feishu blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qualix.ingest.common import BLOCK_TYPE_NAME
from qualix.ingest.feishu.block_parser import (
    extract_block_text,
    extract_media_asset,
    find_root_block_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def build_segments_and_assets(
    blocks: list[dict[str, Any]],
    get_code_language: Callable[[int], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    block_map: dict[str, dict[str, Any]] = {}
    for block in blocks:
        block_id = block.get("block_id", "")
        if block_id:
            block_map[block_id] = block

    root_id = find_root_block_id(block_map)
    if not root_id:
        return [], [], ""

    seq = 0
    visited: set[str] = set()
    segments: list[dict[str, Any]] = []
    media_assets_raw: list[dict[str, Any]] = []
    plain_lines: list[str] = []

    def walk(
        block_id: str,
        depth: int,
        section_stack: list[dict[str, Any]],
        list_stack: list[str],
    ) -> None:
        nonlocal seq
        if block_id in visited:
            return
        block = block_map.get(block_id)
        if not block:
            return

        visited.add(block_id)
        bt = int(block.get("block_type", 0) or 0)
        block_name = BLOCK_TYPE_NAME.get(bt, f"unknown_{bt}")
        text, meta = extract_block_text(block, get_code_language)

        next_sections = list(section_stack)
        heading_level = meta.get("heading_level")
        if heading_level and text:
            next_sections = [item for item in next_sections if item["level"] < heading_level]
            next_sections.append({"level": heading_level, "text": text})

        next_list_stack = list(list_stack)
        if bt == 12:
            next_list_stack.append("bullet")
        elif bt == 13:
            next_list_stack.append("ordered")
        elif bt == 17:
            next_list_stack.append("todo")

        section_path = " > ".join([item["text"] for item in next_sections if item.get("text")])
        media = extract_media_asset(block, section_path)
        if media:
            media_assets_raw.append(media)

        seq += 1
        segment: dict[str, Any] = {
            "seq": seq,
            "block_id": block.get("block_id", ""),
            "parent_id": block.get("parent_id", ""),
            "block_type": bt,
            "block_type_name": block_name,
            "depth": depth,
            "section_path": section_path,
            "list_depth": len(list_stack),
        }
        if text:
            segment["text"] = text
        if meta:
            segment.update(meta)
        if media:
            segment["media"] = {
                "kind": media["kind"],
                "token": media["token"],
                "name": media.get("name", ""),
            }
        segments.append(segment)

        if text:
            if bt in range(3, 12):
                plain_lines.append(f"{'#' * min(bt - 2, 6)} {text}")
            elif bt in (12, 17):
                plain_lines.append(f"{'  ' * max(len(list_stack) - 1, 0)}- {text}")
            elif bt == 13:
                plain_lines.append(f"{'  ' * max(len(list_stack) - 1, 0)}1. {text}")
            elif bt == 14:
                lang = segment.get("code_lang", "")
                plain_lines.append(f"```{lang}")
                plain_lines.append(text)
                plain_lines.append("```")
            else:
                plain_lines.append(text)

        for child_id in block.get("children", []) or []:
            walk(str(child_id), depth + 1, next_sections, next_list_stack)

    walk(root_id, 0, [], [])
    for block_id in list(block_map.keys()):
        if block_id not in visited:
            walk(block_id, 0, [], [])

    dedup_assets: dict[tuple[str, str], dict[str, Any]] = {}
    for asset in media_assets_raw:
        key = (asset["kind"], asset["token"])
        existing = dedup_assets.get(key)
        if existing is None:
            asset["source_block_ids"] = [asset.get("block_id", "")] if asset.get("block_id") else []
            dedup_assets[key] = asset
            continue
        block_id = asset.get("block_id", "")
        if block_id:
            existing.setdefault("source_block_ids", []).append(block_id)

    plain_text = "\n".join(plain_lines).strip() + "\n"
    return segments, list(dedup_assets.values()), plain_text
