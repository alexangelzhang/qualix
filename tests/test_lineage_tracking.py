"""Tests for SourceLocation model."""

import pytest
from pydantic import ValidationError

from dqg.schemas.location import SourceLocation


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
            file="com/xiaomi/service/OrderServiceTest.java",
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
        from dqg.schemas.phase_q05 import TCItem

        item = TCItem(id="TC-001", repo="car-mrs")
        assert item.test_location is None
        assert item.production_location is None

    def test_tc_item_with_test_location(self):
        from dqg.schemas.phase_q05 import TCItem

        loc = SourceLocation(file="OrderServiceTest.java", line_start=45)
        item = TCItem(id="TC-001", repo="car-mrs", test_location=loc)
        assert item.test_location.line_start == 45

    def test_tc_item_with_both_locations(self):
        from dqg.schemas.phase_q05 import TCItem

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
