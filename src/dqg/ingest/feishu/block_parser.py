"""Block type parsing and element extraction from Feishu document blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dqg.ingest.common import BLOCK_TYPE_NAME

if TYPE_CHECKING:
    from collections.abc import Callable


def extract_text_from_elements(elements: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for elem in elements or []:
        if "text_run" in elem:
            text_run = elem.get("text_run", {})
            content = (text_run.get("content", "") or "").replace("\u3000", " ")
            if content:
                parts.append(content)
            continue
        if "mention_user" in elem:
            mention = elem.get("mention_user", {})
            user_id = mention.get("user_id", "") or mention.get("name", "")
            if user_id:
                parts.append(f"@{user_id}")
            continue
        if "mention_doc" in elem:
            mention_doc = elem.get("mention_doc", {})
            title = mention_doc.get("title") or mention_doc.get("token") or "文档"
            parts.append(str(title))
            continue
        if "equation" in elem:
            equation = elem.get("equation", {})
            content = equation.get("content") or equation.get("equation") or ""
            if content:
                parts.append(f"${content}$")
    return "".join(parts).strip()


def get_block_elements(block: dict[str, Any]) -> list[dict[str, Any]]:
    bt = int(block.get("block_type", 0) or 0)
    if bt == 2:
        return block.get("text", {}).get("elements", []) or []
    if 3 <= bt <= 11:
        heading = block.get(f"heading{bt - 2}", {})
        return heading.get("elements", []) or []
    if bt == 12:
        return block.get("bullet", {}).get("elements", []) or []
    if bt == 13:
        return block.get("ordered", {}).get("elements", []) or []
    if bt == 14:
        return block.get("code", {}).get("elements", []) or []
    if bt == 15:
        return block.get("quote", {}).get("elements", []) or []
    if bt == 17:
        return block.get("todo", {}).get("elements", []) or []
    if bt == 19:
        return block.get("callout", {}).get("elements", []) or []
    return []


def collect_mention_docs(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for block in blocks:
        block_id = str(block.get("block_id", "") or "")
        for elem in get_block_elements(block):
            if not isinstance(elem, dict):
                continue
            mention = elem.get("mention_doc")
            if not isinstance(mention, dict):
                continue
            token = str(mention.get("token", "") or "")
            url = str(mention.get("url", "") or "")
            title = str(mention.get("title", "") or "")
            obj_type = str(mention.get("obj_type", "") or "")
            key = (token, url, title, obj_type)

            row = found.get(key)
            if row is None:
                found[key] = {
                    "token": token,
                    "url": url,
                    "title": title,
                    "obj_type": obj_type,
                    "source_block_ids": [block_id] if block_id else [],
                }
                continue
            if block_id and block_id not in row["source_block_ids"]:
                row["source_block_ids"].append(block_id)
    return list(found.values())


def extract_block_text(
    block: dict[str, Any],
    get_code_language: Callable[[int], str],
) -> tuple[str, dict[str, Any]]:
    bt = int(block.get("block_type", 0) or 0)

    if bt == 2:
        return extract_text_from_elements(block.get("text", {}).get("elements", [])), {}
    if 3 <= bt <= 11:
        level = bt - 2
        heading = block.get(f"heading{level}", {})
        return extract_text_from_elements(heading.get("elements", [])), {"heading_level": level}
    if bt == 12:
        return extract_text_from_elements(block.get("bullet", {}).get("elements", [])), {"list_kind": "bullet"}
    if bt == 13:
        return extract_text_from_elements(block.get("ordered", {}).get("elements", [])), {"list_kind": "ordered"}
    if bt == 14:
        code = block.get("code", {})
        style = code.get("style", {}) if isinstance(code, dict) else {}
        language_id = int(style.get("language", 0) or 0)
        text = extract_text_from_elements(code.get("elements", []))
        return text, {"code_lang": get_code_language(language_id)}
    if bt == 15:
        return extract_text_from_elements(block.get("quote", {}).get("elements", [])), {"quote": True}
    if bt == 17:
        todo = block.get("todo", {})
        text = extract_text_from_elements(todo.get("elements", []))
        done = bool((todo.get("style") or {}).get("done", False))
        return text, {"todo_done": done}
    if bt == 19:
        return extract_text_from_elements(block.get("callout", {}).get("elements", [])), {"callout": True}
    return "", {}


def extract_media_asset(block: dict[str, Any], section_path: str) -> dict[str, Any] | None:
    bt = int(block.get("block_type", 0) or 0)
    block_id = block.get("block_id", "")
    if bt == 27 and "image" in block:
        image = block.get("image", {})
        token = image.get("token", "")
        if token:
            return {
                "kind": "image",
                "token": token,
                "name": image.get("name") or "",
                "alt": image.get("alt") or "",
                "block_id": block_id,
                "section_path": section_path,
                "source": "block",
            }
    if bt in (43, 44) and "board" in block:
        board = block.get("board", {})
        token = board.get("token", "")
        if token:
            return {
                "kind": "board",
                "token": token,
                "name": "board",
                "alt": "",
                "block_id": block_id,
                "section_path": section_path,
                "source": "block",
            }
    if bt == 29 and "mindnote" in block:
        mindnote = block.get("mindnote", {})
        token = mindnote.get("token", "")
        if token:
            return {
                "kind": "mindnote",
                "token": token,
                "name": "mindnote",
                "alt": "",
                "block_id": block_id,
                "section_path": section_path,
                "source": "block",
            }
    return None


def find_root_block_id(block_map: dict[str, dict[str, Any]]) -> str | None:
    for block_id, block in block_map.items():
        if int(block.get("block_type", 0) or 0) == 1:
            return block_id
    for block_id, block in block_map.items():
        parent_id = block.get("parent_id", "")
        if not parent_id:
            return block_id
    return next(iter(block_map), None)
