"""Prompt specification types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    """Identity and policy-facing metadata for a compiled prompt."""

    prompt_id: str
    prompt_type: str
    phase_id: str
    role: str
    version: str = "1.0.0"
    language: str | None = None
    profile_id: str | None = None
    output_schema: str | None = None


@dataclass(frozen=True)
class PromptAsset:
    """Source asset that influenced a compiled prompt."""

    kind: str
    path: str
    content: str
