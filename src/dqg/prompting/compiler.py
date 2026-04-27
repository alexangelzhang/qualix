"""Prompt compiler and hashing helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dqg.prompting.manifest import PromptManifest

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dqg.prompting.spec import PromptAsset, PromptSpec


@dataclass(frozen=True)
class PromptBuild:
    """Compiled prompt text with its manifest."""

    prompt: str
    manifest: PromptManifest


class PromptCompiler:
    """Compile prompt sections into text and deterministic manifest metadata."""

    def compile(
        self,
        spec: PromptSpec,
        *,
        sections: Iterable[str],
        assets: Iterable[PromptAsset] = (),
        project_id: str | None = None,
    ) -> PromptBuild:
        prompt = "\n\n".join(section.strip() for section in sections if section.strip())
        manifest = PromptManifest(
            prompt_id=spec.prompt_id,
            prompt_type=spec.prompt_type,
            phase_id=spec.phase_id,
            role=spec.role,
            version=spec.version,
            prompt_hash=_sha256_text(prompt),
            asset_hashes=_hash_assets(assets),
            project_id=project_id,
            language=spec.language,
            profile_id=spec.profile_id,
            output_schema=spec.output_schema,
        )
        return PromptBuild(prompt=prompt, manifest=manifest)

    def compile_named_sections(
        self,
        spec: PromptSpec,
        *,
        sections: Iterable[tuple[str, str]],
        assets: Iterable[PromptAsset] = (),
        section_sources: dict[str, tuple[str, ...]] | None = None,
        project_id: str | None = None,
    ) -> PromptBuild:
        """Compile named sections and retain section-level trace metadata."""
        from dqg.core.model_registry import estimate_tokens

        normalized = [(name, content.strip()) for name, content in sections if content.strip()]
        prompt = "\n\n".join(content for _, content in normalized)
        manifest = PromptManifest(
            prompt_id=spec.prompt_id,
            prompt_type=spec.prompt_type,
            phase_id=spec.phase_id,
            role=spec.role,
            version=spec.version,
            prompt_hash=_sha256_text(prompt),
            asset_hashes=_hash_assets(assets),
            section_hashes={name: _sha256_text(content) for name, content in normalized},
            section_sources=section_sources or {},
            section_tokens={name: estimate_tokens(content) for name, content in normalized},
            assembly_order=tuple(name for name, _ in normalized),
            project_id=project_id,
            language=spec.language,
            profile_id=spec.profile_id,
            output_schema=spec.output_schema,
        )
        return PromptBuild(prompt=prompt, manifest=manifest)

    def compile_text(
        self,
        spec: PromptSpec,
        prompt: str,
        *,
        assets: Iterable[PromptAsset] = (),
        project_id: str | None = None,
    ) -> PromptBuild:
        """Build manifest metadata for already-rendered prompt text."""
        manifest = PromptManifest(
            prompt_id=spec.prompt_id,
            prompt_type=spec.prompt_type,
            phase_id=spec.phase_id,
            role=spec.role,
            version=spec.version,
            prompt_hash=_sha256_text(prompt),
            asset_hashes=_hash_assets(assets),
            project_id=project_id,
            language=spec.language,
            profile_id=spec.profile_id,
            output_schema=spec.output_schema,
        )
        return PromptBuild(prompt=prompt, manifest=manifest)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_assets(assets: Iterable[PromptAsset]) -> dict[str, str]:
    return {
        f"{asset.kind}:{asset.path}": _sha256_text(asset.content)
        for asset in sorted(assets, key=lambda item: (item.kind, item.path))
    }
