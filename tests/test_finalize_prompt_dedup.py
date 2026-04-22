"""Tests for finalize prompt de-duplication."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from dqg.commands.phase import cmd_finalize
from dqg.core.state_machine import PhaseStatus, ProjectState, save_state

if TYPE_CHECKING:
    from pathlib import Path


def _prepare_phase_a(output_dir: Path, project_id: str) -> None:
    state = ProjectState(project_id=project_id)
    state.phases["Q01"].status = PhaseStatus.IN_PROGRESS
    save_state(output_dir, state)

    phase_dir = output_dir / project_id / "Q01"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "phase_a_report.md").write_text("## PROFILE_CONTEXT\n\n# Report\n", encoding="utf-8")
    (phase_dir / "phase_a_structured.json").write_text('{"project_id": "demo", "requirements": []}', encoding="utf-8")


def test_finalize_reuses_review_chain_payload_and_does_not_regenerate_prompts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _prepare_phase_a(output_dir, "demo")

    state = ProjectState(project_id="demo")
    state.phases["Q01"].status = PhaseStatus.IN_PROGRESS

    monkeypatch.setattr("dqg.commands.phase.load_state", lambda *_: state)
    monkeypatch.setattr("dqg.commands.phase.save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("dqg.reporting.telemetry.append_record", lambda *args, **kwargs: None)
    monkeypatch.setattr("dqg.commands.phase.finalize_phase", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.commands.phase.record_judge_score", lambda *args, **kwargs: None)

    monkeypatch.setattr("dqg.quality.finalize_checks.run_finalize_checks", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.quality.cross_phase_check.check_cross_phase_refs", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.schemas.validate_phase_output", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.cache.fact_cache.index_phase_facts", lambda *args, **kwargs: 0)
    monkeypatch.setattr("dqg.reporting.perf_tracker.collect_phase_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr("dqg.reporting.perf_tracker.persist_phase_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "dqg.memory.memory_layer.MemoryLayer.index_phase", lambda *args, **kwargs: {"facts": 0, "version_diff": None}
    )
    monkeypatch.setattr("dqg.quality.golden_sample.compare_with_golden", lambda *args, **kwargs: {})
    monkeypatch.setattr("dqg.quality.golden_sample.format_golden_diff", lambda diff: "golden")
    monkeypatch.setattr("dqg.quality.rule_compliance.compute_rule_compliance", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "dqg.skill_tracker.track_rule_quality",
        lambda *args, **kwargs: {"matched_signals": [], "potential_new_issues": []},
    )
    monkeypatch.setattr("dqg.memory.version_tracker.extract_facts_from_json", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.memory.version_tracker.format_version_diff", lambda *args, **kwargs: "version")
    monkeypatch.setattr("dqg.memory.version_tracker.track_version", lambda *args, **kwargs: {})
    monkeypatch.setattr("dqg.skill_tracker.auto_generate_bug_case", lambda *args, **kwargs: [])
    monkeypatch.setattr("dqg.skill_tracker.suggest_prompt_fix", lambda *args, **kwargs: [])

    review_counts = {"judge": 0, "critique": 0}

    def _judge_prompt(*args, **kwargs):
        review_counts["judge"] += 1
        return "# Judge\n\nJUDGE_BODY"

    def _critique_prompt(*args, **kwargs):
        review_counts["critique"] += 1
        return "# Critique\n\nCRITIQUE_BODY"

    monkeypatch.setattr("dqg.quality.review_chain.generate_judge_prompt", _judge_prompt)
    monkeypatch.setattr("dqg.quality.review_chain.generate_critique_prompt", _critique_prompt)

    monkeypatch.setattr(
        "dqg.quality.judge.generate_judge_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("judge prompt should be reused")),
    )
    monkeypatch.setattr(
        "dqg.quality.critique.generate_critique_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("critique prompt should be reused")),
    )

    exit_code = cmd_finalize(SimpleNamespace(project_id="demo", phase="Q01", base_dir=str(tmp_path)), output_dir)

    assert exit_code == 0
    assert review_counts == {"judge": 1, "critique": 1}

    phase_dir = output_dir / "demo" / "Q01"
    assert (phase_dir / "_review_chain.md").exists()
    assert (phase_dir / "_judge_prompt.md").read_text(encoding="utf-8") == "# Judge\n\nJUDGE_BODY"
    assert (phase_dir / "_critique_prompt.md").read_text(encoding="utf-8") == "# Critique\n\nCRITIQUE_BODY"
