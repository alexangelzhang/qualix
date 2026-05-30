# tests/test_anchor_injection.py
"""Tests for P2: anchor injection to prevent drift."""

from __future__ import annotations

import textwrap

SAMPLE_UPSTREAM = textwrap.dedent("""\
    # Evidence Pack

    ## 需求事实

    - REQ-001: 用户可以创建维保单
    - REQ-002: 维保单支持多车辆关联
    - REQ-003: 维保单状态流转需要审批

    ## 业务规则

    - BR-001: 单个维保单最多关联 5 辆车
    - BR-002: 审批通过后不可撤回
    - BR-003: 金额超过 5000 元需要二级审批

    ## 语义元素

    - SE-001: 创建维保单时校验车辆数量上限
    - SE-002: 状态机流转合法性校验
    - SE-003: 金额阈值触发审批升级
    - SE-004: 并发创建幂等保护

    ## 其他内容
    这里是不相关的内容，不应该被提取。
""")


def test_extract_anchor_summary_extracts_req_br_se():
    """Should extract REQ/BR/SE lines grouped by type."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    result = extract_anchor_summary(SAMPLE_UPSTREAM)
    assert "REQ-001" in result
    assert "BR-001" in result
    assert "SE-001" in result
    assert "核心需求" in result or "REQ" in result
    assert "其他内容" not in result


def test_extract_anchor_summary_empty_input():
    """Empty input returns empty string."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    assert extract_anchor_summary("") == ""


def test_extract_anchor_summary_no_ids():
    """Input without REQ/BR/SE returns empty string."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    assert extract_anchor_summary("just some random text\nno IDs here") == ""


def test_extract_anchor_summary_truncates_to_max_tokens():
    """Long input gets truncated to max_tokens."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    lines = [f"- REQ-{i:03d}: 需求描述 {i} " + "详细内容" * 20 for i in range(50)]
    big_input = "\n".join(lines)
    result = extract_anchor_summary(big_input, max_tokens=200)
    assert len(result) < len(big_input)
    assert "REQ-000" in result


def test_handoff_includes_anchor_section():
    """When anchor_facts is provided, handoff includes Anchor section between Goal and Progress."""
    from qualix.agents.judge_vote import IterationRecord, JudgeVote, VoteResult

    vote = JudgeVote(model="m", scores={}, overall=2.5, verdict="FAIL", issues=[], duration=1.0)
    vr = VoteResult(votes=[vote], consensus="FAIL", avg_score=2.5, disagreements=[])
    prev = IterationRecord(iteration=1, judge_result=vr)

    from qualix.agents.handoff_builder import build_handoff_document

    anchor = "## Anchor（原始需求锚点 — 修正时不可偏离）\n\n### 核心需求 (REQ)\n- REQ-001: 测试需求"
    result = build_handoff_document(prev, 2, anchor_facts=anchor)

    assert "Anchor" in result
    assert "REQ-001" in result
    # Anchor should appear before Progress
    anchor_pos = result.index("Anchor")
    progress_pos = result.index("Progress")
    assert anchor_pos < progress_pos


def test_handoff_without_anchor_unchanged():
    """When anchor_facts is None, handoff is unchanged from current behavior."""
    from qualix.agents.judge_vote import IterationRecord, JudgeVote, VoteResult

    vote = JudgeVote(model="m", scores={}, overall=2.5, verdict="FAIL", issues=[], duration=1.0)
    vr = VoteResult(votes=[vote], consensus="FAIL", avg_score=2.5, disagreements=[])
    prev = IterationRecord(iteration=1, judge_result=vr)

    from qualix.agents.handoff_builder import build_handoff_document

    result = build_handoff_document(prev, 2, anchor_facts=None)
    assert "Anchor" not in result
    assert "Goal" in result
    assert "Progress" in result
