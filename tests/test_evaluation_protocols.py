"""Tests for evaluation_protocols.py — PhaseProtocol data structures and 7 Phase configs."""

from dqg.quality.evaluation_protocols import (
    PHASE_PROTOCOLS,
    get_protocol,
    render_protocol_for_prompt,
)


def test_all_seven_phases_have_protocols():
    for phase_id in ("Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"):
        assert phase_id in PHASE_PROTOCOLS, f"{phase_id} missing from PHASE_PROTOCOLS"


def test_each_protocol_has_judge_and_critique():
    for phase_id, protocol in PHASE_PROTOCOLS.items():
        assert len(protocol.judge.checklist) >= 3, f"{phase_id} judge checklist < 3"
        assert len(protocol.judge.red_lines) >= 1, f"{phase_id} judge red_lines < 1"
        assert len(protocol.judge.focus_areas) >= 2, f"{phase_id} judge focus_areas < 2"
        assert len(protocol.critique.checklist) >= 3, f"{phase_id} critique checklist < 3"
        assert len(protocol.critique.red_lines) >= 1, f"{phase_id} critique red_lines < 1"
        assert len(protocol.critique.focus_areas) >= 2, f"{phase_id} critique focus_areas < 2"


def test_judge_and_critique_checklists_are_different():
    for phase_id, protocol in PHASE_PROTOCOLS.items():
        judge_set = set(protocol.judge.checklist)
        critique_set = set(protocol.critique.checklist)
        if not judge_set or not critique_set:
            continue
        overlap = judge_set & critique_set
        overlap_ratio = len(overlap) / max(len(judge_set), len(critique_set))
        assert overlap_ratio < 0.5, f"{phase_id} judge/critique checklists overlap {overlap_ratio:.0%} >= 50%"


def test_render_protocol_for_prompt():
    protocol = PHASE_PROTOCOLS["Q01"].judge
    rendered = render_protocol_for_prompt(protocol)
    assert "## 检查清单" in rendered
    assert "## 行为红线" in rendered


def test_render_protocol_includes_domain_vocab():
    protocol = PHASE_PROTOCOLS["Q01"].judge
    rendered = render_protocol_for_prompt(protocol)
    assert "## 领域词汇" in rendered
    assert "REQ" in rendered


def test_get_protocol_returns_none_for_unknown():
    assert get_protocol("Q99") is None


def test_get_protocol_returns_correct_phase():
    protocol = get_protocol("Q07")
    assert protocol is not None
    assert protocol.phase_id == "Q07"
