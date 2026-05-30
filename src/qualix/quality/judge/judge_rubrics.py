"""Judge rubric logic: compose shared + routed + dynamic rubric for Judge consumption."""

from __future__ import annotations

from typing import Any, Final

from qualix.constants import SHARED_RUBRIC_DIMENSIONS

from ._rubric_data import ANTI_RATIONALIZATION_SECTION, JUDGE_RUBRICS

# Re-export for backward compatibility
__all__ = [
    "ANTI_RATIONALIZATION_SECTION",
    "JUDGE_RUBRICS",
    "compose_rubric",
    "compose_rubric_compact",
    "compose_rubric_layered",
    "compose_rubric_structured",
]

# Phase → routed rubric dimensions (layer-independent weights, each layer sums to 100%).
PHASE_ROUTED_RUBRICS: Final[dict[str, list[dict[str, Any]]]] = {
    phase_id: rubric["dimensions"] for phase_id, rubric in JUDGE_RUBRICS.items()
}


def compose_rubric_structured(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Compose shared + routed + dynamic dimensions as structured list.

    Each layer keeps its own weights (no cross-layer normalization):
    - Shared: 4 dims × 0.25 each (sum to 1.0 within layer)
    - Routed: original JUDGE_RUBRICS weights (already sum to 1.0)
    - Dynamic: each dim keeps its own weight (0.15 each)
    """
    # Shared: scale to 0.25 each so layer sums to 1.0
    shared = [dict(d) for d in SHARED_RUBRIC_DIMENSIONS]
    for d in shared:
        d["weight"] = 0.25

    # Routed: keep original weights (already sum to 1.0)
    routed = [dict(d) for d in PHASE_ROUTED_RUBRICS.get(phase_id, [])]

    all_dims = shared + routed
    if dynamic_dimensions:
        all_dims.extend(dict(d) for d in dynamic_dimensions)

    return all_dims


def _render_dimension(dim: dict[str, Any], compact: bool = False, brief: bool = False) -> str:
    """Render a single dimension as rubric text for Judge.

    No weight shown — Judge must check every dimension equally.
    Weights are kept in structured data for evaluation/calibration layer only.
    brief=True: only show name + description, no scoring rubric (for shared dims).
    compact=True: only show scores 5/3/1 to reduce token footprint.
    """
    lines = [
        f"### {dim['id']}: {dim.get('name', '')}",
        f"{dim.get('description', '')}",
    ]
    if brief:
        return "\n".join(lines)
    rubric = dim.get("rubric", {})
    keep_scores = {5, 3, 1} if compact else set(rubric.keys())
    for score in sorted(rubric.keys(), reverse=True):
        if score in keep_scores:
            lines.append(f"  - {score}分: {rubric[score]}")
    return "\n".join(lines)


def compose_rubric(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> str:
    """Compose shared + routed + dynamic rubric as rendered text for Judge consumption.

    Weights are intentionally omitted from the rendered text — this is a quality
    gate system, not a scoring system. Every dimension must be checked thoroughly.
    Weights exist only in compose_rubric_structured() for evaluation/calibration.
    """
    dims = compose_rubric_structured(phase_id, dynamic_dimensions)

    parts = ["# 评审维度（共享 + 路由 + 动态）", ""]
    parts.append("## 通用质量维度（每条结论必须满足）")
    parts.append("")
    for d in dims:
        if d["id"] in {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}:
            parts.append(_render_dimension(d))
            parts.append("")

    parts.append("## Phase 专属维度（本 Phase 必须检查）")
    parts.append("")
    shared_ids = {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}
    dynamic_ids = {dd["id"] for dd in (dynamic_dimensions or [])}
    for d in dims:
        if d["id"] not in shared_ids and d["id"] not in dynamic_ids:
            parts.append(_render_dimension(d))
            parts.append("")

    if dynamic_dimensions:
        parts.append("## 动态维度（本项目特有，必须检查）")
        parts.append("")
        for d in dims:
            if d["id"] in dynamic_ids:
                parts.append(_render_dimension(d))
                parts.append("")

    # Append anti-rationalization table
    parts.extend(ANTI_RATIONALIZATION_SECTION)

    return "\n".join(parts)


# Compact anti-rationalization: distilled to core rules only
_ANTI_RATIONALIZATION_COMPACT: Final[list[str]] = [
    "",
    "## Anti-Rationalization（禁止放水）",
    "",
    "- 禁止整体评价，必须逐维度打分并列出具体扣分证据",
    '- 边界/并发/异常缺失即扣分，不接受"主流程覆盖了"的借口',
    "- 覆盖率≠断言质量，assertNotNull 不算有效覆盖",
    "- 每轮独立评审，不考虑历史改进",
    "- **核心原则**：宁可多报不可漏报（FN 比 FP 更严重）",
    "",
]


def compose_rubric_compact(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> str:
    """Compact rubric: 3-level scoring (5/3/1) + distilled anti-rationalization.

    Reduces rubric token footprint by ~40% while preserving scoring anchors.
    """
    dims = compose_rubric_structured(phase_id, dynamic_dimensions)

    parts = ["# 评审维度（共享 + 路由 + 动态）", ""]
    parts.append("## 通用质量维度（每条结论必须满足）")
    parts.append("")
    shared_ids = {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}
    for d in dims:
        if d["id"] in shared_ids:
            parts.append(_render_dimension(d, compact=True))
            parts.append("")

    parts.append("## Phase 专属维度（本 Phase 必须检查）")
    parts.append("")
    dynamic_ids = {dd["id"] for dd in (dynamic_dimensions or [])}
    for d in dims:
        if d["id"] not in shared_ids and d["id"] not in dynamic_ids:
            parts.append(_render_dimension(d, compact=True))
            parts.append("")

    if dynamic_dimensions:
        parts.append("## 动态维度（本项目特有，必须检查）")
        parts.append("")
        for d in dims:
            if d["id"] in dynamic_ids:
                parts.append(_render_dimension(d, compact=True))
                parts.append("")

    parts.extend(_ANTI_RATIONALIZATION_COMPACT)

    return "\n".join(parts)


def compose_rubric_layered(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> str:
    """Layered rubric: shared dims brief (name+description only), routed dims full 5-level.

    Shared dimensions are universal quality baselines (source citation, confidence,
    structural completeness, reasoning quality) — Judge understands these without
    detailed scoring anchors. Routed dimensions are Phase-specific and need full
    5-level rubric for accurate scoring.

    Reduces rubric tokens by ~20-30% with minimal scoring drift.
    """
    dims = compose_rubric_structured(phase_id, dynamic_dimensions)

    parts = ["# 评审维度（共享 + 路由 + 动态）", ""]
    parts.append("## 通用质量维度（每条结论必须满足）")
    parts.append("")
    shared_ids = {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}
    for d in dims:
        if d["id"] in shared_ids:
            parts.append(_render_dimension(d, brief=True))
            parts.append("")

    parts.append("## Phase 专属维度（本 Phase 必须检查）")
    parts.append("")
    dynamic_ids = {dd["id"] for dd in (dynamic_dimensions or [])}
    for d in dims:
        if d["id"] not in shared_ids and d["id"] not in dynamic_ids:
            parts.append(_render_dimension(d))
            parts.append("")

    if dynamic_dimensions:
        parts.append("## 动态维度（本项目特有，必须检查）")
        parts.append("")
        for d in dims:
            if d["id"] in dynamic_ids:
                parts.append(_render_dimension(d))
                parts.append("")

    parts.extend(ANTI_RATIONALIZATION_SECTION)

    return "\n".join(parts)
