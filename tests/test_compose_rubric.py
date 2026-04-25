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


def test_compose_rubric_includes_shared_and_routed():
    """compose_rubric output contains both shared and routed dimension IDs."""
    from dqg.quality.judge_rubrics import compose_rubric

    result = compose_rubric("Q07")
    assert "source_citation" in result  # shared
    assert "finding_validity" in result  # routed (Q07-specific)


def test_compose_rubric_unknown_phase_only_shared():
    """Unknown phase ID returns only shared dimensions."""
    from dqg.quality.judge_rubrics import compose_rubric

    result = compose_rubric("Q99")
    assert "source_citation" in result
    assert "finding_validity" not in result


def test_compose_rubric_all_phases_have_routed():
    """Every known Phase (Q01-Q07) has routed rubric dimensions."""
    from dqg.quality.judge_rubrics import PHASE_ROUTED_RUBRICS, compose_rubric

    for phase_id in ("Q01", "Q03", "Q04", "Q05", "Q06", "Q07"):
        assert phase_id in PHASE_ROUTED_RUBRICS, f"{phase_id} missing from PHASE_ROUTED_RUBRICS"
        result = compose_rubric(phase_id)
        assert "source_citation" in result  # shared always present


def test_compose_rubric_with_dynamic_dimensions():
    """Dynamic dimensions are appended and weights are normalized."""
    from dqg.quality.judge_rubrics import compose_rubric

    dynamic = [
        {
            "id": "dyn_concurrency",
            "name": "并发安全",
            "weight": 0.15,
            "rubric": {5: "好", 4: "较好", 3: "一般", 2: "差", 1: "很差"},
        }
    ]
    result = compose_rubric("Q07", dynamic_dimensions=dynamic)
    assert "dyn_concurrency" in result
    assert "source_citation" in result
    assert "finding_validity" in result


def test_compose_rubric_weights_normalized():
    """Weights in rendered rubric are normalized to sum to 100%."""
    from dqg.quality.judge_rubrics import compose_rubric_structured

    dims = compose_rubric_structured("Q07")
    total = sum(d["weight"] for d in dims)
    assert abs(total - 1.0) < 0.01

    # With dynamic
    dynamic = [
        {
            "id": "dyn_test",
            "name": "Test",
            "weight": 0.15,
            "rubric": {5: "好", 4: "较好", 3: "一般", 2: "差", 1: "很差"},
        }
    ]
    dims2 = compose_rubric_structured("Q07", dynamic_dimensions=dynamic)
    total2 = sum(d["weight"] for d in dims2)
    assert abs(total2 - 1.0) < 0.01
    assert len(dims2) == len(dims) + 1
