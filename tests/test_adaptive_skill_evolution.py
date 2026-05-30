"""Tests for adaptive loop → SkillReflector integration."""

from qualix.agents.judge_vote import JudgeVote, VoteResult, judge_health_check


def test_judge_health_check_triggers_semantic_fail():
    """When all votes are HEALTHY but all consensus FAIL → SEMANTIC_FAIL."""
    votes = [
        JudgeVote(
            model="m",
            scores={},
            overall=2.0,
            verdict="FAIL",
            issues=[{"severity": "high", "description": "missing boundary test"}],
            health="HEALTHY",
        )
    ]
    vr = VoteResult(votes=votes, consensus="FAIL", avg_score=2.0, disagreements=[])
    assert judge_health_check([vr, vr, vr]) == "SEMANTIC_FAIL"


def test_judge_health_check_mixed_health():
    """Mix of HEALTHY and INFRA_FAILURE votes."""
    healthy = JudgeVote(model="m1", scores={}, overall=2.0, verdict="FAIL", issues=[], health="HEALTHY")
    infra = JudgeVote(model="m2", scores={}, overall=0, verdict="FAIL", issues=[], health="INFRA_FAILURE")
    vr1 = VoteResult(votes=[healthy], consensus="FAIL", avg_score=2.0, disagreements=[])
    vr2 = VoteResult(votes=[infra], consensus="FAIL", avg_score=0, disagreements=[])
    vr3 = VoteResult(votes=[healthy], consensus="FAIL", avg_score=2.0, disagreements=[])
    # 2 healthy votes >= 2 threshold, all FAIL → SEMANTIC_FAIL
    assert judge_health_check([vr1, vr2, vr3]) == "SEMANTIC_FAIL"
