"""Tests for Prompt Policy Gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.json_utils import load_json_strict, save_json
from dqg.prompting import PromptCompiler, PromptSpec, write_prompt_manifest
from dqg.prompting.policy import validate_prompt_artifact
from dqg.quality.critique import generate_critique_prompt
from dqg.quality.judge import generate_judge_prompt
from dqg.runtime.execution_context import ExecutionContext
from dqg.runtime.handlers_prompt_policy import handle_prompt_policy
from dqg.runtime.result import PhaseResult

if TYPE_CHECKING:
    from pathlib import Path


def _write_prompt_with_manifest(
    phase_dir: Path,
    *,
    prompt_type: str = "judge",
    prompt: str = "# Judge\n\n## 检查清单（必须逐条检查）\n- 覆盖需求\n\n## 行为红线（绝对不能做）\n- 不编造\n\n必须引用证据，并按 JSON schema 输出。",
    output_schema: str | None = "judge_result",
) -> Path:
    prompt_path = phase_dir / f"_{prompt_type}_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    spec = PromptSpec(
        prompt_id=f"{prompt_type}.Q01",
        prompt_type=prompt_type,
        phase_id="Q01",
        role=prompt_type,
        output_schema=output_schema,
    )
    build = PromptCompiler().compile_text(spec, prompt, project_id="demo")
    write_prompt_manifest(prompt_path, build.manifest)
    return prompt_path


def test_validate_prompt_artifact_blocks_missing_manifest(tmp_path: Path) -> None:
    prompt_path = tmp_path / "_judge_prompt.md"
    prompt_path.write_text(
        "# Judge\n\n## 检查清单（必须逐条检查）\n- 覆盖需求\n\n## 行为红线（绝对不能做）\n- 不编造\n\n必须引用证据，并按 JSON schema 输出。",
        encoding="utf-8",
    )

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "missing_manifest" for issue in result.issues)


def test_validate_prompt_artifact_blocks_hash_mismatch(tmp_path: Path) -> None:
    prompt_path = _write_prompt_with_manifest(tmp_path)
    prompt_path.write_text("# Judge\n\n被篡改的 prompt", encoding="utf-8")

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "prompt_hash_mismatch" for issue in result.issues)


def test_validate_prompt_artifact_blocks_structured_prompt_without_schema(tmp_path: Path) -> None:
    prompt_path = _write_prompt_with_manifest(tmp_path, output_schema=None)

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "missing_output_schema" for issue in result.issues)


def test_validate_prompt_artifact_blocks_missing_evidence_contract(tmp_path: Path) -> None:
    prompt_path = _write_prompt_with_manifest(tmp_path, prompt="# Judge\n\n请整体评价一下。")

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "missing_evidence_contract" for issue in result.issues)


def test_validate_prompt_artifact_blocks_expert_persona_label(tmp_path: Path) -> None:
    prompt_path = _write_prompt_with_manifest(
        tmp_path,
        prompt=(
            "# Judge\n\n## 你的身份\n\n你是一位有 10 年经验的安全审计专家。\n\n"
            "## 检查清单（必须逐条检查）\n- 覆盖需求\n\n"
            "## 行为红线（绝对不能做）\n- 不编造\n\n"
            "必须引用证据，并按 JSON schema 输出。"
        ),
    )

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "expert_persona_label" for issue in result.issues)


def test_validate_prompt_artifact_blocks_missing_protocol_contract(tmp_path: Path) -> None:
    prompt_path = _write_prompt_with_manifest(tmp_path, prompt="# Judge\n\n必须引用证据，并按 JSON schema 输出。")

    result = validate_prompt_artifact(prompt_path)

    assert not result.passed
    assert any(issue.code == "missing_protocol_contract" for issue in result.issues)


def test_handle_prompt_policy_blocks_phase_on_policy_issue(tmp_path: Path) -> None:
    phase_dir = tmp_path / "output" / "demo" / "Q01"
    prompt_path = _write_prompt_with_manifest(phase_dir)
    manifest_path = phase_dir / "_internal" / "_prompt_manifests" / "_judge_prompt.json"
    manifest = {**load_json_strict(manifest_path), "prompt_hash": "bad"}
    save_json(manifest_path, manifest)
    ctx = ExecutionContext(output_dir=tmp_path / "output", project_id="demo", phase_id="Q01")
    ctx.phase_root = phase_dir
    ctx.internal_dir = phase_dir / "_internal"
    result = PhaseResult(phase_id="Q01", action="finalize")

    handle_prompt_policy(ctx, result)

    assert not result.success
    assert any("prompt_hash_mismatch" in error for error in result.errors)
    assert prompt_path.name in result.errors[0]


def test_generated_judge_and_critique_prompts_avoid_expert_persona(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    judge = generate_judge_prompt(output_dir, "demo", "Q01")
    critique = generate_critique_prompt(output_dir, "demo", "Q01")

    assert judge is not None
    assert critique is not None
    for prompt in (judge, critique):
        assert "你的身份" not in prompt
        assert "你是一位" not in prompt
        assert "资深" not in prompt
        assert "年经验" not in prompt
        assert "检查清单" in prompt
        assert "行为红线" in prompt
