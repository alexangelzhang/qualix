"""Chunk Processor: 上下文分块的收集、拆分与压缩.

从 context_loader.py 拆分而来，负责：
1. 安全读取文件
2. 收集 Phase 产物文件
3. 超大 chunk 按段落分块
4. chunk 压缩（代码块/表格/段落截断）
5. 自动压缩（超过 budget 阈值时）
6. 结构化摘要（跨 Phase 传递时用 ID 级摘要替代全文）
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dqg.core.model_registry import estimate_tokens
from dqg.core.state_machine import PHASE_DEFS
from dqg.log import get_logger
from dqg.path_utils import resolve_ingest_file
from dqg.text_utils import REPORT_MAP, STRUCTURED_JSON_MAP

log = get_logger(__name__)

# 模块级文件读取缓存：mtime 感知，避免返回过期内容（上限 128 条防止内存泄漏）
_file_cache: dict[str, tuple[int, str | None]] = {}  # key → (mtime_ns, content)
_FILE_CACHE_MAX_SIZE = 128

# 避免循环导入：运行时从 context_loader 导入 ContextChunk
if TYPE_CHECKING:
    from pathlib import Path

    from dqg.context.loading.context_loader import ContextChunk


def _read_file_safe(path: Path) -> str | None:
    """安全读取文件（带 mtime 感知缓存）."""
    key = str(path)
    if not path.exists():
        _file_cache[key] = (0, None)
        return None

    try:
        current_mtime = path.stat().st_mtime_ns
    except OSError:
        return None

    cached = _file_cache.get(key)
    if cached is not None:
        cached_mtime, cached_content = cached
        if cached_mtime == current_mtime:
            return cached_content

    try:
        content = path.read_text(encoding="utf-8")
        if len(_file_cache) >= _FILE_CACHE_MAX_SIZE:
            _file_cache.clear()
        _file_cache[key] = (current_mtime, content)
        return content
    except OSError:
        log.warning("Failed to read file: %s", path)
        _file_cache[key] = (current_mtime, None)
        return None


def _estimate_tokens_cached(text: str, cache: dict[str, int]) -> int:
    """带局部缓存的 token 估算.

    同一个 chunk 里常会重复出现相同段落或重复的压缩中间态，
    这里用轻量缓存避免重复扫同一段文本。
    """
    cached = cache.get(text)
    if cached is not None:
        return cached

    tokens = estimate_tokens(text)
    cache[text] = tokens
    return tokens


def _collect_phase_artifacts(output_dir: Path, project_id: str, phase_id: str) -> list[ContextChunk]:
    """收集某个 Phase 的产物文件."""
    from dqg.context.loading.context_loader import ContextChunk

    chunks: list[ContextChunk] = []
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return chunks

    dir_suffix = phase_def["dir_suffix"]
    phase_dir = output_dir / project_id / dir_suffix

    if not phase_dir.is_dir():
        return chunks

    has_structured = False

    # 优先加载结构化 JSON（紧凑、token 效率高）
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        content = _read_file_safe(phase_dir / json_file)
        if content:
            has_structured = True
            chunks.append(
                ContextChunk(
                    source=f"Phase {phase_id} 结构化产物 ({json_file})",
                    content=content,
                    token_estimate=estimate_tokens(content),
                    priority=0,  # 最高优先级
                    file_path=str(phase_dir / json_file),
                )
            )

    # 其次加载当前 phase 的 markdown 报告
    report_file = REPORT_MAP.get(phase_id)
    if report_file:
        path = phase_dir / report_file
        content = _read_file_safe(path)
        if content:
            has_structured = True
            chunks.append(
                ContextChunk(
                    source=f"Phase {phase_id} 报告 ({report_file})",
                    content=content,
                    token_estimate=estimate_tokens(content),
                    priority=1,
                    file_path=str(path),
                )
            )

    # 加载图片语义缓存（如果存在），避免下游重新读图片
    image_semantics = _read_file_safe(phase_dir / "image_semantics.md")
    if image_semantics:
        chunks.append(
            ContextChunk(
                source=f"Phase {phase_id} 图片语义缓存 (image_semantics.md)",
                content=image_semantics,
                token_estimate=estimate_tokens(image_semantics),
                priority=1,  # 与 markdown 报告同优先级
                file_path=str(phase_dir / "image_semantics.md"),
            )
        )

    # 仅在没有结构化产物时才加载文本（避免重复消耗 token）
    # 优先加载摘要版本，其次原文
    if not has_structured:
        summary_text = _read_file_safe(resolve_ingest_file(phase_dir, "plain_text_summary.md"))
        if summary_text:
            chunks.append(
                ContextChunk(
                    source=f"Phase {phase_id} 文档摘要 (plain_text_summary.md)",
                    content=summary_text,
                    token_estimate=estimate_tokens(summary_text),
                    priority=2,
                )
            )
        else:
            plain_text = _read_file_safe(resolve_ingest_file(phase_dir, "plain_text_enhanced.txt")) or _read_file_safe(
                resolve_ingest_file(phase_dir, "plain_text.txt")
            )
            if plain_text:
                chunks.append(
                    ContextChunk(
                        source=f"Phase {phase_id} 原始文本 (plain_text.txt)",
                        content=plain_text,
                        token_estimate=estimate_tokens(plain_text),
                        priority=2,  # 最低优先级
                    )
                )

    return chunks


def _collect_current_phase_inputs(phase_dir: Path, phase_id: str) -> list[ContextChunk]:
    """收集当前 Phase 的输入证据和重跑基线产物。"""
    from dqg.context.loading.context_loader import ContextChunk

    chunks: list[ContextChunk] = []
    if not phase_dir.is_dir():
        return chunks

    image_semantics = _read_file_safe(phase_dir / "image_semantics.md")
    if image_semantics:
        chunks.append(
            ContextChunk(
                source=f"Current Phase {phase_id} 图片语义缓存 (image_semantics.md)",
                content=image_semantics,
                token_estimate=estimate_tokens(image_semantics),
                priority=0,
            )
        )

    summary_text = _read_file_safe(resolve_ingest_file(phase_dir, "plain_text_summary.md"))
    if summary_text:
        chunks.append(
            ContextChunk(
                source=f"Current Phase {phase_id} 文档摘要 (plain_text_summary.md)",
                content=summary_text,
                token_estimate=estimate_tokens(summary_text),
                priority=0,
            )
        )
    else:
        for filename in ("aggregate_plain_text.txt", "plain_text_enhanced.txt", "plain_text.txt"):
            raw_text = _read_file_safe(resolve_ingest_file(phase_dir, filename))
            if raw_text:
                chunks.append(
                    ContextChunk(
                        source=f"Current Phase {phase_id} 原始文本 ({filename})",
                        content=raw_text,
                        token_estimate=estimate_tokens(raw_text),
                        priority=3,
                    )
                )
                break

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        structured = _read_file_safe(phase_dir / json_file)
        if structured:
            chunks.append(
                ContextChunk(
                    source=f"Current Phase {phase_id} 上次结构化产物 ({json_file})",
                    content=structured,
                    token_estimate=estimate_tokens(structured),
                    priority=1,
                )
            )

    report_file = REPORT_MAP.get(phase_id)
    if report_file:
        report = _read_file_safe(phase_dir / report_file)
        if report:
            chunks.append(
                ContextChunk(
                    source=f"Current Phase {phase_id} 上次报告 ({report_file})",
                    content=report,
                    token_estimate=estimate_tokens(report),
                    priority=2,
                )
            )

    return chunks


def _split_large_chunk(chunk: ContextChunk, max_tokens: int) -> list[ContextChunk]:
    """将超大 chunk 按段落分块."""
    from dqg.context.loading.context_loader import ContextChunk

    if chunk.token_estimate <= max_tokens:
        return [chunk]

    # 按双换行分段
    paragraphs = chunk.content.split("\n\n")
    sub_chunks: list[ContextChunk] = []
    current_parts: list[str] = []
    current_tokens = 0
    token_cache: dict[str, int] = {}

    for para in paragraphs:
        para_tokens = _estimate_tokens_cached(para, token_cache)
        if current_tokens + para_tokens > max_tokens and current_parts:
            sub_chunks.append(
                ContextChunk(
                    source=f"{chunk.source} (part {len(sub_chunks) + 1})",
                    content="\n\n".join(current_parts),
                    token_estimate=current_tokens,
                    priority=chunk.priority,
                )
            )
            current_parts = []
            current_tokens = 0

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        sub_chunks.append(
            ContextChunk(
                source=f"{chunk.source} (part {len(sub_chunks) + 1})",
                content="\n\n".join(current_parts),
                token_estimate=current_tokens,
                priority=chunk.priority,
            )
        )

    return sub_chunks


def _compact_chunk(chunk: ContextChunk, target_tokens: int) -> ContextChunk:
    """压缩一个 chunk 到目标 token 数.

    压缩策略（按优先级）：
    1. 移除代码块内容（保留标记）
    2. 移除表格的中间行（保留表头和前 3 行）
    3. 按段落截断
    """
    from dqg.context.loading.context_loader import ContextChunk

    if chunk.token_estimate <= target_tokens:
        return chunk

    content = chunk.content
    original_tokens = chunk.token_estimate
    token_cache: dict[str, int] = {}

    # 策略 1: 压缩代码块（保留语言标记和首尾行）
    def compress_code_block(match: object) -> str:
        block = match.group(0)
        lines = block.split("\n")
        if len(lines) <= 4:
            return block
        return f"{lines[0]}\n{lines[1]}\n  ... ({len(lines) - 3} lines omitted)\n{lines[-1]}"

    compressed = re.sub(r"```\w*\n[\s\S]*?```", compress_code_block, content)
    compressed_tokens = _estimate_tokens_cached(compressed, token_cache)
    if compressed_tokens <= target_tokens:
        return ContextChunk(
            source=f"{chunk.source} (compressed)",
            content=compressed,
            token_estimate=compressed_tokens,
            priority=chunk.priority,
        )

    # 策略 2: 压缩表格（保留表头 + 前 3 行）
    def compress_table(match: object) -> str:
        table = match.group(0)
        lines = table.strip().split("\n")
        if len(lines) <= 5:  # header + separator + 3 rows
            return table
        kept = lines[:5]
        kept.append(f"| ... ({len(lines) - 5} rows omitted) |")
        return "\n".join(kept)

    compressed = re.sub(r"(\|[^\n]+\|\n){4,}", compress_table, compressed)
    compressed_tokens = _estimate_tokens_cached(compressed, token_cache)
    if compressed_tokens <= target_tokens:
        return ContextChunk(
            source=f"{chunk.source} (compressed)",
            content=compressed,
            token_estimate=compressed_tokens,
            priority=chunk.priority,
        )

    # 策略 3: 按段落截断
    paragraphs = compressed.split("\n\n")
    kept_parts: list[str] = []
    kept_tokens = 0
    for para in paragraphs:
        para_tokens = _estimate_tokens_cached(para, token_cache)
        if kept_tokens + para_tokens > target_tokens:
            break
        kept_parts.append(para)
        kept_tokens += para_tokens

    if kept_parts:
        kept_parts.append(f"\n<!-- compressed: {original_tokens} → {kept_tokens} tokens -->")
        return ContextChunk(
            source=f"{chunk.source} (compressed)",
            content="\n\n".join(kept_parts),
            token_estimate=kept_tokens,
            priority=chunk.priority,
        )

    # 最后兜底：硬截断
    ratio = target_tokens / max(original_tokens, 1)
    cut_pos = int(len(content) * ratio)
    return ContextChunk(
        source=f"{chunk.source} (hard-truncated)",
        content=content[:cut_pos] + "\n\n<!-- hard-truncated -->",
        token_estimate=target_tokens,
        priority=chunk.priority,
    )


def _auto_compact_chunks(
    chunks: list[ContextChunk],
    budget: int,
    compact_threshold: float = 0.8,
) -> tuple[list[ContextChunk], bool]:
    """当总 token 超过 budget 的 compact_threshold 时，自动压缩最旧（优先级最低）的 chunk.

    Returns:
        (compacted_chunks, was_compacted)
    """
    total_tokens = sum(c.token_estimate for c in chunks)
    threshold = int(budget * compact_threshold)

    if total_tokens <= threshold:
        return chunks, False

    # 从优先级最低（数字最大）的 chunk 开始压缩
    sorted_by_priority = sorted(enumerate(chunks), key=lambda x: -x[1].priority)
    result = list(chunks)
    current_total = total_tokens

    for idx, chunk in sorted_by_priority:
        if current_total <= threshold:
            break

        # 计算这个 chunk 需要压缩到多少
        excess = current_total - threshold
        target = max(chunk.token_estimate - excess, chunk.token_estimate // 3)  # 至少保留 1/3

        compacted = _compact_chunk(chunk, target)
        saved = chunk.token_estimate - compacted.token_estimate
        result[idx] = compacted
        current_total -= saved

    return result, True


# ---------------------------------------------------------------------------
# Backward-compat re-export: summarize_upstream_chunk moved to chunk_summarizer
# Lazy import to break context_loader ↔ chunk_processor ↔ chunk_summarizer cycle
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    if name == "summarize_upstream_chunk":
        from .chunk_summarizer import summarize_upstream_chunk

        return summarize_upstream_chunk
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
