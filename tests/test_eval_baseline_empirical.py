"""P1: eval baseline 实证尾部回归门控."""

from __future__ import annotations

import json
from pathlib import Path

from qualix.quality.eval.eval_baseline import (
    REGRESSION_THRESHOLD,
    _empirical_regression_tail,
    compare_with_baseline,
)


def test_empirical_tail_volatile_history_blocks_weak_signal() -> None:
    hist_vals = [1.0, 0.5] * 7  # 14 points → 13 deltas, alternating ±0.5
    confirms, frac = _empirical_regression_tail(hist_vals, -0.06)
    assert confirms is False
    assert frac is not None and frac > REGRESSION_THRESHOLD


def test_empirical_tail_calm_history_allows_large_drop() -> None:
    hist_vals = [0.9 - i * 0.001 for i in range(15)]
    confirms, frac = _empirical_regression_tail(hist_vals, -0.08)
    assert confirms is True
    assert frac is not None


def test_compare_suppresses_regression_when_empirical_not_confirmed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "qualix.quality.eval.eval_baseline._load_metric_series",
        lambda *a, **k: [1.0, 0.5] * 7,
    )

    out_dir = tmp_path / "output"
    proj = "p1"
    baseline_file = out_dir / proj / "_eval_baseline.json"
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    baseline_file.write_text(
        json.dumps({"Q04": {"req_coverage_rate": 1.0}}, ensure_ascii=False),
        encoding="utf-8",
    )

    cmp = compare_with_baseline(
        out_dir,
        proj,
        "Q04",
        {"metrics": {"req_coverage_rate": 1.0 - REGRESSION_THRESHOLD - 0.01}},
    )
    row = next(r for r in cmp["comparisons"] if r["metric"] == "req_coverage_rate")
    assert row["status"] == "STABLE"
    assert cmp["has_regression"] is False
