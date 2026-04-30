"""Skill Crystal: Worker 经验结晶 — 把成功的 Phase 执行模式结晶为可复用模板.

借鉴 GenericAgent 的 skill crystallization 思路：
- 从成功执行（judge_passed + score >= 4.0）中提取执行模式
- 结晶为结构化模板，下次同 Phase 执行时直接注入
- 减少 LLM 从头推理的 token 消耗，提升一致性
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

CRYSTAL_DIR = "regression/crystals"
CRYSTAL_MIN_SCORE = 4.0  # 只结晶高分执行


def extract_crystal(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    judge_result: dict[str, Any],
) -> dict[str, Any] | None:
    """从高分 Phase 执行中提取经验结晶.

    只在 judge_passed=True 且 overall_score >= 4.0 时触发。
    """
    score = judge_result.get("overall_score", 0)
    if score < CRYSTAL_MIN_SCORE:
        return None

    # 提取高分维度的模式
    dimensions = judge_result.get("dimensions", [])
    strong_dims = [d for d in dimensions if d.get("score", 0) >= 4 and not d.get("issues")]

    if not strong_dims:
        return None

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    crystal = {
        "crystal_id": f"CRYS-{phase_id}-{ts}",
        "phase_id": phase_id,
        "project_id": project_id,
        "created_at": datetime.now().isoformat(),
        "overall_score": score,
        "strong_dimensions": [{"id": d.get("id", ""), "score": d.get("score", 0)} for d in strong_dims],
        "summary": judge_result.get("summary", ""),
        "top_patterns": _extract_patterns(judge_result),
        "use_count": 0,
    }
    return crystal


def _extract_patterns(judge_result: dict[str, Any]) -> list[str]:
    """从 judge 结果中提取成功模式描述."""
    patterns: list[str] = []

    # 从 gate_checklist 中提取全部通过的项
    checklist = judge_result.get("gate_checklist", [])
    passed_items = [item.get("item", "") for item in checklist if item.get("passed")]
    if passed_items:
        patterns.append(f"Gate checklist 全通过: {', '.join(passed_items[:5])}")

    summary = judge_result.get("summary", "")
    if summary:
        patterns.append(f"Judge 总结: {summary}")

    return patterns[:5]


def save_crystal(base_dir: Path, crystal: dict[str, Any]) -> str:
    """保存经验结晶."""
    phase_id = crystal["phase_id"]
    crystal_id = crystal["crystal_id"]
    crystal_dir = base_dir / CRYSTAL_DIR / phase_id
    crystal_dir.mkdir(parents=True, exist_ok=True)
    save_json(crystal_dir / f"{crystal_id}.json", crystal)
    log.info("Crystal saved: %s (score=%.1f)", crystal_id, crystal.get("overall_score", 0))
    return crystal_id


def load_crystals_for_phase(
    base_dir: Path,
    phase_id: str,
    max_crystals: int = 3,
) -> list[dict[str, Any]]:
    """加载指定 Phase 的经验结晶，按 score 降序取 top N."""
    crystal_dir = base_dir / CRYSTAL_DIR / phase_id
    if not crystal_dir.exists():
        return []

    crystals: list[dict[str, Any]] = []
    for p in sorted(crystal_dir.glob("CRYS-*.json")):
        c = load_json(p)
        if c:
            crystals.append(c)

    crystals.sort(key=lambda c: c.get("overall_score", 0), reverse=True)
    return crystals[:max_crystals]


def render_crystals_for_prompt(crystals: list[dict[str, Any]]) -> str:
    """将经验结晶渲染为可注入 prompt 的文本."""
    if not crystals:
        return ""

    lines = [
        "## 历史成功模式（经验结晶）",
        "",
        "以下是该 Phase 历史高分执行的成功模式，请参考：",
        "",
    ]
    for i, c in enumerate(crystals, 1):
        lines.append(f"### Crystal {i}: {c.get('crystal_id', '')} (score={c.get('overall_score', 0):.1f})")
        for dim in c.get("strong_dimensions", []):
            lines.append(f"- 高分维度: {dim.get('id', '')} = {dim.get('score', 0)}")
        for pattern in c.get("top_patterns", []):
            lines.append(f"- {pattern}")
        lines.append("")

    return "\n".join(lines)
