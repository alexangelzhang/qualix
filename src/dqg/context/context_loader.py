"""Context Loader: 自动加载上游 Phase 产物，注入下游 prompt.

核心职责：
1. 根据 Phase 依赖关系，自动收集上游产物
2. 根据模型 token budget 做智能分块
3. 生成 retrieval-first evidence pack，而不是全文拼接
4. 支持跨 session 恢复（从持久化的 JSON/markdown 加载）
5. Token 预算自动压缩：达到 80% budget 时压缩最旧的 chunk
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from dqg.constants import (
    BUG_CASE_RELEVANCE_SEED_LIMIT,
    EVIDENCE_PACK_HEADER,
)
from dqg.context.evidence_renderer import render_chunk_body, render_key_quotes
from dqg.core.model_registry import ModelProfile, get_model_profile
from dqg.core.state_machine import PHASE_DEFS, load_state

# Re-export for backward compatibility (chunk_processor imports ContextChunk from here)
__all__ = ["ContextChunk", "LoadedContext", "load_context"]


@dataclass
class ContextChunk:
    """一个上下文分块."""

    source: str  # 来源描述，如 "Phase A 结构化产物"
    content: str
    token_estimate: int
    priority: int = 0  # 越小越优先
    file_path: str = ""  # 源文件路径，用于 citation 定位


@dataclass
class LoadedContext:
    """加载完成的上下文."""

    phase_id: str
    model: ModelProfile
    chunks: list[ContextChunk] = field(default_factory=list)
    truncated: bool = False
    total_tokens: int = 0
    budget_tokens: int = 0
    verification_targets: list[dict] | None = None

    def render_evidence_pack(self) -> str:
        """渲染 retrieval-first evidence pack."""
        lines = [
            EVIDENCE_PACK_HEADER,
            "",
            "## Pack 概览",
            f"- Target Phase: {self.phase_id}",
            f"- Context Budget: ~{self.total_tokens} / {self.budget_tokens} tokens",
            f"- Truncated: {'yes' if self.truncated else 'no'}",
            f"- Evidence Chunks: {len(self.chunks)}",
        ]

        if not self.chunks:
            lines.extend(["", "## 证据摘要", "（当前没有可注入的上游或本 Phase 证据）"])
            return "\n".join(lines)

        lines.extend(["", "## 证据摘要"])
        for chunk in self.chunks:
            lines.extend(["", f"### {chunk.source}", render_chunk_body(chunk)])

        # 根据 root cause 趋势动态调整 Evidence Pack 参数
        priority_ids = None
        if self.verification_targets:
            from dqg.runtime.phase_contract import extract_priority_ids

            priority_ids = extract_priority_ids(self.verification_targets)

        try:
            from dqg.quality.root_cause_tuner import get_adjusted_evidence_limits

            limits = get_adjusted_evidence_limits(self.phase_id)
            key_quotes = render_key_quotes(
                self.chunks,
                max_quotes=limits["max_quotes"],
                total_char_limit=limits["total_quote_char_limit"],
                priority_ids=priority_ids,
            )
        except Exception:
            from dqg.log import get_logger

            get_logger(__name__).warning("动态 evidence limits 调整失败，使用默认值", exc_info=True)
            key_quotes = render_key_quotes(self.chunks, priority_ids=priority_ids)
        if key_quotes:
            lines.extend(["", "## 关键引用", *key_quotes])

        result = "\n".join(lines)

        # Lossless compression: reduce Evidence Pack token footprint
        try:
            from dqg.context.prompt_compressor import compress, compression_ratio

            compressed = compress(result)
            ratio = compression_ratio(result, compressed)
            if ratio >= 0.08:
                from dqg.log import get_logger

                get_logger(__name__).info(
                    "Evidence Pack compressed: %.0f%% reduction (%d → %d chars)",
                    ratio * 100,
                    len(result),
                    len(compressed),
                )
                return compressed
        except Exception:
            from dqg.log import get_logger

            get_logger(__name__).warning("Evidence Pack 压缩失败，使用原文", exc_info=True)

        return result

    def iter_rendered_blocks(self):
        """按 block 产出 evidence pack 文本。"""
        yield self.render_evidence_pack()

    def write_full_text(self, path: Path) -> None:
        """将 evidence pack 写入文件，避免整份原文再次进入 prompt。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render_evidence_pack(), encoding="utf-8")

    @property
    def relevance_seed(self) -> str:
        """为 bug case relevance matching 提供轻量种子文本."""
        return _build_relevance_seed(self.chunks)

    @property
    def full_text(self) -> str:
        """返回渲染后的 evidence pack 文本."""
        return self.render_evidence_pack()

    @property
    def summary(self) -> str:
        """加载摘要."""
        status = "完整加载" if not self.truncated else "已截断"
        return (
            f"Phase {self.phase_id} 上下文: "
            f"{len(self.chunks)} chunks, "
            f"~{self.total_tokens} tokens / {self.budget_tokens} budget, "
            f"{status}"
        )


