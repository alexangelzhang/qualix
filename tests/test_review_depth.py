# tests/test_review_depth.py
"""Tests for P1: ACT review depth configuration."""

from __future__ import annotations

from unittest.mock import patch


def test_review_depth_config_has_all_tiers():
    """Every risk tier maps to a depth config."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    for tier in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        cfg = REVIEW_DEPTH_CONFIG[tier]
        assert "max_iterations" in cfg
        assert "force_secondary" in cfg
        assert "skip_critique" in cfg


def test_review_depth_low_is_lightest():
    """LOW tier: 1 iteration, no secondary, skip critique."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["LOW"]
    assert cfg["max_iterations"] == 1
    assert cfg["force_secondary"] is False
    assert cfg["skip_critique"] is True


def test_review_depth_high_forces_secondary():
    """HIGH tier: 3 iterations, force secondary."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["HIGH"]
    assert cfg["max_iterations"] == 3
    assert cfg["force_secondary"] is True
    assert cfg["skip_critique"] is False


def test_review_depth_default_is_medium():
    """Default fallback is MEDIUM."""
    from qualix.constants import REVIEW_DEPTH_DEFAULT

    assert REVIEW_DEPTH_DEFAULT == "MEDIUM"


def test_force_secondary_skips_boundary_check():
    """force_secondary=True invokes secondary models regardless of primary score."""
    from qualix.agents.judge_vote import JudgeVote, multi_judge_vote

    fake_vote = JudgeVote(
        model="primary",
        scores={},
        overall=4.5,
        verdict="PASS",
        issues=[],
        duration=1.0,
        raw_output="clean output",
        health="HEALTHY",
    )

    with patch("qualix.agents.judge_vote._run_single_judge", return_value=fake_vote) as mock_judge:
        result = multi_judge_vote(
            output_dir="/tmp",
            report_path="/tmp/report.md",
            rubric="test rubric",
            models=["primary-model", "secondary-model"],
            fallback="fallback",
            force_secondary=True,
        )
        # Should call judge for both primary AND secondary (force_secondary bypasses boundary check)
        assert mock_judge.call_count >= 2
        assert len(result.votes) == 2


def test_no_force_secondary_skips_clear_pass():
    """Without force_secondary, clear PASS (4.5) skips secondary."""
    from qualix.agents.judge_vote import JudgeVote, multi_judge_vote

    fake_vote = JudgeVote(
        model="primary",
        scores={},
        overall=4.5,
        verdict="PASS",
        issues=[],
        duration=1.0,
        raw_output="clean output",
        health="HEALTHY",
    )

    with patch("qualix.agents.judge_vote._run_single_judge", return_value=fake_vote):
        result = multi_judge_vote(
            output_dir="/tmp",
            report_path="/tmp/report.md",
            rubric="test rubric",
            models=["primary-model", "secondary-model"],
            fallback="fallback",
            force_secondary=False,
        )
        # Clear PASS → only primary vote
        assert len(result.votes) == 1
