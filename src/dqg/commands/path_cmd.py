from __future__ import annotations

from dqg.core.resource_resolver import ResourceResolver

_ALLOWED = {"skills", "references", "profiles", "regression"}


def run_path(category: str) -> int:
    """打印内置资源目录的绝对路径（只读查看）."""
    if category not in _ALLOWED:
        print(f"错误: 未知类别 '{category}'。可用: {', '.join(sorted(_ALLOWED))}")
        return 1
    try:
        path = ResourceResolver().resolve_dir(category)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        return 2
    print(path)
    return 0
