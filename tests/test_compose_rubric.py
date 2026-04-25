# tests/test_compose_rubric.py
"""Tests for P3: shared + routed Judge rubric composition."""

from __future__ import annotations


def test_shared_rubric_has_four_dimensions():
    """Shared rubric defines exactly 4 universal quality dimensions."""
    from dqg.constants import SHARED_RUBRIC_DIMENSIONS

    assert len(SHARED_RUBRIC_DIMENSIONS) == 4
    ids = {d["id"] for d in SHARED_RUBRIC_DIMENSIONS}
    assert ids == {"source_citation", "confidence_tagging", "structural_completeness", "reasoning_quality"}


def test_shared_rubric_weights_sum_to_040():
    """Shared rubric base weights sum to 0.40 (40%)."""
    from dqg.constants import SHARED_RUBRIC_DIMENSIONS

    total = sum(d["weight"] for d in SHARED_RUBRIC_DIMENSIONS)
    assert abs(total - 0.40) < 0.001


def test_shared_rubric_dimensions_have_rubric_scale():
    """Each shared dimension has a 1-5 rubric scale."""
    from dqg.constants import SHARED_RUBRIC_DIMENSIONS

    for dim in SHARED_RUBRIC_DIMENSIONS:
        assert "rubric" in dim
        assert set(dim["rubric"].keys()) == {1, 2, 3, 4, 5}
