"""Tests for qualix.telemetry."""

from pathlib import Path

from qualix.reporting.telemetry import PhaseRunRecord, append_record, load_records


class TestTelemetry:
    def test_append_and_load(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        record = PhaseRunRecord(
            project_id="TEST",
            phase_id="Q01",
            phase_name="需求结构化",
            action="execute",
            status="in_progress",
        )
        append_record(output_dir, record)

        record2 = PhaseRunRecord(
            project_id="TEST",
            phase_id="Q01",
            phase_name="需求结构化",
            action="finalize",
            status="pending_review",
            duration_seconds=120.5,
        )
        append_record(output_dir, record2)

        records = load_records(output_dir, "TEST")
        assert len(records) == 2
        assert records[0].action == "execute"
        assert records[1].action == "finalize"
        assert records[1].duration_seconds == 120.5

    def test_load_empty(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        records = load_records(output_dir, "NOPROJECT")
        assert records == []

    def test_record_has_metadata(self):
        record = PhaseRunRecord(
            project_id="TEST",
            phase_id="Q01",
            action="execute",
            status="in_progress",
        )
        assert record.os_type != ""
        assert record.python_version != ""
        assert record.timestamp != ""
