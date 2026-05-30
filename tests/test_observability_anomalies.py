"""P3: observability metric anomalies."""

from __future__ import annotations

from qualix.reporting.observability_anomalies import (
    anomalies_to_alert_dicts,
    detect_metric_anomalies,
)


def test_detect_zscore_drop_in_approval_rate() -> None:
    history = []
    for d in range(1, 12):
        history.append(
            {
                "date": f"2026-04-{d:02d}",
                "project_id": "PX",
                "phase": "Q01",
                "approval_rate": 0.9,
                "failure_rate": 0.05,
                "finalized": 3,
            }
        )
    history.append(
        {
            "date": "2026-04-12",
            "project_id": "PX",
            "phase": "Q01",
            "approval_rate": 0.2,
            "failure_rate": 0.05,
            "finalized": 3,
        }
    )
    found = detect_metric_anomalies(history, "2026-04-12", min_points=5, z_threshold=2.0, iqr_k=1.5)
    assert any(x["metric"] == "approval_rate" for x in found)
    alerts = anomalies_to_alert_dicts(found)
    assert any(a["rule"] == "METRIC_ANOMALY" for a in alerts)


def test_insufficient_history_returns_empty() -> None:
    history = [
        {"date": "2026-05-01", "project_id": "PX", "phase": "Q01", "approval_rate": 0.5},
        {"date": "2026-05-02", "project_id": "PX", "phase": "Q01", "approval_rate": 0.1},
    ]
    assert detect_metric_anomalies(history, "2026-05-02", min_points=10) == []
