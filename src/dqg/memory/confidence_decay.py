"""记忆置信度时间衰减（参考 jcode：按类型差异化半衰期 + 访问频次 + trust_weight）."""

from __future__ import annotations

import math
from enum import Enum
from pathlib import Path
from typing import Any

from dqg.memory.trust_level import TrustLevel
from dqg.memory.trust_level import trust_weight as _trust_weight_scalar
from dqg.store import get_connection

# 与 jcode 对齐：Correction / Preference / Fact 三种记忆半衰期（天）
HALF_LIFE_DAYS_CORRECTION = 365.0
HALF_LIFE_DAYS_PREFERENCE = 90.0
HALF_LIFE_DAYS_FACT = 30.0


class MemoryDecayCategory(str, Enum):
    """用于衰减策略的记忆大类（与 structured_facts 的 fact_type 不同层）."""

    CORRECTION = "correction"
    PREFERENCE = "preference"
    FACT = "fact"


def half_life_days(category: MemoryDecayCategory | str) -> float:
    """返回半衰期（天）。未知类别按 Fact 处理。"""
    if isinstance(category, MemoryDecayCategory):
        c = category
    else:
        try:
            c = MemoryDecayCategory(str(category).lower())
        except ValueError:
            c = MemoryDecayCategory.FACT
    return {
        MemoryDecayCategory.CORRECTION: HALF_LIFE_DAYS_CORRECTION,
        MemoryDecayCategory.PREFERENCE: HALF_LIFE_DAYS_PREFERENCE,
        MemoryDecayCategory.FACT: HALF_LIFE_DAYS_FACT,
    }[c]


def compute_decayed_confidence(
    *,
    initial: float,
    age_days: float,
    memory_category: MemoryDecayCategory | str,
    access_count: int = 0,
    trust_weight: float | None = None,
) -> float:
    """计算衰减后的置信度。

    confidence = initial × e^(-age/half_life) × (1 + 0.1 × log(access_count + 1)) × trust_weight

    其中 ``log`` 为自然对数 ``ln``（与常见指数衰减文献一致）；``trust_weight`` 为 [0,1] 标量，
    缺省时为中等信任 0.65（与 ``TrustLevel.MEDIUM`` 一致）。
    """
    tw = float(trust_weight) if trust_weight is not None else float(_trust_weight_scalar(TrustLevel.MEDIUM))
    tw = max(0.0, min(1.0, tw))
    age = max(0.0, float(age_days))
    ac = max(0, int(access_count))
    half = max(half_life_days(memory_category), 1e-9)
    ini = max(0.0, float(initial))

    decay = math.exp(-age / half)
    usage = 1.0 + 0.1 * math.log(ac + 1)
    return ini * decay * usage * tw


def recent_mean_trust_weight(output_dir: Path, project_id: str, *, limit: int = 10) -> float:
    """取该项目最近若干条 feedback_trust 的信任权重均值；无记录时返回 MEDIUM。"""
    lim = max(1, min(50, int(limit)))
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT trust_level FROM feedback_trust WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (project_id, lim),
        ).fetchall()
    if not rows:
        return float(_trust_weight_scalar(TrustLevel.MEDIUM))
    vals = [float(_trust_weight_scalar(str(r[0]))) for r in rows]
    return sum(vals) / len(vals)


def compute_decayed_confidence_for_project(
    output_dir: Path,
    *,
    project_id: str,
    initial: float,
    age_days: float,
    memory_category: MemoryDecayCategory | str,
    access_count: int = 0,
    trust_weight: float | None = None,
) -> dict[str, Any]:
    """在可选 DB 信任序列上计算置信度，并返回调试字段。"""
    tw = trust_weight if trust_weight is not None else recent_mean_trust_weight(output_dir, project_id)
    conf = compute_decayed_confidence(
        initial=initial,
        age_days=age_days,
        memory_category=memory_category,
        access_count=access_count,
        trust_weight=tw,
    )
    return {
        "confidence": conf,
        "trust_weight": tw,
        "half_life_days": half_life_days(memory_category),
        "age_days": max(0.0, float(age_days)),
        "access_count": max(0, int(access_count)),
    }
