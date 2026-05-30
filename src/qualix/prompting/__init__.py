"""Prompt Harness primitives.

This package treats prompts as versioned, observable engineering artifacts.
Domain modules still own skill/rubric/protocol semantics; Prompt Harness owns
compilation metadata, assembly order, and manifest persistence.
"""

from qualix.prompting.assembler import PromptAssembler, PromptSection, PromptTemplate
from qualix.prompting.compiler import PromptBuild, PromptCompiler
from qualix.prompting.manifest import PromptManifest, write_prompt_manifest
from qualix.prompting.policy import PromptPolicyIssue, PromptPolicyResult, validate_prompt_artifact
from qualix.prompting.record import record_prompt_manifest
from qualix.prompting.spec import PromptAsset, PromptSpec

__all__ = [
    "PromptAssembler",
    "PromptAsset",
    "PromptBuild",
    "PromptCompiler",
    "PromptManifest",
    "PromptPolicyIssue",
    "PromptPolicyResult",
    "PromptSection",
    "PromptSpec",
    "PromptTemplate",
    "record_prompt_manifest",
    "validate_prompt_artifact",
    "write_prompt_manifest",
]
