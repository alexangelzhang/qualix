"""Prompt manifest persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from dqg.json_utils import save_json

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class PromptManifest:
    """Trace metadata for a rendered prompt artifact."""

    prompt_id: str
    prompt_type: str
    phase_id: str
    role: str
    version: str
    prompt_hash: str
    asset_hashes: dict[str, str] = field(default_factory=dict)
    section_hashes: dict[str, str] = field(default_factory=dict)
    section_sources: dict[str, tuple[str, ...]] = field(default_factory=dict)
    assembly_order: tuple[str, ...] = ()
    project_id: str | None = None
    language: str | None = None
    profile_id: str | None = None
    output_schema: str | None = None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable payload without empty optional values."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def write_prompt_manifest(prompt_path: Path, manifest: PromptManifest) -> Path:
    """Write manifest beside a prompt under the phase internal directory."""
    manifest_dir = prompt_path.parent / "_internal" / "_prompt_manifests"
    manifest_path = manifest_dir / f"{prompt_path.stem}.json"
    save_json(manifest_path, manifest.to_payload(), sort_keys=True)
    return manifest_path
