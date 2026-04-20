"""Chunk Summarizer: 跨 Phase 传递时用 ID 级摘要替代全文.

从 chunk_processor.py 拆分而来，负责：
1. 从结构化 JSON 生成 ID 级摘要
2. 从 Markdown 报告提取标题 + 关键段落
3. 上游 chunk 自动摘要（summarize_upstream_chunk）
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from dqg.constants import ID_PATTERN_BASE
from dqg.core.model_registry import estimate_tokens
from dqg.log import get_logger

if TYPE_CHECKING:
    from dqg.context.context_loader import ContextChunk

log = get_logger(__name__)

_ID_PATTERN = re.compile(ID_PATTERN_BASE)


def _extract_ids_by_type(text: str) -> dict[str, list[str]]:
    """从文本中提取所有结构化 ID，按类型分组."""
    ids: dict[str, list[str]] = {}
    for match in _ID_PATTERN.finditer(text):
        id_str = match.group(0)
        prefix = id_str.split("-")[0]
        ids.setdefault(prefix, [])
        if id_str not in ids[prefix]:
            ids[prefix].append(id_str)
    return ids


def _summarize_structured_json(content: str, phase_id: str) -> str | None:
    """从结构化 JSON 生成 ID 级摘要.

    返回格式：
    ## Phase A 结构化摘要
    - 需求 ID: REQ-001, REQ-002, ... (共 N 条)
    - 已识别 GAP: GAP-001(状态), GAP-002(状态) (共 N 条)
    - 未闭环 OPEN: OPEN-001, OPEN-002 (共 N 条)
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    lines = [f"## Phase {phase_id} 结构化摘要"]

    # 提取各类 ID 列表
    id_fields = {
        "requirements": ("需求", "REQ/BR/SE"),
        "gaps": ("缺口", "GAP"),
        "open_items": ("待确认", "OPEN"),
        "eut_items": ("测试单元", "EUT"),
        "findings": ("发现", "FINDING"),
        "audit_items": ("审计项", "AUDIT"),
    }

    for field_key, (label, _prefix) in id_fields.items():
        items = data.get(field_key)
        if not items or not isinstance(items, list):
            continue

        count = len(items)
        # 提取前 5 个 ID 作为示例
        sample_ids = []
        for item in items[:5]:
            if isinstance(item, dict):
                for k in ("req_id", "br_id", "se_id", "gap_id", "open_id",
                          "eut_id", "case_id", "id", "finding_id"):
                    v = item.get(k)
                    if v:
                        status = item.get("status", "")
                        sample_ids.append(f"{v}({status})" if status else str(v))
                        break

        if sample_ids:
            ids_str = ", ".join(sample_ids)
            suffix = f", ... " if count > 5 else ""
            lines.append(f"- {label}: {ids_str}{suffix}(共 {count} 条)")
        else:
            lines.append(f"- {label}: {count} 条")

    # 提取关键决策/结论（如果有）
    for key in ("conclusion", "summary", "overall_assessment"):
        val = data.get(key)
        if val and isinstance(val, str):
            lines.append(f"- 结论: {val[:200]}")
            break

    if len(lines) <= 1:
        return None

    return "\n".join(lines)


def _summarize_report(content: str, phase_id: str) -> str | None:
    """从 Markdown 报告提取标题 + 关键段落（首段/结论段）."""
    lines = content.split("\n")
    headings: list[str] = []
    first_para: list[str] = []
    conclusion_para: list[str] = []
    in_conclusion = False
    current_para: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped)
            lower = stripped.lower()
            in_conclusion = any(kw in lower for kw in ("结论", "总结", "summary", "conclusion", "总评"))
            if current_para and not first_para:
                first_para = list(current_para)
            current_para = []
        elif stripped:
            current_para.append(stripped)
            if in_conclusion:
                conclusion_para.append(stripped)
        else:
            if current_para and not first_para:
                first_para = list(current_para)
            current_para = []

    if not headings:
        return None

    parts = [f"## Phase {phase_id} 报告摘要", "### 结构"]
    parts.extend(headings[:15])
    if first_para:
        parts.append("### 开篇")
        parts.append(" ".join(first_para[:5]))
    if conclusion_para:
        parts.append("### 结论")
        parts.append(" ".join(conclusion_para[:8]))

    return "\n".join(parts)


def summarize_upstream_chunk(chunk: ContextChunk, phase_id: str, force: bool = False) -> ContextChunk:
    """将上游 Phase 的 chunk 转为结构化摘要.

    所有上游 chunk 默认走摘要模式：
    - 结构化 JSON -> ID 级摘要
    - 报告 -> 标题 + 关键段落
    - 其他文本 -> 截断压缩
    force 参数保留向后兼容但不再影响行为。
    """
    from dqg.context.context_loader import ContextChunk as _CC

    # 结构化产物：生成 ID 级摘要
    if "结构化产物" in chunk.source:
        summary = _summarize_structured_json(chunk.content, phase_id)
        if summary:
            tokens = estimate_tokens(summary)
            log.info(
                "Summarized upstream chunk '%s': %d -> %d tokens",
                chunk.source, chunk.token_estimate, tokens,
            )
            return _CC(
                source=f"{chunk.source} (structured-summary)",
                content=summary,
                token_estimate=tokens,
                priority=chunk.priority,
            )

    # 报告类 chunk：提取标题 + 关键段落
    if "报告" in chunk.source and chunk.token_estimate > 300:
        report_summary = _summarize_report(chunk.content, phase_id)
        if report_summary:
            tokens = estimate_tokens(report_summary)
            log.info(
                "Summarized upstream report '%s': %d -> %d tokens",
                chunk.source, chunk.token_estimate, tokens,
            )
            return _CC(
                source=f"{chunk.source} (report-summary)",
                content=report_summary,
                token_estimate=tokens,
                priority=chunk.priority,
            )

    # 其他文本类 chunk：默认截断压缩
    _DEFAULT_CHAR_LIMIT = 2000
    if chunk.token_estimate > 500 and len(chunk.content) > _DEFAULT_CHAR_LIMIT:
        truncated = chunk.content[:_DEFAULT_CHAR_LIMIT] + "\n\n<!-- upstream-summarized -->"
        tokens = estimate_tokens(truncated)
        log.info(
            "Truncated upstream chunk '%s': %d -> %d tokens",
            chunk.source, chunk.token_estimate, tokens,
        )
        return _CC(
            source=f"{chunk.source} (truncated-summary)",
            content=truncated,
            token_estimate=tokens,
            priority=chunk.priority,
        )

    return chunk
