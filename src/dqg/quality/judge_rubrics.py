"""Judge rubric logic: compose shared + routed + dynamic rubric for Judge consumption."""

from __future__ import annotations

from typing import Any, Final

from dqg.constants import SHARED_RUBRIC_DIMENSIONS
from dqg.quality._rubric_data import ANTI_RATIONALIZATION_SECTION, JUDGE_RUBRICS

# Re-export for backward compatibility
__all__ = ["ANTI_RATIONALIZATION_SECTION", "JUDGE_RUBRICS", "compose_rubric", "compose_rubric_structured"]

# Phase → routed rubric dimensions (60% base weight).
PHASE_ROUTED_RUBRICS: Final[dict[str, list[dict[str, Any]]]] = {
    phase_id: rubric["dimensions"] for phase_id, rubric in JUDGE_RUBRICS.items()
}


def _normalize_weights(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize dimension weights to sum to 1.0."""
    total = sum(d["weight"] for d in dimensions)
    if total <= 0:
        return dimensions
    return [{**d, "weight": round(d["weight"] / total, 4)} for d in dimensions]


def compose_rubric_structured(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Compose shared + routed + dynamic dimensions as structured list.

    Weight normalization: shared(40%) + routed(60%) as base ratio,
    dynamic appended then all weights re-normalized to sum to 1.0.
    """
    shared = [dict(d) for d in SHARED_RUBRIC_DIMENSIONS]
    routed = [dict(d) for d in PHASE_ROUTED_RUBRICS.get(phase_id, [])]

    # Scale routed weights so shared:routed = 40:60
    if routed:
        routed_total = sum(d["weight"] for d in routed)
        if routed_total > 0:
            for d in routed:
                d["weight"] = d["weight"] / routed_total * 0.60

    all_dims = shared + routed
    if dynamic_dimensions:
        all_dims.extend(dict(d) for d in dynamic_dimensions)

    return _normalize_weights(all_dims)


def _render_dimension(dim: dict[str, Any], weight_pct: float) -> str:
    """Render a single dimension as rubric text."""
    lines = [
        f"### {dim['id']}: {dim.get('name', '')} (权重 {weight_pct:.0f}%)",
        f"{dim.get('description', '')}",
    ]
    rubric = dim.get("rubric", {})
    for score in sorted(rubric.keys(), reverse=True):
        lines.append(f"  - {score}分: {rubric[score]}")
    return "\n".join(lines)


def compose_rubric(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> str:
    """Compose shared + routed + dynamic rubric as rendered text for Judge consumption."""
    dims = compose_rubric_structured(phase_id, dynamic_dimensions)

    parts = ["# 评审维度（共享 + 路由 + 动态）", ""]
    parts.append("## 通用质量维度（Shared）")
    parts.append("")
    for d in dims:
        if d["id"] in {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}:
            parts.append(_render_dimension(d, d["weight"] * 100))
            parts.append("")

    parts.append("## Phase 专属维度（Routed）")
    parts.append("")
    shared_ids = {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}
    dynamic_ids = {dd["id"] for dd in (dynamic_dimensions or [])}
    for d in dims:
        if d["id"] not in shared_ids and d["id"] not in dynamic_ids:
            parts.append(_render_dimension(d, d["weight"] * 100))
            parts.append("")

    if dynamic_dimensions:
        parts.append("## 动态维度（Dynamic）")
        parts.append("")
        for d in dims:
            if d["id"] in dynamic_ids:
                parts.append(_render_dimension(d, d["weight"] * 100))
                parts.append("")

    # Append anti-rationalization table
    parts.extend(ANTI_RATIONALIZATION_SECTION)

    return "\n".join(parts)
