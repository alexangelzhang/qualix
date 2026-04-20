"""统一 JSON 操作工具函数.

消除全局 43+ 次 json.loads(path.read_text()) 和 59+ 次
json.dumps(..., ensure_ascii=False, indent=2) 的重复模式。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 模块级 JSON 解析缓存：按 (路径, mtime_ns, size) 缓存，文件变更自动失效
_json_cache: dict[tuple[str, int, int], Any] = {}


def load_json(path: Path) -> Any:
    """读取 JSON 文件并解析（带缓存），失败返回 None."""
    try:
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        cached = _json_cache.get(key)
        if cached is not None:
            return cached
        data = json.loads(path.read_text(encoding="utf-8"))
        _json_cache[key] = data
        return data
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
