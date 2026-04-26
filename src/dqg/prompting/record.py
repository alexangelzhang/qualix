"""Helpers for recording prompt artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.prompting.compiler import PromptCompiler
from dqg.prompting.manifest import write_prompt_manifest
from dqg.prompting.spec import PromptAsset, PromptSpec

if TYPE_CHECKING:
    from pathlib import Path


def record_prompt_manifest(
    prompt_path: Path,
    *,
    prompt: str,
    prompt_type: str,
    phase_id: str,
    project_id: str,
    role: str | None = None,
    assets: tuple[PromptAsset, ...] = (),
    output_schema: str | None = None,
) -> Path:
    """Persist manifest metadata for a rendered prompt file."""
    spec = PromptSpec(
        prompt_id=f"{prompt_type}.{phase_id}",
        prompt_type=prompt_type,
        phase_id=phase_id,
        role=role or prompt_type,
        output_schema=output_schema,
    )
    build = PromptCompiler().compile_text(spec, prompt, assets=assets, project_id=project_id)
    return write_prompt_manifest(prompt_path, build.manifest)
