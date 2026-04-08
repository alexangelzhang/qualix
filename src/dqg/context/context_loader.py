"""Context Loader: 自动加载上游 Phase 产物，注入下游 prompt.

核心职责：
1. 根据 Phase 依赖关系，自动收集上游产物
2. 根据模型 token budget 做智能分块
3. 生成 retrieval-first evidence pack，而不是全文拼接
4. 支持跨 session 恢复（从持久化的 JSON/markdown 加载）
5. Token 预算自动压缩：达到 80% budget 时压缩最旧的 chunk
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from dqg.constants import (
    BUG_CASE_RELEVANCE_SEED_LIMIT,
    EVIDENCE_PACK_HEADER,
    EVIDENCE_PACK_MAX_QUOTES,
    EVIDENCE_PACK_QUOTE_CHAR_LIMIT,
    EVIDENCE_PACK_SUMMARY_MAX_LINES,
    EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT,
)
from dqg.context.chunk_processor import (
    _auto_compact_chunks,
    _collect_current_phase_inputs,
    _collect_phase_artifacts,
    _split_large_chunk,
)
from dqg.context.doc_summary import extract_summary
from dqg.core.model_registry import ModelProfile, estimate_tokens, get_model_profile
from dqg.core.profiles import get_profile, load_profile_context
from dqg.core.state_machine import PHASE_DEFS, PhaseStatus, load_state
from dqg.path_utils import resolve_internal_file
from dqg.skill_tracker import render_relevant_cases_for_prompt

_KEY_QUOTE_PATTERN = re.compile(
    r"REQ-|BR-|SE-|GAP-|OPEN-|状态|流程|权限|异常|并发|幂等|校验|提示|接口|字段|图片|泳道|Mermaid",
    re.IGNORECASE,
)
_ID_KEYS: tuple[str, ...] = (
    "req_id",
    "br_id",
    "se_id",
    "gap_id",
    "open_id",
    "fact_id",
    "id",
    "case_id",
)


@dataclass
class ContextChunk:
    """一个上下文分块."""

    source: str  # 来源描述，如 "Phase A 结构化产物"
    content: str
    token_estimate: int
    priority: int = 0  # 越小越优先


@dataclass
class LoadedContext:
    """加载完成的上下文."""

    phase_id: str
    model: ModelProfile
    chunks: list[ContextChunk] = field(default_factory=list)
    truncated: bool = False
    total_tokens: int = 0
    budget_tokens: int = 0

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
            lines.extend(["", f"### {chunk.source}", _render_chunk_body(chunk)])

        key_quotes = _render_key_quotes(self.chunks)
        if key_quotes:
            lines.extend(["", "## 关键引用", *key_quotes])

        return "\n".join(lines)

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


def _truncate_chars(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...(截断)"


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


def _sample_ids(items: list[object], max_items: int = 3) -> list[str]:
    samples: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in _ID_KEYS:
            value = item.get(key)
            if value:
                samples.append(str(value))
                break
        if len(samples) >= max_items:
            break
    return samples


def _summarize_json_content(content: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return _truncate_chars(content, EVIDENCE_PACK_QUOTE_CHAR_LIMIT)

    lines: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                line = f"- {key}: {len(value)} 项"
                samples = _sample_ids(value)
                if samples:
                    line += f"；示例: {', '.join(samples)}"
                lines.append(line)
            elif isinstance(value, dict):
                lines.append(f"- {key}: {len(value)} 个字段")
            elif value not in (None, "", []):
                rendered = _truncate_chars(str(value), 80).replace("\n", " ")
                lines.append(f"- {key}: {rendered}")
    elif isinstance(data, list):
        lines.append(f"- list: {len(data)} 项")
        samples = _sample_ids(data)
        if samples:
            lines.append(f"- 示例: {', '.join(samples)}")
    else:
        lines.append(f"- value: {_truncate_chars(str(data), 120)}")

    return "\n".join(lines[: min(EVIDENCE_PACK_SUMMARY_MAX_LINES, 12)]) or _truncate_chars(content, 200)


def _summarize_text_content(content: str) -> str:
    summary = extract_summary(content, max_lines=min(EVIDENCE_PACK_SUMMARY_MAX_LINES, 12)).strip()
    if not summary:
        paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
        summary = "\n\n".join(paragraphs[:2])
    return _truncate_chars(summary, 1_200)


def _render_chunk_body(chunk: ContextChunk) -> str:
    content = chunk.content.strip()
    if not content:
        return "（空）"

    if "Bug cases" in chunk.source or "Diff context" in chunk.source:
        return _truncate_chars(content, 2_000)
    if content.startswith("{") or content.startswith("["):
        return _summarize_json_content(content)
    return _summarize_text_content(content)


def _pick_quote_candidates(content: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    candidates: list[str] = []
    for para in paragraphs:
        if para.startswith(("#", "- ", "|")) or _KEY_QUOTE_PATTERN.search(para):
            candidates.append(para)
    if not candidates:
        candidates = paragraphs[:2]

    deduped: list[str] = []
    seen: set[str] = set()
    for para in candidates:
        normalized = para.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _render_key_quotes(chunks: list[ContextChunk]) -> list[str]:
    lines: list[str] = []
    quote_count = 0
    used_chars = 0

    for chunk in chunks:
        if quote_count >= EVIDENCE_PACK_MAX_QUOTES or used_chars >= EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT:
            break
        for para in _pick_quote_candidates(chunk.content):
            if quote_count >= EVIDENCE_PACK_MAX_QUOTES or used_chars >= EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT:
                break
            remaining = EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT - used_chars
            if remaining <= 0:
                break
            quote = _truncate_chars(para, min(EVIDENCE_PACK_QUOTE_CHAR_LIMIT, remaining))
            if not quote:
                continue
            quote_count += 1
            used_chars += len(quote)
            lines.append(f"### 引用 {quote_count}: {chunk.source}")
            lines.extend(f"> {line}" for line in quote.splitlines())
            lines.append("")

    if not lines:
        return ["（无可用关键引用）"]
    if lines[-1] == "":
        lines.pop()
    return lines


def load_context(
    output_dir: Path,
    project_id: str,
    target_phase: str,
    model_name: str | None = None,
) -> LoadedContext:
    """为目标 Phase 加载上游产物上下文.

    自动：
    1. 根据依赖关系找到需要加载的上游 Phase
    2. 收集本 Phase 输入证据与上游产物
    3. 按优先级排序
    4. 根据模型 token budget 截断
    """
    model = get_model_profile(model_name)
    budget = model.available_for_context

    phase_def = PHASE_DEFS.get(target_phase)
    if not phase_def:
        return LoadedContext(phase_id=target_phase, model=model, budget_tokens=budget)

    state = load_state(output_dir, project_id)
    upstream_phases = phase_def["depends_on"]
    phase_root = output_dir / project_id / phase_def["dir_suffix"]

    all_chunks: list[ContextChunk] = []
    inject_bug_cases = target_phase in {"A", "A.5", "A.6", "B", "C", "D"}

    current_phase_chunks = _collect_current_phase_inputs(phase_root, target_phase)
    if current_phase_chunks:
        all_chunks.extend(current_phase_chunks)

    if target_phase in {"A.5", "A.6", "B", "C", "D"}:
        profile = get_profile(getattr(state, "profile_id", None))
        profile_context = load_profile_context(profile)
        all_chunks.append(
            ContextChunk(
                source=f"Profile {profile.profile_id} baseline and thresholds",
                content=profile_context,
                token_estimate=estimate_tokens(profile_context),
                priority=-1,
            )
        )

    for dep_id in upstream_phases:
        dep_state = state.phases.get(dep_id)
        if dep_state and dep_state.status in (PhaseStatus.APPROVED, PhaseStatus.PENDING_REVIEW):
            all_chunks.extend(_collect_phase_artifacts(output_dir, project_id, dep_id))

    if target_phase in ("C", "D"):
        diff_path = resolve_internal_file(phase_root, "_diff_context.md")
        if diff_path.exists():
            diff_text = diff_path.read_text(encoding="utf-8")
            all_chunks.append(
                ContextChunk(
                    source=f"Diff context for Phase {target_phase} (incremental)",
                    content=diff_text,
                    token_estimate=estimate_tokens(diff_text),
                    priority=-2,
                )
            )

    mem_file = Path(".dqg/MEMORY.md")
    if mem_file.exists():
        mem_text = mem_file.read_text(encoding="utf-8")
        if mem_text.strip():
            all_chunks.append(
                ContextChunk(
                    source="Persistent Memory (.dqg/MEMORY.md)",
                    content=mem_text,
                    token_estimate=estimate_tokens(mem_text),
                    priority=-3,
                )
            )

    if inject_bug_cases:
        relevance_input = _build_relevance_seed(all_chunks)
        if relevance_input.strip():
            bug_cases_md = render_relevant_cases_for_prompt(target_phase, relevance_input)
            if bug_cases_md:
                all_chunks.append(
                    ContextChunk(
                        source=f"Bug cases for Phase {target_phase} (relevance-matched)",
                        content=bug_cases_md,
                        token_estimate=estimate_tokens(bug_cases_md),
                        priority=0,
                    )
                )

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
    )
