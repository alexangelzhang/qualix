"""Tests for dqg.profiles."""

from __future__ import annotations

from pathlib import Path

from dqg.core.profiles import (
    _load_profile_context_cached,
    DqgProfile,
    get_profile,
    list_profiles,
    load_profile_context,
    render_profile_context_markdown,
)


def test_list_profiles_contains_two_baselines() -> None:
    profile_ids = {item.profile_id for item in list_profiles()}
    assert "java-ddd-tmf" in profile_ids
    assert "go-service" in profile_ids


def test_get_profile_returns_expected_baseline() -> None:
    profile = get_profile("java-ddd-tmf")
    assert profile.profile_id == "java-ddd-tmf"
    assert profile.baseline_path.name == "baseline.md"


def test_load_profile_context_includes_thresholds() -> None:
    profile = get_profile("go-service")
    context = load_profile_context(profile)
    assert "go-service" in context
    assert "coverage_thresholds" in context
    assert "risk_catalog_path" in context


def test_unknown_profile_raises() -> None:
    try:
        get_profile("unknown-profile")
    except ValueError as exc:
        assert "Unknown profile" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown profile")


def test_render_profile_context_markdown_contains_profile_fields() -> None:
    profile = get_profile("go-service")
    rendered = render_profile_context_markdown(profile)
    assert "## PROFILE_CONTEXT" in rendered
    assert "`go-service`" in rendered
    assert "profiles/go-service/baseline.md" in rendered
    assert "Quality Thresholds" in rendered


def test_load_profile_context_reuses_cached_file_reads(monkeypatch) -> None:
    _load_profile_context_cached.cache_clear()

    profile = get_profile("go-service")
    read_counts = {"baseline": 0, "risk": 0}
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args, **kwargs):
        if self == profile.baseline_path:
            read_counts["baseline"] += 1
        if self == profile.risk_catalog_path:
            read_counts["risk"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    first = load_profile_context(profile)
    second = load_profile_context(profile)

    assert first == second
    assert read_counts == {"baseline": 1, "risk": 1}


def test_load_profile_context_reloads_after_file_change(tmp_path: Path, monkeypatch) -> None:
    _load_profile_context_cached.cache_clear()

    baseline = tmp_path / "baseline.md"
    risk_catalog = tmp_path / "risk-catalog.md"
    baseline.write_text("baseline-v1", encoding="utf-8")
    risk_catalog.write_text("risk-v1", encoding="utf-8")

    profile = DqgProfile(
        profile_id="test-profile",
        name="Test Profile",
        description="for cache invalidation",
        baseline_path=baseline,
        risk_catalog_path=risk_catalog,
        quality_thresholds={"coverage": 0.9},
    )

    first = load_profile_context(profile)
    baseline.write_text("baseline-v2", encoding="utf-8")
    baseline.touch()
    second = load_profile_context(profile)

    assert "baseline-v1" in first
    assert "baseline-v2" in second
