"""Integration tests for prompt manifests in existing prompt writers."""

from __future__ import annotations

from qualix.json_utils import load_json_strict
from qualix.quality.critique import write_critique_prompt, write_preference_prompt
from qualix.quality.judge import write_judge_prompt
from qualix.quality.review_chain import write_review_chain_prompt


def test_write_judge_prompt_persists_prompt_manifest(tmp_path) -> None:
    output_dir = tmp_path / "output"
    path = write_judge_prompt(output_dir, "demo", "Q01")

    assert path is not None
    manifest_path = output_dir / "demo" / "Q01" / "_internal" / "_prompt_manifests" / "_judge_prompt.json"
    manifest = load_json_strict(manifest_path)
    assert manifest["prompt_id"] == "judge.Q01"
    assert manifest["prompt_type"] == "judge"
    assert manifest["phase_id"] == "Q01"
    assert manifest["project_id"] == "demo"
    assert manifest["prompt_hash"]
    assert manifest["assembly_order"][:5] == [
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
        "rubric",
    ]
    assert manifest["section_hashes"]["evaluation_protocol"]
    assert manifest["section_hashes"]["rubric"]
    assert "qualix.quality.judge_rubrics" in manifest["section_sources"]["rubric"]


def test_write_critique_prompt_persists_prompt_manifest(tmp_path) -> None:
    output_dir = tmp_path / "output"
    path = write_critique_prompt(output_dir, "demo", "Q01")

    assert path is not None
    manifest_path = output_dir / "demo" / "Q01" / "_internal" / "_prompt_manifests" / "_critique_prompt.json"
    manifest = load_json_strict(manifest_path)
    assert manifest["prompt_id"] == "critique.Q01"
    assert manifest["prompt_type"] == "critique"
    assert manifest["output_schema"] == "critique_result"
    assert manifest["assembly_order"][:4] == [
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
    ]
    assert manifest["section_hashes"]["critique_steps"]
    assert "qualix.quality.evaluation_protocols" in manifest["section_sources"]["evaluation_protocol"]


def test_write_review_chain_prompt_persists_prompt_manifest(tmp_path) -> None:
    output_dir = tmp_path / "output"
    path = write_review_chain_prompt(output_dir, "demo", "Q01")

    assert path is not None
    manifest_path = output_dir / "demo" / "Q01" / "_internal" / "_prompt_manifests" / "_review_chain.json"
    manifest = load_json_strict(manifest_path)
    assert manifest["prompt_id"] == "review_chain.Q01"
    assert manifest["prompt_type"] == "review_chain"
    assert manifest["phase_id"] == "Q01"
    assert manifest["assembly_order"] == [
        "goal",
        "judge_block",
        "critique_block",
        "preference_block",
        "completion_contract",
    ]
    assert "qualix.quality.judge" in manifest["section_sources"]["judge_block"]


def test_write_preference_prompt_persists_section_manifest(tmp_path) -> None:
    output_dir = tmp_path / "output"
    path = write_preference_prompt(output_dir, "demo", "Q01")

    assert path is not None
    manifest_path = output_dir / "demo" / "Q01" / "_internal" / "_prompt_manifests" / "_preference_prompt.json"
    manifest = load_json_strict(manifest_path)
    assert manifest["prompt_id"] == "preference.Q01"
    assert manifest["prompt_type"] == "preference"
    assert manifest["section_hashes"]["comparison_steps"]
