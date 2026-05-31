"""Schema for Q05a target-module discovery output."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TargetMapping(BaseModel):
    item_id: str = Field(default="", description="REQ/BR/SE id")
    impl_class: str = ""
    repo: str = ""
    found: bool = False
    gap_reason: str | None = None
    evidence: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, values: dict) -> dict:
        if "item_id" not in values:
            values["item_id"] = values.get("se_id") or values.get("br_id") or values.get("req_id") or ""
        return values

    @model_validator(mode="after")
    def found_requires_impl_or_gap(self) -> TargetMapping:
        if self.found and not self.impl_class:
            msg = f"{self.item_id or 'mapping'} found=true 时 impl_class 必填"
            raise ValueError(msg)
        if not self.found and not self.gap_reason:
            msg = f"{self.item_id or 'mapping'} found=false 时 gap_reason 必填"
            raise ValueError(msg)
        return self


class CodeSymbolTarget(BaseModel):
    name: str
    kind: str
    file: str
    language: str = ""
    container: str = ""


class Q05TargetModules(BaseModel):
    target_repos: list[str] = Field(default_factory=list)
    git_diff_files: list[str] = Field(default_factory=list)
    se_mappings: list[TargetMapping] = Field(default_factory=list)
    br_mappings: list[TargetMapping] = Field(default_factory=list)
    code_symbols: list[CodeSymbolTarget] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    default_branch: str = ""
    language_id: str = ""