# --- Relevance seed helpers (used by upstream_collector) ---


def _is_relevance_seed_chunk(chunk: ContextChunk) -> bool:
    if chunk.source.startswith("Profile "):
        return False
    if chunk.source.startswith("Persistent Memory "):
        return False
    return "Bug cases for Phase" not in chunk.source


def _build_relevance_seed(chunks: list[ContextChunk]) -> str:
    parts: list[str] = []
    remaining = BUG_CASE_RELEVANCE_SEED_LIMIT
    for chunk in chunks:
        if remaining <= 0:
            break
        if not _is_relevance_seed_chunk(chunk):
            continue
        snippet = chunk.content[: min(1_000, remaining)].strip()
        if not snippet:
            continue
        parts.append(snippet)
        remaining -= len(snippet)
    return " ".join(parts)


# --- Assembly ---


def _assemble_context(
    target_phase: str,
    model: ModelProfile,
    budget: int,
    all_chunks: list[ContextChunk],
    verification_targets: list[dict] | None = None,
) -> LoadedContext:
    """排序、分块、压缩、截断，组装最终 LoadedContext."""
    from dqg.context.chunk_processor import _auto_compact_chunks, _split_large_chunk

    all_chunks.sort(key=lambda c: c.priority)

    max_chunk_tokens = budget // 3
    expanded: list[ContextChunk] = []
    for chunk in all_chunks:
        expanded.extend(_split_large_chunk(chunk, max_chunk_tokens))

    expanded, _ = _auto_compact_chunks(expanded, budget)

    selected: list[ContextChunk] = []
    used_tokens = 0
    truncated = False

    for chunk in expanded:
        if used_tokens + chunk.token_estimate <= budget:
            selected.append(chunk)
            used_tokens += chunk.token_estimate
            continue

        truncated = True
        remaining = budget - used_tokens
        if remaining > 500:
            ratio = remaining / chunk.token_estimate
            cut_pos = int(len(chunk.content) * ratio)
            cut_pos = chunk.content.rfind("\n\n", 0, cut_pos)
            if cut_pos > 0:
                truncated_content = chunk.content[:cut_pos] + "\n\n<!-- ... 已截断 -->"
                selected.append(
                    ContextChunk(
                        source=f"{chunk.source} (截断)",
                        content=truncated_content,
                        token_estimate=remaining,
                        priority=chunk.priority,
                    )
                )
                used_tokens += remaining
        break

    return LoadedContext(
        phase_id=target_phase,
        model=model,
        chunks=selected,
        truncated=truncated,
        total_tokens=used_tokens,
        budget_tokens=budget,
        verification_targets=verification_targets,
    )


# --- Public API ---


def load_context(
    output_dir: Path,
    project_id: str,
    target_phase: str,
    model_name: str | None = None,
) -> LoadedContext:
    """为目标 Phase 加载上游产物上下文.

    自动：
    1. 根据依赖关系找到需要加载的上游 Phase
    2. 收集本 Phase 输入证据与上游产物（并行 I/O）
    3. 加载 sidecar 文件（diff, memory, bug cases）
    4. 按优先级排序，根据模型 token budget 截断
    """
    from dqg.context.upstream_collector import load_sidecar_context, load_upstream_context

    model = get_model_profile(model_name)
    budget = model.available_for_context

    phase_def = PHASE_DEFS.get(target_phase)
    if not phase_def:
        return LoadedContext(phase_id=target_phase, model=model, budget_tokens=budget)

    # Reasoning Sandwich：根据 reasoning_profile 动态调整 budget
    reasoning_profile = phase_def.get("reasoning_profile", {})
    execution_level = reasoning_profile.get("execution", "standard")
    if execution_level == "standard" and reasoning_profile:
        budget = int(budget * 0.6)

    state = load_state(output_dir, project_id)
    upstream_phases = phase_def["depends_on"]
    phase_root = output_dir / project_id / phase_def["dir_suffix"]

    # Phase 1: 并行加载上游产物 + 当前 Phase 输入
    all_chunks, _ = load_upstream_context(
        output_dir,
        project_id,
        target_phase,
        phase_root,
        state,
        upstream_phases,
    )

    # Phase 2: 加载 sidecar（diff, memory, bug cases）
    load_sidecar_context(output_dir, project_id, target_phase, phase_root, all_chunks)

    # Phase 2.5: 加载 verification_targets（用于 Oracle-guided evidence selection）
    verification_targets = None
    contract_path = phase_root / "_internal" / "_phase_contract.json"
    if contract_path.exists():
        from dqg.json_utils import load_json

        contract = load_json(contract_path)
        if contract:
            verification_targets = contract.get("verification_targets")

    # Phase 3: 组装最终 context
    return _assemble_context(target_phase, model, budget, all_chunks, verification_targets)
