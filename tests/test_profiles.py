"""Tests for qualix.profiles."""

from __future__ import annotations

from pathlib import Path

from qualix.core.profiles import (
    QualixProfile,
    _load_profile_context_cached,
    get_profile,
    list_profiles,
    load_profile_context,
    profile_to_payload,
    render_profile_context_markdown,
    validate_all_profiles,
    validate_profile_file,
)


def test_list_profiles_contains_two_baselines() -> None:
    profile_ids = {item.profile_id for item in list_profiles()}
    assert "java-ddd-tmf" in profile_ids
    assert "go-service" in profile_ids


def test_get_profile_returns_expected_baseline() -> None:
    profile = get_profile("java-ddd-tmf")
    assert profile.profile_id == "java-ddd-tmf"
    assert profile.baseline_path.name == "baseline.md"
    assert profile.version == "1.0.0"


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
    assert "Language: `go`" in rendered
    assert "Version: `1.0.0`" in rendered
    assert "profiles/go-service/baseline.md" in rendered
    assert "Quality Thresholds" in rendered


def test_profile_payload_includes_governance_fields() -> None:
    payload = profile_to_payload(get_profile("typescript-service"))
    assert payload["version"] == "1.0.0"
    assert payload["language"] == "typescript"


def test_bundled_profiles_pass_schema_validation() -> None:
    issues = validate_all_profiles()
    assert issues == {}


def test_validate_profile_file_reports_missing_required_field(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles" / "bad-service"
    profile_dir.mkdir(parents=True)
    (profile_dir / "baseline.md").write_text("baseline", encoding="utf-8")
    risk_catalog = tmp_path / "references" / "risk-catalog-risks.md"
    risk_catalog.parent.mkdir()
    risk_catalog.write_text("risks", encoding="utf-8")
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        """
{
  "profile_id": "bad-service",
  "name": "Bad Service",
  "baseline_path": "profiles/bad-service/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "quality_thresholds": {"line_coverage": 0.8}
}
""",
        encoding="utf-8",
    )

    issues = validate_profile_file(profile_path, repo_root=tmp_path)

    assert any("missing required field: description" in issue for issue in issues)


def test_validate_profile_file_reports_invalid_version(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles" / "bad-version"
    profile_dir.mkdir(parents=True)
    (profile_dir / "baseline.md").write_text("baseline", encoding="utf-8")
    risk_catalog = tmp_path / "references" / "risk-catalog-risks.md"
    risk_catalog.parent.mkdir()
    risk_catalog.write_text("risks", encoding="utf-8")
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        """
{
  "profile_id": "bad-version",
  "name": "Bad Version",
  "description": "Invalid version profile.",
  "version": "v1",
  "language": "java",
  "baseline_path": "profiles/bad-version/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "quality_thresholds": {"line_coverage": 0.8}
}
""",
        encoding="utf-8",
    )

    issues = validate_profile_file(profile_path, repo_root=tmp_path)

    assert any("version must use semantic format" in issue for issue in issues)


def test_validate_profile_file_requires_version_and_language(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles" / "missing-governance"
    profile_dir.mkdir(parents=True)
    (profile_dir / "baseline.md").write_text("baseline", encoding="utf-8")
    risk_catalog = tmp_path / "references" / "risk-catalog-risks.md"
    risk_catalog.parent.mkdir()
    risk_catalog.write_text("risks", encoding="utf-8")
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        """
{
  "profile_id": "missing-governance",
  "name": "Missing Governance",
  "description": "Profile without explicit governance fields.",
  "baseline_path": "profiles/missing-governance/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "quality_thresholds": {"line_coverage": 0.8}
}
""",
        encoding="utf-8",
    )

    issues = validate_profile_file(profile_path, repo_root=tmp_path)

    assert any("missing required field: version" in issue for issue in issues)
    assert any("missing required field: language" in issue for issue in issues)


def test_validate_profile_file_allows_future_language_ids(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles" / "kotlin-service"
    profile_dir.mkdir(parents=True)
    (profile_dir / "baseline.md").write_text("baseline", encoding="utf-8")
    risk_catalog = tmp_path / "references" / "risk-catalog-risks.md"
    risk_catalog.parent.mkdir()
    risk_catalog.write_text("risks", encoding="utf-8")
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        """
{
  "profile_id": "kotlin-service",
  "version": "1.0.0",
  "name": "Kotlin Service",
  "description": "Future language profile.",
  "language": "kotlin",
  "baseline_path": "profiles/kotlin-service/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "quality_thresholds": {"line_coverage": 0.8}
}
""",
        encoding="utf-8",
    )

    issues = validate_profile_file(profile_path, repo_root=tmp_path)

    assert issues == []


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

    profile = QualixProfile(
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
