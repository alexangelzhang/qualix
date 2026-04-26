"""Tests for centralized prompt assembly."""

from __future__ import annotations

import pytest

from dqg.prompting import PromptAssembler, PromptSpec, PromptTemplate
from dqg.quality.critique import build_critique_prompt, build_preference_prompt
from dqg.quality.judge import build_judge_prompt
from dqg.quality.review_chain import build_review_chain_prompt


def test_prompt_assembler_preserves_judge_order_and_section_hashes() -> None:
    spec = PromptSpec(
        prompt_id="judge.Q01",
        prompt_type="judge",
        phase_id="Q01",
        role="judge",
        output_schema="judge_result",
    )

    build = PromptAssembler.for_role("judge").assemble(
        spec,
        {
            "rubric": "RUBRIC",
            "goal": "GOAL",
            "behavior_constraints": "CONSTRAINTS",
            "gate_checklist": "CHECKLIST",
            "evaluation_protocol": "PROTOCOL",
            "inputs": "INPUTS",
            "bug_cases": "BUGS",
            "genes": "GENES",
            "anti_rationalization": "ANTI",
            "output_schema": "SCHEMA",
        },
        project_id="demo",
    )

    assert build.prompt == "\n\n".join(
        [
            "GOAL",
            "CONSTRAINTS",
            "CHECKLIST",
            "PROTOCOL",
            "RUBRIC",
            "INPUTS",
            "BUGS",
            "GENES",
            "ANTI",
            "SCHEMA",
        ]
    )
    assert build.manifest.assembly_order == (
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
        "rubric",
        "inputs",
        "bug_cases",
        "genes",
        "anti_rationalization",
        "output_schema",
    )
    assert set(build.manifest.section_hashes) == set(build.manifest.assembly_order)
    assert build.manifest.project_id == "demo"


def test_prompt_assembler_rejects_missing_required_judge_section() -> None:
    spec = PromptSpec(prompt_id="judge.Q01", prompt_type="judge", phase_id="Q01", role="judge")

    with pytest.raises(ValueError, match="missing required prompt sections"):
        PromptAssembler.for_role("judge").assemble(
            spec,
            {
                "goal": "GOAL",
                "behavior_constraints": "CONSTRAINTS",
                "gate_checklist": "CHECKLIST",
                "evaluation_protocol": "PROTOCOL",
                "rubric": "RUBRIC",
            },
        )


def test_prompt_assembler_preserves_critique_order_and_section_hashes() -> None:
    spec = PromptSpec(
        prompt_id="critique.Q01",
        prompt_type="critique",
        phase_id="Q01",
        role="critique",
        output_schema="critique_result",
    )

    build = PromptAssembler.for_role("critique").assemble(
        spec,
        {
            "goal": "GOAL",
            "behavior_constraints": "CONSTRAINTS",
            "gate_checklist": "CHECKLIST",
            "evaluation_protocol": "PROTOCOL",
            "inputs": "INPUTS",
            "bug_cases": "BUGS",
            "critique_steps": "STEPS",
            "output_schema": "SCHEMA",
            "revision_instructions": "REVISION",
        },
        project_id="demo",
    )

    assert build.manifest.assembly_order == (
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
        "inputs",
        "bug_cases",
        "critique_steps",
        "output_schema",
        "revision_instructions",
    )
    assert build.prompt.index("GOAL") < build.prompt.index("PROTOCOL") < build.prompt.index("STEPS")
    assert build.manifest.section_hashes["evaluation_protocol"]
    assert build.manifest.section_hashes["critique_steps"]


def test_prompt_template_renders_variables() -> None:
    section = PromptTemplate(name="goal", template="Phase {phase_id}: {phase_name}").render(
        phase_id="Q01",
        phase_name="需求结构化",
    )

    assert section.name == "goal"
    assert section.content == "Phase Q01: 需求结构化"


def test_prompt_template_rejects_missing_variables() -> None:
    with pytest.raises(ValueError, match="missing template variables"):
        PromptTemplate(name="goal", template="Phase {phase_id}: {phase_name}").render(phase_id="Q01")


def test_build_judge_prompt_returns_section_traced_build(tmp_path) -> None:
    build = build_judge_prompt(tmp_path / "output", "demo", "Q01")

    assert build is not None
    assert build.manifest.assembly_order[:5] == (
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
        "rubric",
    )
    assert (
        build.prompt.index("## Gate Checklist") < build.prompt.index("## 检查清单") < build.prompt.index("## 评审维度")
    )
    assert build.manifest.section_hashes["evaluation_protocol"]
    assert build.manifest.section_hashes["rubric"]


def test_build_critique_prompt_returns_section_traced_build(tmp_path) -> None:
    build = build_critique_prompt(tmp_path / "output", "demo", "Q01")

    assert build is not None
    assert build.manifest.assembly_order[:4] == (
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "evaluation_protocol",
    )
    assert (
        build.prompt.index("## Gate Checklist") < build.prompt.index("## 检查清单") < build.prompt.index("## 批评步骤")
    )
    assert build.manifest.section_hashes["evaluation_protocol"]
    assert build.manifest.section_hashes["critique_steps"]


def test_build_preference_prompt_returns_section_traced_build(tmp_path) -> None:
    build = build_preference_prompt(tmp_path / "output", "demo", "Q01")

    assert build is not None
    assert build.manifest.assembly_order == (
        "goal",
        "behavior_constraints",
        "gate_checklist",
        "inputs",
        "comparison_steps",
        "output_schema",
    )
    assert build.manifest.section_hashes["comparison_steps"]


def test_build_review_chain_prompt_returns_section_traced_build(tmp_path) -> None:
    build = build_review_chain_prompt(tmp_path / "output", "demo", "Q01")

    assert build is not None
    assert build.manifest.assembly_order == (
        "goal",
        "judge_block",
        "critique_block",
        "preference_block",
        "completion_contract",
    )
    assert build.manifest.section_hashes["judge_block"]
