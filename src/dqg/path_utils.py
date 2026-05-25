"""路径工具函数."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.constants import UPSTREAM_EMBEDDED_CONTEXT_FILES

if TYPE_CHECKING:
    from pathlib import Path


def resolve_with_fallback(primary: Path, fallback: Path) -> Path:
    """返回存在的路径，优先 primary，不存在则返回 fallback（不保证 fallback 存在）."""
    return primary if primary.exists() else fallback


def resolve_phase_file(phase_dir: Path, filename: str, *subdirs: str) -> Path:
    """解析 Phase 目录中的文件路径.

    按给定子目录顺序查找，最后回退到 Phase 根目录，兼容旧布局和新布局。
    """
    candidates = [phase_dir / subdir / filename for subdir in subdirs if subdir]
    root_path = phase_dir / filename
    if root_path not in candidates:
        candidates.append(root_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else root_path


def resolve_ingest_file(phase_dir: Path, filename: str) -> Path:
    """解析 ingest 产物路径：新路径（ingest/）优先，旧路径（phase 根目录）fallback."""
    return resolve_phase_file(phase_dir, filename, "ingest")


def resolve_internal_file(phase_dir: Path, filename: str) -> Path:
    """解析过程文件路径：新路径（_internal/）优先，旧路径（phase 根目录）fallback."""
    return resolve_phase_file(phase_dir, filename, "_internal")


def resolve_context_files(phase_dir: Path) -> list[Path]:
    """收集 Agent / perf 需要读取的上下文文件.

    统一兼容旧布局（Phase 根目录）和新布局（_internal/、ingest/）。
    """
    file_specs: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("_phase_map.md", ("_internal",)),  # phase-map 置首：aider repo-map 思路，先建全局感知
        ("_upstream_context.md", ("_internal",)),
        ("_profile_context.md", ("_internal",)),
        ("_bug_cases.md", ("_internal",)),
        ("_diff_context.md", ("_internal",)),
        ("image_semantics.md", tuple()),
        ("plain_text_summary.md", ("ingest",)),
        ("plain_text.txt", ("ingest",)),
    )

    seen: set[Path] = set()
    files: list[Path] = []
    for filename, subdirs in file_specs:
        path = resolve_phase_file(phase_dir, filename, *subdirs)
        if path.exists() and path not in seen:
            seen.add(path)
            files.append(path)
    return files


def resolve_effective_context_files(phase_dir: Path) -> list[Path]:
    """返回去重后的有效上下文文件列表。

    `load_context()` 产出的 `_upstream_context.md` 已经内联了高成本的
    profile / bug cases / diff 内容。
    当它存在时，Agent 链路不再重复注入这些 side files，避免 token 双算。
    """
    files = resolve_context_files(phase_dir)
    names = {path.name for path in files}
    if "_upstream_context.md" not in names:
        return files

    duplicated_side_files = set(UPSTREAM_EMBEDDED_CONTEXT_FILES)
    return [path for path in files if path.name not in duplicated_side_files]
