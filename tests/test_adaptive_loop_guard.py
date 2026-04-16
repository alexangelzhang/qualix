"""Tests for adaptive loop guard + JudgeRunner integration."""
import pytest
from dqg.agents.adaptive_loop import JudgeVote, VoteResult, judge_health_check


def test_judge_vote_has_raw_output_and_health():
    vote = JudgeVote(
        model="test", scores={}, overall=3.5, verdict="PASS",
        issues=[], duration=1.0, raw_output="raw text", health="HEALTHY",
    )
    assert vote.raw_output == "raw text"
    assert vote.health == "HEALTHY"


def test_judge_vote_health_defaults_to_healthy():
    vote = JudgeVote(
        model="test", scores={}, overall=3.5, verdict="PASS",
        issues=[], duration=1.0,
    )
    assert vote.health == "HEALTHY"
    assert vote.raw_output == ""


def test_judge_health_check_healthy():
    votes = [JudgeVote(model="m", scores={}, overall=4.0, verdict="PASS", issues=[], health="HEALTHY")]
    vr1 = VoteResult(votes=votes, consensus="PASS", avg_score=4.0, disagreements=[])
    vr2 = VoteResult(votes=votes, consensus="PASS", avg_score=4.0, disagreements=[])
    assert judge_health_check([vr1, vr2]) == "HEALTHY"


def test_judge_health_check_semantic_fail():
    votes = [JudgeVote(model="m", scores={}, overall=2.0, verdict="FAIL", issues=[], health="HEALTHY")]
    vr1 = VoteResult(votes=votes, consensus="FAIL", avg_score=2.0, disagreements=[])
    vr2 = VoteResult(votes=votes, consensus="FAIL", avg_score=2.0, disagreements=[])
    assert judge_health_check([vr1, vr2]) == "SEMANTIC_FAIL"


def test_judge_health_check_infra_failure():
    votes = [JudgeVote(model="m", scores={}, overall=0, verdict="FAIL", issues=[], health="INFRA_FAILURE")]
    vr1 = VoteResult(votes=votes, consensus="FAIL", avg_score=0, disagreements=[])
    assert judge_health_check([vr1]) == "INFRA_FAILURE"
