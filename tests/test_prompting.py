"""Tests for Prompt Harness primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.json_utils import load_json_strict
from qualix.prompting import PromptAsset, PromptCompiler, PromptSpec, write_prompt_manifest

if TYPE_CHECKING:
    from pathlib import Path


def test_prompt_compiler_builds_stable_manifest() -> None:
    spec = PromptSpec(
        prompt_id="judge.Q01",
        prompt_type="judge",
        phase_id="Q01",
        role="judge",
        output_schema="judge_result",
        language="kotlin",
    )
    assets = [
        PromptAsset(kind="rubric", path="quality/judge_rubrics.py", content="score every dimension"),
        PromptAsset(kind="protocol", path="quality/evaluation_protocols.py", content="must cite evidence"),
    ]

    first = PromptCompiler().compile(
        spec,
        sections=["# Judge", "Read files", "Return JSON"],
        assets=assets,
    )
    second = PromptCompiler().compile(
        spec,
        sections=["# Judge", "Read files", "Return JSON"],
        assets=list(reversed(assets)),
    )

    assert first.prompt == "# Judge\n\nRead files\n\nReturn JSON"
    assert first.manifest.prompt_hash == second.manifest.prompt_hash
    assert first.manifest.language == "kotlin"
    assert first.manifest.asset_hashes["protocol:quality/evaluation_protocols.py"]
    assert first.manifest.asset_hashes["rubric:quality/judge_rubrics.py"]


def test_prompt_compiler_records_section_sources() -> None:
    spec = PromptSpec(prompt_id="judge.Q01", prompt_type="judge", phase_id="Q01", role="judge")

    build = PromptCompiler().compile_named_sections(
        spec,
        sections=[("rubric", "RUBRIC"), ("evaluation_protocol", "PROTOCOL")],
        section_sources={
            "rubric": ("qualix.quality.judge_rubrics", "qualix.quality.dynamic_rubric"),
            "evaluation_protocol": ("qualix.quality.evaluation_protocols",),
        },
    )

    assert build.manifest.section_sources["rubric"] == (
        "qualix.quality.judge_rubrics",
        "qualix.quality.dynamic_rubric",
    )
    assert build.manifest.section_sources["evaluation_protocol"] == ("qualix.quality.evaluation_protocols",)


def test_write_prompt_manifest_uses_internal_manifest_dir(tmp_path: Path) -> None:
    spec = PromptSpec(
        prompt_id="critique.Q06",
        prompt_type="critique",
        phase_id="Q06",
        role="critique",
    )
    build = PromptCompiler().compile(spec, sections=["critique prompt"])
    prompt_path = tmp_path / "output" / "demo" / "Q06" / "_critique_prompt.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text(build.prompt, encoding="utf-8")

    manifest_path = write_prompt_manifest(prompt_path, build.manifest)
    payload = load_json_strict(manifest_path)

    assert manifest_path == prompt_path.parent / "_internal" / "_prompt_manifests" / "_critique_prompt.json"
    assert payload["prompt_id"] == "critique.Q06"
    assert payload["prompt_type"] == "critique"
    assert payload["phase_id"] == "Q06"
    assert payload["prompt_hash"] == build.manifest.prompt_hash
