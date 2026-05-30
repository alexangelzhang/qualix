# tests/test_gene_store_phase_filter.py
"""Tests for Gene store phase_id + agent_role filtering."""

from __future__ import annotations


def _make_gene(gene_id: str, phase_id: str, agent_role: str = "judge") -> dict:
    return {
        "gene_id": f"GENE-{phase_id}-FN-20260101000000-{gene_id}",
        "phase_id": phase_id,
        "agent_role": agent_role,
        "error_type": "FN",
        "severity": "high",
        "target_pattern": "降级|超时",
        "description": "缺少降级策略",
        "action": "补充降级方案",
        "confidence": "high",
        "impact": "high",
        "source": {"project_id": "test", "phase_id": phase_id},
        "match_count": 0,
        "last_matched_at": None,
    }


def test_load_genes_for_phase_and_role(tmp_path):
    """load_genes_for_phase filters by phase_id (existing behavior)."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(tmp_path, [_make_gene("G1", "Q03"), _make_gene("G2", "Q07")])
    q03_genes = load_genes_for_phase(tmp_path, "Q03")
    assert len(q03_genes) == 1
    assert q03_genes[0]["gene_id"] == "GENE-Q03-FN-20260101000000-G1"


def test_load_genes_filters_by_agent_role(tmp_path):
    """load_genes_for_phase with agent_role filters correctly."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(
        tmp_path,
        [
            _make_gene("G1", "Q03", "judge"),
            _make_gene("G2", "Q03", "critique"),
        ],
    )
    judge_genes = load_genes_for_phase(tmp_path, "Q03", agent_role="judge")
    assert len(judge_genes) == 1
    assert judge_genes[0]["agent_role"] == "judge"

    critique_genes = load_genes_for_phase(tmp_path, "Q03", agent_role="critique")
    assert len(critique_genes) == 1
    assert critique_genes[0]["agent_role"] == "critique"


def test_load_genes_no_role_filter_returns_all(tmp_path):
    """Without agent_role filter, returns all genes for the phase."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(
        tmp_path,
        [
            _make_gene("G1", "Q03", "judge"),
            _make_gene("G2", "Q03", "critique"),
        ],
    )
    all_genes = load_genes_for_phase(tmp_path, "Q03")
    assert len(all_genes) == 2


def test_extract_genes_includes_agent_role():
    """Extracted genes include agent_role field."""
    from qualix.quality.gene_store import extract_genes_from_preference

    preference = {
        "preferred": "v2",
        "confidence": "high",
        "critique_effectiveness": [
            {"was_valid": True, "should_persist": True, "impact": "high", "critique_issue": "缺少降级"}
        ],
    }
    critique = {"issues_found": [{"description": "缺少降级", "type": "FN", "severity": "high"}]}
    genes = extract_genes_from_preference(preference, critique, "Q03", "test-proj", agent_role="judge")
    assert len(genes) >= 1
    assert genes[0].get("agent_role") == "judge"
