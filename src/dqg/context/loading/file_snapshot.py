"""File Snapshot: 轻量增量检测 — sha256 hash 比对跳过未变更文件.

核心思路：
- 每次 context loading 后，把读取的文件列表 + sha256 + mtime 存为快照
- 下次加载前比对快照，未变更的文件直接跳过重读
- 快照存在 Phase 的 _internal/_context_snapshot.json

适用场景：
- DAG 模式：多 Phase 连续执行，上游产物在同一 run 内不变
- 手动模式重跑：critique 后修正再跑，大部分输入文件未变
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

SNAPSHOT_FILENAME = "_context_snapshot.json"


def _file_hash(path: Path) -> str:
    """计算文件 sha256（前 64KB 快速哈希，大文件不全读）."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(65536))
    except OSError:
        return ""
    return h.hexdigest()


def _file_entry(path: Path) -> dict[str, Any]:
    """构建单个文件的快照条目."""
    try:
        stat = path.stat()
        return {
            "path": str(path),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "hash": _file_hash(path),
        }
    except OSError:
        return {"path": str(path), "mtime": 0, "size": 0, "hash": ""}


def take_snapshot(files: list[Path]) -> dict[str, dict[str, Any]]:
    """对一组文件生成快照（path → entry）."""
    return {str(p): _file_entry(p) for p in files if p.exists()}


def save_snapshot(snapshot_dir: Path, snapshot: dict[str, dict[str, Any]]) -> Path:
    """持久化快照到 _internal/_context_snapshot.json."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / SNAPSHOT_FILENAME
    save_json(path, snapshot)
    return path


def load_snapshot(snapshot_dir: Path) -> dict[str, dict[str, Any]]:
    """加载上次的快照."""
    path = snapshot_dir / SNAPSHOT_FILENAME
    data = load_json(path)
    if isinstance(data, dict):
        return data
    return {}


def diff_snapshot(
    old: dict[str, dict[str, Any]],
    new_files: list[Path],
) -> tuple[list[Path], list[Path]]:
    """比对快照，返回 (changed, unchanged) 文件列表.

    比对策略（快速路径优先）：
    1. 文件不在旧快照中 → changed
    2. mtime + size 都没变 → unchanged（快速路径，不算 hash）
    3. mtime 或 size 变了 → 算 hash 再比
    """
    changed: list[Path] = []
    unchanged: list[Path] = []

    for p in new_files:
        if not p.exists():
            continue
        key = str(p)
        old_entry = old.get(key)

        if not old_entry:
            changed.append(p)
            continue

        try:
            stat = p.stat()
        except OSError:
            changed.append(p)
            continue

        # 快速路径：mtime + size 都没变
        if stat.st_mtime == old_entry.get("mtime") and stat.st_size == old_entry.get("size"):
            unchanged.append(p)
            continue

        # 慢路径：hash 比对
        new_hash = _file_hash(p)
        if new_hash == old_entry.get("hash") and new_hash:
            unchanged.append(p)
        else:
            changed.append(p)

    return changed, unchanged
