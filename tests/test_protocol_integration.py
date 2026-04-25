# tests/test_protocol_integration.py
"""Integration tests for Phase evaluation protocol system."""

from __future__ import annotations


def test_protocol_renders_into_judge_prompt():
    """Protocol renders into text suitable for Judge prompt injection."""
    from dqg.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt

    for phase_id in ("Q01", "Q03", "Q04", "Q05", "Q06", "Q07"):
        proto = get_protocol(phase_id)
        assert proto is not None
        judge_text = render_protocol_for_prompt(proto.judge)
        critique_text = render_protocol_for_prompt(proto.critique)
        assert len(judge_text) > 100, f"{phase_id} judge text too short"
        assert len(critique_text) > 100, f"{phase_id} critique text too short"
        assert "检查清单" in judge_text
        assert "重点检查方向" in critique_text


def test_gene_store_phase_filtering_end_to_end(tmp_path):
    """Genes saved with phase+role are correctly filtered on load."""
    from dqg.quality.gene_store import load_genes_for_phase, save_genes

    genes = [
        {
            "gene_id": "GENE-Q03-FN-20260425-judge",
            "phase_id": "Q03",
            "agent_role": "judge",
            "error_type": "FN",
            "severity": "high",
            "target_pattern": "降级",
            "description": "缺少降级",
            "confidence": "high",
            "impact": "high",
            "source": {},
            "match_count": 0,
            "last_matched_at": None,
        },
        {
            "gene_id": "GENE-Q03-FN-20260425-critique",
            "phase_id": "Q03",
            "agent_role": "critique",
            "error_type": "FN",
            "severity": "high",
            "target_pattern": "级联",
            "description": "级联失败",
            "confidence": "high",
            "impact": "high",
            "source": {},
            "match_count": 0,
            "last_matched_at": None,
        },
        {
            "gene_id": "GENE-Q07-FN-20260425-judge",
            "phase_id": "Q07",
            "agent_role": "judge",
            "error_type": "FN",
            "severity": "high",
            "target_pattern": "注入",
            "description": "SQL注入",
            "confidence": "high",
            "impact": "high",
            "source": {},
            "match_count": 0,
            "last_matched_at": None,
        },
    ]
    save_genes(tmp_path, genes)

    q03j = load_genes_for_phase(tmp_path, "Q03", agent_role="judge")
    assert len(q03j) == 1
    assert q03j[0]["gene_id"] == "GENE-Q03-FN-20260425-judge"

    q03_all = load_genes_for_phase(tmp_path, "Q03")
    assert len(q03_all) == 2

    q07j = load_genes_for_phase(tmp_path, "Q07", agent_role="judge")
    assert len(q07j) == 1


def test_compose_rubric_plus_protocol():
    """compose_rubric + protocol render can be concatenated."""
    from dqg.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt
    from dqg.quality.judge_rubrics import compose_rubric

    rubric = compose_rubric("Q07")
    proto = get_protocol("Q07")
    assert proto is not None
    protocol_text = render_protocol_for_prompt(proto.judge)

    combined = protocol_text + "\n\n" + rubric
    assert "检查清单" in combined
    assert "source_citation" in combined
    assert "finding_validity" in combined
