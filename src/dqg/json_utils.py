"""统一 JSON 操作工具函数.

消除全局 43+ 次 json.loads(path.read_text()) 和 59+ 次
json.dumps(..., ensure_ascii=False, indent=2) 的重复模式。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    """读取 JSON 文件并解析，失败返回 None."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_json_strict(path: Path) -> Any:
    """读取 JSON 文件并解析，失败抛异常."""
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any, *, indent: int = 2, sort_keys: bool = False) -> None:
    """将数据写入 JSON 文件."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys),
        encoding="utf-8",
    )


def dump_json_str(data: Any, *, indent: int | None = 2) -> str:
    """序列化为 JSON 字符串（ensure_ascii=False）."""
    return json.dumps(data, ensure_ascii=False, indent=indent)


def dump_jsonl(data: Any) -> str:
    """序列化为单行 JSONL 格式（无 indent，带换行）."""
    return json.dumps(data, ensure_ascii=False) + "\n"
