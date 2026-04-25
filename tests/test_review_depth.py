# tests/test_review_depth.py
"""Tests for P1: ACT review depth configuration."""

from __future__ import annotations


def test_review_depth_config_has_all_tiers():
    """Every risk tier maps to a depth config."""
    from dqg.constants import REVIEW_DEPTH_CONFIG

    for tier in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        cfg = REVIEW_DEPTH_CONFIG[tier]
        assert "max_iterations" in cfg
        assert "force_secondary" in cfg
        assert "skip_critique" in cfg


def test_review_depth_low_is_lightest():
    """LOW tier: 1 iteration, no secondary, skip critique."""
    from dqg.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["LOW"]
    assert cfg["max_iterations"] == 1
    assert cfg["force_secondary"] is False
    assert cfg["skip_critique"] is True


def test_review_depth_high_forces_secondary():
    """HIGH tier: 3 iterations, force secondary."""
    from dqg.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["HIGH"]
    assert cfg["max_iterations"] == 3
    assert cfg["force_secondary"] is True
    assert cfg["skip_critique"] is False


def test_review_depth_default_is_medium():
    """Default fallback is MEDIUM."""
    from dqg.constants import REVIEW_DEPTH_DEFAULT

    assert REVIEW_DEPTH_DEFAULT == "MEDIUM"
