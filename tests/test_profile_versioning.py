"""Tests for profile versioning with @version syntax."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from qualix.core.profiles import QualixProfile, get_profile


def _make_profile(profile_id: str, version: str = "1.0.0") -> QualixProfile:
    return QualixProfile(
        profile_id=profile_id,
        version=version,
        name=f"Test {profile_id}",
        description="Test profile",
        baseline_path=f"profiles/{profile_id}/baseline.md",
        risk_catalog_path="references/risk-catalog-risks.md",
        quality_thresholds={},
    )


_PROFILES = [
    _make_profile("java-ddd-tmf", "2.0.0"),
    _make_profile("java-ddd-tmf@v1", "1.0.0"),
    _make_profile("typescript-service", "1.0.0"),
]


@patch("qualix.core.profiles.list_profiles", return_value=_PROFILES)
def test_get_profile_exact_match(mock_list):
    p = get_profile("java-ddd-tmf")
    assert p.profile_id == "java-ddd-tmf"
    assert p.version == "2.0.0"


@patch("qualix.core.profiles.list_profiles", return_value=_PROFILES)
def test_get_profile_at_version_syntax(mock_list):
    p = get_profile("java-ddd-tmf@v1")
    assert p.profile_id == "java-ddd-tmf@v1"
    assert p.version == "1.0.0"


@patch("qualix.core.profiles.list_profiles", return_value=_PROFILES)
def test_get_profile_unknown_raises(mock_list):
    with pytest.raises(ValueError, match="Unknown profile"):
        get_profile("nonexistent")


@patch("qualix.core.profiles.list_profiles", return_value=_PROFILES)
def test_get_profile_unknown_version_shows_candidates(mock_list):
    with pytest.raises(ValueError, match="java-ddd-tmf"):
        get_profile("java-ddd-tmf@v99")


@patch("qualix.core.profiles.list_profiles", return_value=_PROFILES)
def test_get_profile_default_is_java_ddd_tmf(mock_list):
    p = get_profile(None)
    assert p.profile_id == "java-ddd-tmf"
