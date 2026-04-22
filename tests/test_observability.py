"""Tests for dqg.observability."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from dqg.reporting.observability import _build_alerts, _parse_date, _write_prometheus_snapshot, generate_report
from dqg.tracking.regression import append_failure_history
from dqg.reporting.telemetry import PhaseRunRecord, append_record

if TYPE_CHECKING:
    from pathlib import Path


def _append_sample_records(output_dir: Path, project_id: str) -> None:
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=project_id,
            phase_id="Q01",
            phase_name="需求结构化",
            action="finalize",
            status="pending_review",
            duration_seconds=12.0,
            timestamp=datetime.now().isoformat(),
        ),
    )
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=project_id,
            phase_id="Q01",
            phase_name="需求结构化",
            action="approve",
            status="approved",
            timestamp=datetime.now().isoformat(),
        ),
    )
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=project_id,
            phase_id="Q03",
            phase_name="技术方案质量评审",
            action="finalize",
            status="pending_review",
            duration_seconds=20.0,
            validation_errors=["x"],
            timestamp=datetime.now().isoformat(),
        ),
    )


def _write_metrics_reports(output_dir: Path, project_id: str) -> None:
    phase_a = output_dir / project_id / "Q01"
    phase_a.mkdir(parents=True, exist_ok=True)
    (phase_a / "phase_a_report.md").write_text(
        "| REQ-001 | desc |\n| BR-001 | desc |\n| SE-001 | desc |\n| GAP-001 | desc |\n评审结论：**有条件通过**\n",
        encoding="utf-8",
    )
    phase_a5 = output_dir / project_id / "Q04"
    phase_a5.mkdir(parents=True, exist_ok=True)
    (phase_a5 / "tech_design_coverage_review.md").write_text(
        "| GAP-001 | 未闭环 |\n| GAP-002 | 已闭环 |\n",
        encoding="utf-8",
    )
    phase_a6 = output_dir / project_id / "Q03"
    phase_a6.mkdir(parents=True, exist_ok=True)
    (phase_a6 / "tech_design_quality_review.md").write_text(
        "| ARCH-001 | x |\n| CRITICAL_GAP | y |\n| SAFE | z |\n",
        encoding="utf-8",
    )
    phase_d = output_dir / project_id / "Q07"
    phase_d.mkdir(parents=True, exist_ok=True)
    (phase_d / "review_report.md").write_text("存在 BLOCKER 问题\n", encoding="utf-8")


def test_generate_daily_report_with_filters(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _append_sample_records(output_dir, "P1")
    _append_sample_records(output_dir, "P2")
    _write_metrics_reports(output_dir, "P1")
    _write_metrics_reports(output_dir, "P2")

    payload, json_path, md_path = generate_report(
        output_dir,
        period_name="daily",
        anchor=_parse_date(None),
        project_filter="P1",
        phase_filter=None,
    )

    assert len(payload["projects"]) == 1
    assert payload["projects"][0]["project_id"] == "P1"
    assert payload["projects"][0]["phase_approval_rate"] == 0.5
    assert payload["projects"][0]["block_count"] >= 1
    assert json_path.exists()
    assert md_path.exists()


def test_build_alerts_for_block_spike_and_failure_rate() -> None:
    history = [
        {"date": "2026-03-30", "project_id": "P1", "phase": "ALL", "block_count": 1},
        {"date": "2026-03-31", "project_id": "P1", "phase": "ALL", "block_count": 3},
        {"date": "2026-03-31", "project_id": "P1", "phase": "Q03", "failure_rate": 0.8, "finalized": 2},
    ]
    alerts = _build_alerts(
        history,
        current_label="2026-03-31",
        block_spike_ratio=2.0,
        phase_failure_threshold=0.5,
    )
    rules = {item["rule"] for item in alerts}
    assert "BLOCK_SPIKE" in rules
    assert "PHASE_FAILURE_RATE" in rules


def test_report_json_is_valid(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _append_sample_records(output_dir, "P1")
    _write_metrics_reports(output_dir, "P1")
    payload, json_path, _ = generate_report(
        output_dir,
        period_name="daily",
        anchor=_parse_date(None),
        project_filter=None,
        phase_filter=None,
    )
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["label"] == payload["label"]
    assert parsed["projects"][0]["project_id"] == "P1"


def test_write_prometheus_snapshot(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    payload = {
        "label": "2026-03-31",
        "projects": [
            {
                "project_id": "P1",
                "phase_approval_rate": 0.5,
                "avg_duration_seconds": 15.0,
                "gap_closure_rate": 0.4,
                "block_count": 2,
                "phase_stats": {
                    "Q01": {"failure_rate": 0.0},
                    "Q03": {"failure_rate": 0.5},
                },
            }
        ],
    }
    alerts = [{"rule": "PHASE_FAILURE_RATE"}]
    path = _write_prometheus_snapshot(output_dir, payload, alerts)
    text = path.read_text(encoding="utf-8")
    assert 'dqg_project_phase_approval_rate{project="P1"} 0.5' in text
    assert 'dqg_phase_failure_rate{project="P1",phase="Q03"} 0.5' in text
    assert "dqg_alert_count 1" in text


def test_weekly_report_includes_failure_library_trend(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _append_sample_records(output_dir, "P1")
    _write_metrics_reports(output_dir, "P1")

    history_path = tmp_path / "regression" / "failure-library" / "history.jsonl"
    append_failure_history(
        [
            {"library": "failure-library", "case_id": "fp-001", "error_type": "误报", "passed": False},
            {"library": "failure-library", "case_id": "fn-001", "error_type": "漏报", "passed": True},
        ],
        history_path,
        "2026-03-31",
    )

    payload, _, md_path = generate_report(
        output_dir,
        period_name="weekly",
        anchor=_parse_date("2026-03-31"),
        project_filter=None,
        phase_filter=None,
    )

    assert payload["failure_library"]["weeks"][0]["by_error_type"]["误报"]["failed"] == 1
    text = md_path.read_text(encoding="utf-8")
    assert "## Failure Library" in text
    assert "| 误报 | 1 | 1 | 0.00% |" in text


def test_daily_alerts_include_failure_library_regression(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _append_sample_records(output_dir, "P1")
    _write_metrics_reports(output_dir, "P1")

    history_path = tmp_path / "regression" / "failure-library" / "history.jsonl"
    append_failure_history(
        [
            {"library": "failure-library", "case_id": "fp-001", "error_type": "误报", "passed": False},
            {"library": "failure-library", "case_id": "fn-001", "error_type": "漏报", "passed": True},
        ],
        history_path,
        "2026-03-31",
    )

    payload, _, _ = generate_report(
        output_dir,
        period_name="daily",
        anchor=_parse_date("2026-03-31"),
        project_filter=None,
        phase_filter=None,
    )
    history = [
        {"date": "2026-03-31", "project_id": "P1", "phase": "ALL", "block_count": 1},
    ]
    alerts = _build_alerts(
        history,
        current_label="2026-03-31",
        block_spike_ratio=2.0,
        phase_failure_threshold=0.5,
        failure_library=payload.get("failure_library"),
    )
    rules = {item["rule"] for item in alerts}
    assert "FAILURE_LIBRARY_REGRESSION" in rules
