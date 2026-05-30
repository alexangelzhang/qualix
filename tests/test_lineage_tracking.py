"""Tests for SourceLocation model."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from qualix.quality.auto_checks import auto_derive_checks
from qualix.schemas.location import SourceLocation


class TestSourceLocation:
    def test_minimal_valid(self):
        loc = SourceLocation(file="OrderServiceTest.java", line_start=45)
        assert loc.file == "OrderServiceTest.java"
        assert loc.line_start == 45
        assert loc.line_end is None
        assert loc.class_name == ""
        assert loc.method_name == ""
        assert loc.repo == ""

    def test_full_fields(self):
        loc = SourceLocation(
            file="com/example/service/OrderServiceTest.java",
            line_start=45,
            line_end=72,
            class_name="OrderServiceTest",
            method_name="testApprove_success",
            repo="car-mrs",
        )
        assert loc.line_end == 72
        assert loc.repo == "car-mrs"

    def test_line_start_must_be_positive(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="Foo.java", line_start=0)

    def test_line_end_must_be_gte_line_start(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="Foo.java", line_start=10, line_end=5)

    def test_file_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="", line_start=1)


class TestTCItemWithLocation:
    def test_tc_item_without_location_is_valid(self):
        from qualix.schemas.phase_q05 import TCItem

        item = TCItem(id="TC-001", repo="car-mrs")
        assert item.test_location is None
        assert item.production_location is None

    def test_tc_item_with_test_location(self):
        from qualix.schemas.phase_q05 import TCItem

        loc = SourceLocation(file="OrderServiceTest.java", line_start=45)
        item = TCItem(id="TC-001", repo="car-mrs", test_location=loc)
        assert item.test_location.line_start == 45

    def test_tc_item_with_both_locations(self):
        from qualix.schemas.phase_q05 import TCItem

        item = TCItem(
            id="TC-001",
            repo="car-mrs",
            test_location=SourceLocation(
                file="OrderServiceTest.java",
                line_start=45,
                line_end=72,
                class_name="OrderServiceTest",
                method_name="testApprove",
                repo="car-mrs",
            ),
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                class_name="OrderService",
                method_name="approve",
                repo="car-mrs",
            ),
        )
        assert item.production_location.method_name == "approve"


class TestEutAuditItemWithLocation:
    def test_eut_audit_item_without_location_is_valid(self):
        from qualix.schemas.phase_q06 import EutAuditItem

        item = EutAuditItem(eut_id="EUT-001", status="COVERED")
        assert item.test_location is None
        assert item.production_location is None

    def test_eut_audit_item_with_locations(self):
        from qualix.schemas.phase_q06 import EutAuditItem

        item = EutAuditItem(
            eut_id="EUT-001",
            status="COVERED",
            test_location=SourceLocation(
                file="OrderServiceTest.java",
                line_start=52,
                class_name="OrderServiceTest",
                method_name="testApprove_success",
                repo="car-mrs",
            ),
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                class_name="OrderService",
                method_name="approve",
                repo="car-mrs",
            ),
        )
        assert item.test_location.line_start == 52
        assert item.production_location.class_name == "OrderService"


class TestFindingItemWithLocation:
    def test_finding_item_without_location_is_valid(self):
        from qualix.schemas.phase_q06 import FindingItem

        item = FindingItem(id="FIND-001", severity="HIGH")
        assert item.production_location is None

    def test_finding_item_with_production_location(self):
        from qualix.schemas.phase_q06 import FindingItem

        item = FindingItem(
            id="FIND-001",
            severity="HIGH",
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                repo="car-mrs",
            ),
        )
        assert item.production_location.file == "OrderService.java"


def _write_q06_json(tmpdir: Path, data: dict) -> Path:
    phase_dir = tmpdir / "test-proj" / "Q06"
    phase_dir.mkdir(parents=True)
    json_path = phase_dir / "phase_c_structured.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmpdir


class TestLocationGate:
    def test_covered_without_test_location_is_downgraded(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "COVERED",
                    "evidence": "assertEquals(...) [Foo.java:10]",
                    "test_location": None,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        assert any("test_location" in e and "PARTIAL" in e for e in errors)

    def test_covered_with_test_location_passes(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "COVERED",
                    "evidence": "assertEquals(...) [Foo.java:10]",
                    "test_location": {
                        "file": "FooTest.java",
                        "line_start": 10,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        location_errors = [e for e in errors if "test_location" in e and "PARTIAL" in e]
        assert len(location_errors) == 0

    def test_missing_status_skips_location_check(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "MISSING",
                    "test_location": None,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        location_errors = [e for e in errors if "test_location" in e and "PARTIAL" in e]
        assert len(location_errors) == 0
