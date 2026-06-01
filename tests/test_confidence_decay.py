"""confidence_decay：半衰期与公式."""

from __future__ import annotations

import math
from pathlib import Path

from qualix.memory.confidence_decay import (
    HALF_LIFE_DAYS_FACT,
    MemoryDecayCategory,
    compute_decayed_confidence,
    compute_decayed_confidence_for_project,
    half_life_days,
    recent_mean_trust_weight,
)
from qualix.memory.trust_level import TrustLevel, record_trust_event
from qualix.store import get_connection


def test_half_life_constants() -> None:
    assert half_life_days(MemoryDecayCategory.CORRECTION) == 365.0
    assert half_life_days(MemoryDecayCategory.PREFERENCE) == 90.0
    assert half_life_days(MemoryDecayCategory.FACT) == 30.0
    assert half_life_days("fact") == HALF_LIFE_DAYS_FACT
    assert half_life_days("unknown_xyz") == HALF_LIFE_DAYS_FACT


def test_formula_age_zero_access_zero() -> None:
    c = compute_decayed_confidence(
        initial=1.0,
        age_days=0.0,
        memory_category="fact",
        access_count=0,
        trust_weight=1.0,
    )
    assert abs(c - 1.0) < 1e-9


def test_formula_one_half_life() -> None:
    # age = half_life => exp(-1); access 0 => usage 1; trust 1
    c = compute_decayed_confidence(
        initial=1.0,
        age_days=30.0,
        memory_category="fact",
        access_count=0,
        trust_weight=1.0,
    )
    assert abs(c - math.exp(-1.0)) < 1e-9


def test_access_count_boost() -> None:
    base = compute_decayed_confidence(
        initial=1.0,
        age_days=0.0,
        memory_category="fact",
        access_count=0,
        trust_weight=1.0,
    )
    boosted = compute_decayed_confidence(
        initial=1.0,
        age_days=0.0,
        memory_category="fact",
        access_count=9,
        trust_weight=1.0,
    )
    assert boosted > base
    expect = 1.0 * 1.0 * (1.0 + 0.1 * math.log(10)) * 1.0
    assert abs(boosted - expect) < 1e-9


def test_recent_mean_trust_weight(tmp_path: Path) -> None:
    out = tmp_path / "o"
    out.mkdir()
    with get_connection(out):
        pass
    record_trust_event(
        out,
        project_id="p",
        phase_id="Q01",
        event_type="t",
        trust_level=TrustLevel.HIGH,
    )
    record_trust_event(
        out,
        project_id="p",
        phase_id="Q01",
        event_type="t2",
        trust_level=TrustLevel.LOW,
    )
    m = recent_mean_trust_weight(out, "p", limit=10)
    assert abs(m - (1.0 + 0.35) / 2) < 1e-9


def test_compute_for_project_uses_db_trust(tmp_path: Path) -> None:
    out = tmp_path / "o2"
    out.mkdir()
    with get_connection(out):
        pass
    record_trust_event(
        out,
        project_id="px",
        phase_id="Q05a",
        event_type="judge_auto_synthesized",
        trust_level=TrustLevel.MEDIUM,
    )
    r = compute_decayed_confidence_for_project(
        out,
        project_id="px",
        initial=1.0,
        age_days=0.0,
        memory_category="preference",
        access_count=0,
    )
    assert r["half_life_days"] == 90.0
    assert abs(r["trust_weight"] - 0.65) < 1e-9
    assert abs(r["confidence"] - 0.65) < 1e-9
