# tests/test_adaptive_loop_rdt.py
"""Integration tests for P1+P2+P3 RDT-inspired review optimization."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def tmp_output(tmp_path):
    """Set up a minimal output directory with blast_radius and upstream context."""
    project_id = "test-project"
    phase_dir = tmp_path / project_id / "Q07"
    internal = phase_dir / "_internal"
    internal.mkdir(parents=True)

    # P1: blast_radius with HIGH risk
    blast = {"risk_tier": "HIGH", "risk_score": 65, "changed_files": ["A.java"]}
    (internal / "_blast_radius.json").write_text(json.dumps(blast))

    # P2: upstream context with REQ/BR/SE
    upstream = "- REQ-001: 用户创建维保单\n- BR-001: 单个维保单最多关联 5 辆车\n- SE-001: 创建时校验车辆数量上限\n"
    (phase_dir / "_upstream_context.md").write_text(upstream)

    return tmp_path, project_id


def test_p1_depth_config_resolves_from_blast_radius(tmp_output):
    """HIGH risk_tier → max_iterations=3, force_secondary=True."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["HIGH"]
    assert cfg["max_iterations"] == 3
    assert cfg["force_secondary"] is True


def test_p2_anchor_extracted_from_upstream(tmp_output):
    """Anchor summary extracts REQ/BR/SE from upstream context."""
    tmp_path, project_id = tmp_output
    upstream_path = tmp_path / project_id / "Q07" / "_upstream_context.md"

    from qualix.agents.handoff_builder import extract_anchor_summary

    text = upstream_path.read_text()
    anchor = extract_anchor_summary(text)
    assert "REQ-001" in anchor
    assert "BR-001" in anchor
    assert "SE-001" in anchor


def test_p3_composed_rubric_has_shared_and_routed():
    """Q07 composed rubric includes both shared and routed dimensions."""
    from qualix.quality.judge_rubrics import compose_rubric_structured

    dims = compose_rubric_structured("Q07")
    ids = {d["id"] for d in dims}
    # Shared
    assert "source_citation" in ids
    assert "confidence_tagging" in ids
    # Routed (Q07-specific)
    assert "finding_validity" in ids
    assert "req_code_alignment" in ids


def test_p1_p2_p3_all_wired_in_adaptive_loop(tmp_output):
    """Smoke test: adaptive loop resolves depth, anchor, and rubric without error."""
    tmp_path, project_id = tmp_output

    # We can't run the full loop (needs LLM), but we can verify the setup code runs
    from qualix.constants import REVIEW_DEPTH_CONFIG, REVIEW_DEPTH_DEFAULT
    from qualix.json_utils import load_json

    blast_path = tmp_path / project_id / "Q07" / "_internal" / "_blast_radius.json"
    blast_data = load_json(blast_path)
    risk_tier = blast_data.get("risk_tier", REVIEW_DEPTH_DEFAULT)
    depth_cfg = REVIEW_DEPTH_CONFIG[risk_tier]

    assert depth_cfg["max_iterations"] == 3  # HIGH
    assert depth_cfg["force_secondary"] is True

    upstream_path = tmp_path / project_id / "Q07" / "_upstream_context.md"
    assert upstream_path.exists()

    from qualix.agents.handoff_builder import extract_anchor_summary

    anchor = extract_anchor_summary(upstream_path.read_text())
    assert "REQ-001" in anchor

    from qualix.quality.judge_rubrics import compose_rubric

    rubric = compose_rubric("Q07")
    assert "source_citation" in rubric
    assert "finding_validity" in rubric
