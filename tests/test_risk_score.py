"""Test Impact Radius risk scoring."""

from __future__ import annotations


def test_risk_score_empty_change():
    """No changes → score 0, tier LOW."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {"changed_files": [], "changed_methods": [], "affected_callers": [], "affected_tests": []}
    result = compute_risk_score(radius)
    assert result["score"] == 0
    assert result["tier"] == "LOW"


def test_risk_score_small_change():
    """1 file, 1 method, 0 callers → LOW tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": ["Foo.java"],
        "changed_methods": ["Foo.bar"],
        "affected_callers": [],
        "affected_tests": ["FooTest.testBar"],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "LOW"
    assert 0 < result["score"] <= 25


def test_risk_score_medium_change():
    """3-5 files, several callers → MEDIUM tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(4)],
        "changed_methods": [f"Class{i}.method" for i in range(6)],
        "affected_callers": [f"Caller{i}.call" for i in range(5)],
        "affected_tests": [f"Test{i}.test" for i in range(3)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "MEDIUM"
    assert 25 < result["score"] <= 55


def test_risk_score_high_change():
    """10+ files, many callers → HIGH tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(12)],
        "changed_methods": [f"Class{i}.method" for i in range(20)],
        "affected_callers": [f"Caller{i}.call" for i in range(15)],
        "affected_tests": [f"Test{i}.test" for i in range(8)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] in ("HIGH", "CRITICAL")
    assert result["score"] > 55


def test_risk_score_critical_change():
    """30+ files, massive blast radius → CRITICAL."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(35)],
        "changed_methods": [f"Class{i}.method" for i in range(50)],
        "affected_callers": [f"Caller{i}.call" for i in range(30)],
        "affected_tests": [f"Test{i}.test" for i in range(20)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "CRITICAL"
    assert result["score"] > 75


def test_compute_blast_radius_includes_risk():
    """compute_risk_score integration: verify shape matches what write_blast_radius persists."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": ["A.java"],
        "changed_methods": ["A.foo"],
        "affected_callers": [],
        "affected_tests": [],
        "risk_summary": "1 files, 1 methods changed; 0 callers, 0 tests potentially affected",
    }
    risk = compute_risk_score(radius)
    assert "score" in risk
    assert "tier" in risk
    assert risk["tier"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_risk_score_factors_breakdown():
    """Result should include per-factor breakdown."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": ["A.java", "B.java"],
        "changed_methods": ["A.foo", "B.bar"],
        "affected_callers": ["C.baz"],
        "affected_tests": [],
    }
    result = compute_risk_score(radius)
    assert "factors" in result
    factors = result["factors"]
    assert "file_count" in factors
    assert "method_count" in factors
    assert "caller_count" in factors
    assert "test_count" in factors
    assert "blast_ratio" in factors


def test_constraints_relaxed_for_low_risk():
    """LOW risk tier should relax coverage thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", "LOW")
    # Q04 default: req_coverage_rate >= 0.8, se_coverage_rate >= 0.8
    # LOW risk: relax to 0.6
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] == 0.6


def test_constraints_unchanged_for_critical_risk():
    """CRITICAL risk tier should keep or tighten thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", "CRITICAL")
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] >= 0.8


def test_constraints_default_without_risk_tier():
    """No risk tier → use default thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", None)
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] == 0.8
